// Tests for scripts/validate-mdx.js using Node's built-in test runner.
// Run with: node --test scripts/__tests__/validate-mdx.test.mjs
import { test } from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import os from 'node:os';

import { validateMDX } from '../validate-mdx.js';

function makeTempDir() {
  return fs.mkdtempSync(path.join(os.tmpdir(), 'mdx-validate-'));
}

const VALID_MDX = `---
title: Hello
---

# Heading

Some prose with a [link](https://example.com).
`;

const INVALID_MDX = `---
title: Broken
---

<UnclosedTag>
`;

test('validates a directory of well-formed MDX files', async () => {
  const dir = makeTempDir();
  fs.writeFileSync(path.join(dir, 'a.mdx'), VALID_MDX);
  fs.writeFileSync(path.join(dir, 'b.mdx'), VALID_MDX);

  const count = await validateMDX({
    pattern: `${dir}/*.mdx`,
    log: () => {},
  });
  assert.equal(count, 2);
});

test('throws with the offending file path when MDX cannot compile', async () => {
  const dir = makeTempDir();
  fs.writeFileSync(path.join(dir, 'good.mdx'), VALID_MDX);
  const badPath = path.join(dir, 'bad.mdx');
  fs.writeFileSync(badPath, INVALID_MDX);

  await assert.rejects(
    validateMDX({ pattern: `${dir}/*.mdx`, log: () => {} }),
    (error) => {
      assert.match(error.message, /MDX compilation failed/);
      assert.equal(error.file, badPath);
      return true;
    }
  );
});

test('returns 0 when the glob matches no files (no spurious failure)', async () => {
  const dir = makeTempDir();
  const count = await validateMDX({
    pattern: `${dir}/*.mdx`,
    log: () => {},
  });
  assert.equal(count, 0);
});
