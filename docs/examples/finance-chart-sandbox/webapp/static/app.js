"use strict";

const form = document.getElementById("chart-form");
const queryInput = document.getElementById("query");
const submitBtn = document.getElementById("submit");
const statusEl = document.getElementById("status");
const statusText = document.getElementById("status-text");
const errorEl = document.getElementById("error");
const resultEl = document.getElementById("result");
const resultTitle = document.getElementById("result-title");
const statsEl = document.getElementById("stats");
const downloadBtn = document.getElementById("download");
const viewJsonLink = document.getElementById("view-json");
const answerWrap = document.getElementById("answer-wrap");
const answerEl = document.getElementById("answer");

const chartImg = document.getElementById("chart");
let es = null;

function show(el) { el.classList.remove("hidden"); }
function hide(el) { el.classList.add("hidden"); }

function setBusy(busy) {
  submitBtn.disabled = busy;
  submitBtn.textContent = busy ? "Working…" : "Ask";
}

// Example chips fill the query box.
document.querySelectorAll(".chip").forEach((chip) => {
  chip.addEventListener("click", () => {
    queryInput.value = chip.textContent;
    queryInput.focus();
  });
});

function renderChart(r) {
  hide(statusEl);
  resultTitle.textContent = r.title;

  // The chart is the PNG matplotlib rendered inside the sandbox.
  chartImg.src = r.chart_url;
  chartImg.alt = r.title;

  const cost = r.cost ? `${r.cost.total.toFixed(4)} ${r.cost.currency}` : "—";
  statsEl.innerHTML = "";
  for (const [k, v] of [
    ["Ticker", r.ticker || "—"],
    ["Data points", r.points],
    ["Range", `${r.first_date} → ${r.last_date}`],
    ["Sandbox calls", r.sandbox_invocations],
    ["Cost", cost],
  ]) {
    const div = document.createElement("div");
    div.innerHTML = `<dt>${k}</dt><dd>${v}</dd>`;
    statsEl.appendChild(div);
  }
  show(resultEl);
}

function onError(message) {
  if (es) { es.close(); es = null; }
  hide(statusEl);
  setBusy(false);
  errorEl.textContent = message;
  show(errorEl);
}

function startStream(jobId) {
  viewJsonLink.href = `/api/charts/${jobId}/response.json`;
  downloadBtn.onclick = () => { window.location.href = `/api/charts/${jobId}/csv`; };

  es = new EventSource(`/api/charts/${jobId}/events`);

  es.addEventListener("progress", (e) => {
    statusText.textContent = JSON.parse(e.data).message;
  });

  es.addEventListener("chart", (e) => {
    renderChart(JSON.parse(e.data));
  });

  es.addEventListener("answer_start", () => {
    answerEl.textContent = "";
    answerEl.classList.add("streaming");
    show(answerWrap);
  });

  es.addEventListener("token", (e) => {
    answerEl.textContent += JSON.parse(e.data).text;
  });

  es.addEventListener("done", () => {
    answerEl.classList.remove("streaming");
    setBusy(false);
    es.close(); es = null;
  });

  es.addEventListener("error", (e) => {
    let msg = "The stream failed.";
    try { msg = JSON.parse(e.data).message || msg; } catch (_) {}
    onError(msg);
  });

  // Network-level failure (not a server "error" event).
  es.onerror = () => {
    if (es && es.readyState === EventSource.CLOSED) {
      onError("Connection to the server was lost.");
    }
  };
}

form.addEventListener("submit", async (e) => {
  e.preventDefault();
  hide(errorEl);
  hide(resultEl);
  hide(answerWrap);
  setBusy(true);
  show(statusEl);
  statusText.textContent = "Submitting…";

  try {
    const res = await fetch("/api/charts", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ query: queryInput.value.trim() }),
    });
    if (!res.ok) {
      const detail = await res.json().catch(() => ({}));
      throw new Error(detail.detail || `Submit failed (HTTP ${res.status})`);
    }
    const { job_id } = await res.json();
    startStream(job_id);
  } catch (err) {
    onError(err.message || String(err));
  }
});
