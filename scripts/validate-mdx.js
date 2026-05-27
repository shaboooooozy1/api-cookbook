import fs from 'fs';
import { pathToFileURL } from 'url';
import { compile } from '@mdx-js/mdx';
import { glob } from 'glob';

/**
 * Validate every MDX file matched by a glob pattern.
 *
 * Returns the number of files validated. Throws on the first compilation
 * failure so callers (CLI or tests) can decide how to surface the error.
 *
 * @param {object} [options]
 * @param {string} [options.pattern] - Glob pattern (default: 'docs/&#42;&#42;/&#42;.mdx').
 * @param {(message: string) => void} [options.log] - Logger (default: console.log).
 * @returns {Promise<number>}
 */
export async function validateMDX({ pattern = 'docs/**/*.mdx', log = console.log } = {}) {
  const mdxFiles = await glob(pattern);

  for (const file of mdxFiles) {
    log(`Validating: ${file}`);
    const content = fs.readFileSync(file, 'utf8');
    try {
      await compile(content, { jsx: true });
      log(`✅ ${file} - Valid MDX`);
    } catch (error) {
      const wrapped = new Error(`MDX compilation failed for ${file}: ${error.message}`);
      wrapped.cause = error;
      wrapped.file = file;
      throw wrapped;
    }
  }

  log(`\n🎉 All ${mdxFiles.length} MDX files are valid!`);
  return mdxFiles.length;
}

// Run as a script when invoked directly (`node scripts/validate-mdx.js`).
const invokedAsScript =
  import.meta.url === pathToFileURL(process.argv[1] ?? '').href;

if (invokedAsScript) {
  validateMDX().catch((error) => {
    console.error(`❌ ${error.file ?? 'Validation'}: ${error.message}`);
    process.exit(1);
  });
}
