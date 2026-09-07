#!/usr/bin/env python3
"""
FastAPI backend for the Finance Chart (Sandbox) UI.

The user types a natural-language question ("apple stock price over the last 6
months?"). The backend, using the Perplexity Python SDK, runs a two-phase flow:

  Phase 1 (data)    A *background* Agent API request gives the model the
                    ``sandbox`` tool, which resolves the ticker + period from
                    the question, fetches the daily closing prices inside an
                    isolated container, and **writes them to a CSV file**
                    (downloaded here) plus a tiny META block on stdout.
  Phase 2 (answer)  A *streaming* request (no sandbox) writes a short
                    natural-language analysis of that series, token by token.

The sandbox tool only runs as a background task (not streamable), so the prose
answer is produced by the separate streaming call in phase 2.

Endpoints:
  POST /api/charts                 -> submit a question, returns {"job_id"}
  GET  /api/charts/{id}/events     -> Server-Sent Events: progress, chart,
                                      streamed answer tokens, done/error
  GET  /api/charts/{id}/response.json -> the raw Agent API response (phase 1)
  GET  /api/charts/{id}/csv        -> download the date,close CSV
  GET  /api/charts/{id}            -> plain JSON status snapshot

Execution runs in a worker thread and writes incremental state onto the job, so
the SSE stream merely *tails* that state — reconnects never re-run the work.

CSV parsing and shared-file helpers are reused from the CLI module
(``finance_chart_sandbox``); only the API call differs (SDK here, raw HTTP there).
"""

import json
import os
import re
import sys
import threading
import time
import uuid
from pathlib import Path
from typing import Dict, List, Optional

from fastapi import FastAPI, HTTPException
from fastapi.responses import PlainTextResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from perplexity import APIError, Perplexity

# Reuse the CLI module's tool-agnostic helpers (CSV extraction, parsing, usage).
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import finance_chart_sandbox as fcs  # noqa: E402

app = FastAPI(title="Finance Chart (Sandbox) UI")

# In-memory job store. Fine for a single-process demo; swap for Redis/DB to
# scale out. Guarded by a lock because a worker thread mutates it.
JOBS: Dict[str, dict] = {}
_LOCK = threading.Lock()

DEFAULT_MODEL = "openai/gpt-5.5"
POLL_TIMEOUT = 300
META_START = "===META_START==="
META_END = "===META_END==="

# Phase 1: data-gathering AND charting inside the sandbox.
DATA_PROMPT = f"""You answer natural-language questions about a stock's recent
price history by producing a CSV file and a line-chart PNG.

You have the `sandbox` tool — an isolated Python environment with
`urllib`/`requests`, pandas, matplotlib, the standard library, and a writable
working directory.

The files `{fcs.CSV_NAME}` and `{fcs.PNG_NAME}` ARE the deliverable; they are
returned to the caller as downloadable artifacts. The task is complete only
once both exist. Do this:
1. Read the question and determine the stock TICKER (resolve a company name to
   its symbol, e.g. "apple" -> AAPL) and the PERIOD as a Yahoo range token
   (1mo, 3mo, 6mo, 1y, 2y, 5y; default 6mo).
2. Fetch the daily closing prices from Yahoo Finance's v8 chart JSON at exactly
   `https://query1.finance.yahoo.com/v8/finance/chart/<TICKER>?range=<RANGE>&interval=1d`
   with a browser `User-Agent` header (e.g. `Mozilla/5.0`). Parse
   `result.timestamp` (epoch) with `result.indicators.quote[0].close`; drop
   null closes. If it is rate-limited, fall back to the Stooq daily CSV
   (`https://stooq.com/q/d/l/?s=<ticker>.us&i=d`). Never fabricate prices.
3. Write `{fcs.CSV_NAME}`: header `date,close`; ascending; dates YYYY-MM-DD;
   close a plain number.
4. Render a line chart and save `{fcs.PNG_NAME}` (~10x5in @150dpi; line #1f77b4
   with a light fill; dashed grid; x-label "Date", y-label "Close (USD)";
   title "<TICKER> closing price — <label>"; concise date ticks).
5. Then print to stdout ONLY this routing block (not the prices):
   {META_START}
   ticker: <TICKER>
   label: <short human label, e.g. last 6 months>
   {META_END}"""

# Phase 2: the streamed natural-language analysis.
ANSWER_PROMPT = """You are a concise financial analyst. Given a user's question
and a stock's daily closing prices, answer in 3-5 sentences: the overall trend,
the start and end levels, notable highs/lows or moves, and the net change over
the period. Use only the data provided. Do not give investment advice. Write
plain prose — no markdown, asterisks, headings, or bullet points."""


class ChartRequest(BaseModel):
    query: str = Field(..., min_length=3, max_length=400)
    attempts: int = Field(3, ge=1, le=8)
    max_steps: int = Field(25, ge=5, le=60)


# ---------------------------------------------------------------------------
# Job state helpers (all mutate under the lock)
# ---------------------------------------------------------------------------
def _set(job_id: str, **fields) -> None:
    with _LOCK:
        JOBS[job_id].update(fields)


def _push(job_id: str, event: dict) -> None:
    with _LOCK:
        JOBS[job_id]["events"].append(event)


def _append_answer(job_id: str, text: str) -> None:
    with _LOCK:
        JOBS[job_id]["answer"] += text


def _to_dict(response) -> dict:
    """SDK response object -> plain dict (silence harmless serializer warnings)."""
    try:
        return response.model_dump(warnings=False)
    except TypeError:  # older pydantic
        return response.model_dump()


# ---------------------------------------------------------------------------
# SDK calls
# ---------------------------------------------------------------------------
def _make_client() -> Perplexity:
    kw = {}
    if os.environ.get("PERPLEXITY_BASE_URL"):
        kw["base_url"] = os.environ["PERPLEXITY_BASE_URL"]
    return Perplexity(api_key=fcs.resolve_api_key(), **kw)


def _run_sandbox(client, query, model, max_steps, poll_timeout) -> dict:
    """Phase 1: one background SDK call (create + poll by id), returned as a dict."""
    response = client.responses.create(
        model=model,
        instructions=DATA_PROMPT,
        input=query,
        tools=[{"type": "sandbox"}],
        background=True,
        # Generous headroom: the sandbox spends output tokens writing the code
        # that fetches the data and writes the file; a tight cap can starve the
        # final write step.
        max_output_tokens=8192,
        max_steps=max_steps,
    )
    deadline = time.time() + poll_timeout
    while response.status in ("queued", "in_progress"):
        if time.time() > deadline:
            raise TimeoutError("Timed out waiting for the sandbox response.")
        time.sleep(3)
        response = client.responses.retrieve(response.id)
    return _to_dict(response)


def _sandbox_stdout(response: dict) -> str:
    """Concatenate stdout from every sandbox execution result (for the META block)."""
    chunks: List[str] = []
    for item in response.get("output", []) or []:
        if item.get("type") != "sandbox_results":
            continue
        for res in item.get("results", []) or []:
            if res.get("stdout"):
                chunks.append(res["stdout"])
    return "\n".join(chunks)


def _parse_meta(response: dict) -> Dict[str, str]:
    block = re.search(
        re.escape(META_START) + r"\s*(.*?)\s*" + re.escape(META_END),
        _sandbox_stdout(response), re.S,
    )
    meta: Dict[str, str] = {}
    if block:
        for line in block.group(1).splitlines():
            if ":" in line:
                key, val = line.split(":", 1)
                meta[key.strip().lower()] = val.strip()
    return meta


def _base_url() -> str:
    return os.environ.get("PERPLEXITY_BASE_URL", fcs.DEFAULT_BASE_URL)


def _fetch_data(client, query, attempts, max_steps, poll_timeout, on_attempt):
    """Retry phase 1 until the sandbox shares a usable CSV file and a chart PNG.

    Returns ``(dates, closes, csv_text, png_bytes, meta, response)``. The CSV is
    parsed here both to validate it and to feed the phase-2 analysis; the PNG is
    the chart the sandbox rendered.
    """
    base_url, key = _base_url(), fcs.resolve_api_key()
    for attempt in range(1, attempts + 1):
        on_attempt(attempt, attempts, None)
        try:
            response = _run_sandbox(client, query, DEFAULT_MODEL, max_steps, poll_timeout)
        except (APIError, TimeoutError) as err:
            on_attempt(attempt, attempts, str(err))
            continue
        if response.get("status") == "failed":
            on_attempt(attempt, attempts, f"request failed: {response.get('error')}")
            continue
        files = fcs.shared_files(response, base_url, key)
        csv_file, png_file = fcs.pick_file(files, ".csv"), fcs.pick_file(files, ".png")
        if not csv_file or not png_file:
            have = ", ".join(f.get("filename", "?") for f in files) or "none"
            on_attempt(attempt, attempts, f"missing CSV/PNG (got: {have})")
            continue
        try:
            candidate = fcs._download(base_url, key, csv_file["url"]).decode("utf-8", "replace")
            png_bytes = fcs._download(base_url, key, png_file["url"])
            dates, closes = fcs.parse_csv(candidate)
        except (OSError, RuntimeError, TimeoutError) as err:
            on_attempt(attempt, attempts, f"unusable CSV/PNG: {err}")
            continue
        return dates, closes, candidate, png_bytes, _parse_meta(response), response
    raise RuntimeError(
        f"Could not answer the query from the sandbox after {attempts} "
        "attempt(s). Data fetching is best-effort (sources rate-limit); "
        "try rephrasing or asking again."
    )


def _stream_answer(client, query, ticker, label, dates, closes, on_text) -> None:
    """Phase 2: stream a short analysis of the series, token by token."""
    rows = list(zip(dates, closes))
    if len(rows) > 250:  # keep the prompt small for long ranges
        step = len(rows) // 250 + 1
        rows = rows[::step] + [rows[-1]]
    series = "\n".join(f"{d:%Y-%m-%d},{c}" for d, c in rows)
    user = (
        f"Question: {query}\n"
        f"Ticker: {ticker or 'unknown'} ({label})\n"
        f"Daily closing prices (date,close):\n{series}\n\nWrite the analysis."
    )
    stream = client.responses.create(
        model=DEFAULT_MODEL,
        instructions=ANSWER_PROMPT,
        input=user,
        stream=True,
        max_output_tokens=400,
    )
    for event in stream:
        if getattr(event, "type", None) == "response.output_text.delta":
            delta = getattr(event, "delta", None)
            if delta:
                on_text(delta)


# ---------------------------------------------------------------------------
# Worker
# ---------------------------------------------------------------------------
def _run_job(job_id: str) -> None:
    with _LOCK:
        job = dict(JOBS[job_id])
    query, attempts, max_steps = job["query"], job["attempts"], job["max_steps"]

    try:
        client = _make_client()
    except RuntimeError as err:
        _push(job_id, {"kind": "progress", "message": str(err)})
        _set(job_id, status="error", error=str(err))
        return

    def on_attempt(n: int, total: int, note: Optional[str]) -> None:
        msg = (f"Attempt {n}/{total}: the sandbox is fetching prices…"
               if note is None else f"Attempt {n}/{total}: {note}")
        _set(job_id, status="running")
        _push(job_id, {"kind": "progress", "message": msg})

    try:
        dates, closes, csv_text, png_bytes, meta, response = _fetch_data(
            client, query, attempts, max_steps, poll_timeout=POLL_TIMEOUT,
            on_attempt=on_attempt,
        )
    except (RuntimeError, TimeoutError) as err:
        _set(job_id, status="error", error=str(err))
        return

    ticker = meta.get("ticker", "").upper() or None
    label = meta.get("label") or "price history"
    title = f"{ticker} · closing price · {label}" if ticker else query
    cost = fcs.total_cost(response)
    result = {
        "title": title,
        "ticker": ticker,
        "label": label,
        "points": len(dates),
        "first_date": dates[0].strftime("%Y-%m-%d"),
        "last_date": dates[-1].strftime("%Y-%m-%d"),
        # The chart is the PNG the sandbox rendered, served at /chart.png.
        "chart_url": f"/api/charts/{job_id}/chart.png",
        "sandbox_invocations": fcs.sandbox_invocations(response),
        "cost": ({"total": cost[0], "currency": cost[1]} if cost else None),
    }
    filename = ((ticker or "chart") + "_" + re.sub(r"[^\w]+", "-", label)).strip("-")
    _set(job_id, csv=csv_text, png=png_bytes, filename=filename,
         response=response, result=result)
    _push(job_id, {"kind": "chart", "result": result})

    # Phase 2: stream the natural-language analysis.
    _push(job_id, {"kind": "answer_start"})
    try:
        _stream_answer(client, query, ticker, label, dates, closes,
                       on_text=lambda t: _append_answer(job_id, t))
    except APIError as err:
        _append_answer(job_id, f"\n\n_(analysis unavailable: {err})_")

    _set(job_id, status="done")


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------
def _sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"


@app.post("/api/charts")
def create_chart(req: ChartRequest) -> dict:
    job_id = uuid.uuid4().hex
    with _LOCK:
        JOBS[job_id] = {
            "status": "queued", "query": req.query.strip(),
            "attempts": req.attempts, "max_steps": req.max_steps,
            "events": [], "answer": "", "result": None, "csv": None,
            "png": None, "filename": "chart", "response": None, "error": None,
        }
    threading.Thread(target=_run_job, args=(job_id,), daemon=True).start()
    return {"job_id": job_id, "status": "queued"}


@app.get("/api/charts/{job_id}/events")
def stream_events(job_id: str) -> StreamingResponse:
    with _LOCK:
        if job_id not in JOBS:
            raise HTTPException(status_code=404, detail="Unknown job_id")

    def gen():
        ev_idx, ans_pos = 0, 0
        yield ":ok\n\n"  # open the stream
        while True:
            with _LOCK:
                job = JOBS.get(job_id)
                new_events = job["events"][ev_idx:]
                ev_idx = len(job["events"])
                ans_delta = job["answer"][ans_pos:]
                ans_pos = len(job["answer"])
                status, error = job["status"], job["error"]
                has_json = job["response"] is not None
            for e in new_events:
                if e["kind"] == "progress":
                    yield _sse("progress", {"message": e["message"]})
                elif e["kind"] == "chart":
                    yield _sse("chart", e["result"])
                elif e["kind"] == "answer_start":
                    yield _sse("answer_start", {})
            if ans_delta:
                yield _sse("token", {"text": ans_delta})
            if status == "error":
                yield _sse("error", {"message": error or "Run failed."})
                return
            if status == "done":
                yield _sse("done", {"has_json": has_json})
                return
            time.sleep(0.12)

    return StreamingResponse(
        gen(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.get("/api/charts/{job_id}")
def get_status(job_id: str) -> dict:
    with _LOCK:
        job = JOBS.get(job_id)
        if job is None:
            raise HTTPException(status_code=404, detail="Unknown job_id")
        return {"status": job["status"], "result": job["result"],
                "answer": job["answer"], "error": job["error"],
                "has_json": job["response"] is not None}


@app.get("/api/charts/{job_id}/response.json")
def get_response_json(job_id: str) -> Response:
    with _LOCK:
        job = JOBS.get(job_id)
        response = job["response"] if job else None
    if response is None:
        raise HTTPException(status_code=404, detail="No response stored yet")
    return Response(json.dumps(response, indent=2), media_type="application/json")


@app.get("/api/charts/{job_id}/csv")
def get_csv(job_id: str) -> PlainTextResponse:
    with _LOCK:
        job = JOBS.get(job_id)
    if job is None or not job.get("csv"):
        raise HTTPException(status_code=404, detail="No CSV for this job")
    return PlainTextResponse(
        job["csv"],
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{job["filename"]}.csv"'},
    )


@app.get("/api/charts/{job_id}/chart.png")
def get_chart_png(job_id: str) -> Response:
    """The chart PNG the sandbox rendered (downloaded in phase 1)."""
    with _LOCK:
        job = JOBS.get(job_id)
        png = job["png"] if job else None
    if not png:
        raise HTTPException(status_code=404, detail="No chart for this job")
    return Response(png, media_type="image/png")


# Serve the static frontend at the root. Mounted last so /api/* takes priority.
_STATIC = Path(__file__).resolve().parent / "static"
app.mount("/", StaticFiles(directory=str(_STATIC), html=True), name="static")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=int(os.environ.get("PORT", "8000")))
