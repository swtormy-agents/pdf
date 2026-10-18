// Builds the browser JS (no CDN, all same-origin):
//   src/app.js    -> ../assets/app.js            (ESM, page UI; core helpers for selection-time checks)
//   src/worker.js -> ../assets/worker.js         (classic worker: @local-pdf-tools/core + pdf-lib)
//   pdfjs-dist build/pdf.min.mjs, pdf.worker.min.mjs -> ../assets/vendor/pdf.min.js, pdf.worker.min.js (copied verbatim)
// --check: builds into a temp dir twice, verifies byte-identical output and that the committed files are current.
import { build } from 'esbuild';
import { createHash } from 'node:crypto';
import { readFileSync, writeFileSync, mkdirSync, mkdtempSync, rmSync, copyFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';

const tools = join(dirname(fileURLToPath(import.meta.url)), '..');
const FILES = ['app.js', 'worker.js', 'vendor/pdf.min.js', 'vendor/pdf.worker.min.js'];
async function run(out) {
  mkdirSync(join(out, 'vendor'), { recursive: true });
  const common = { bundle: true, minify: true, legalComments: 'eof', target: ['es2022'], logLevel: 'error', absWorkingDir: tools, charset: 'utf8' };
  await build({ ...common, entryPoints: ['src/app.js'], outfile: join(out, 'app.js'), format: 'esm', external: ['./vendor/pdf.min.js'] });
  await build({ ...common, entryPoints: ['src/worker.js'], outfile: join(out, 'worker.js'), format: 'iife' });
  copyFileSync(join(tools, 'node_modules/pdfjs-dist/build/pdf.min.mjs'), join(out, 'vendor/pdf.min.js'));
  copyFileSync(join(tools, 'node_modules/pdfjs-dist/build/pdf.worker.min.mjs'), join(out, 'vendor/pdf.worker.min.js'));
}
const sha = (f) => createHash('sha256').update(readFileSync(f)).digest('hex');
const assets = join(tools, '..', 'assets');
if (process.argv.includes('--check')) {
  const t = mkdtempSync(join(tmpdir(), 'js-check-'));
  let ok = true;
  try {
    await run(join(t, 'a')); await run(join(t, 'b'));
    for (const f of FILES) {
      const a = sha(join(t, 'a', f)), b = sha(join(t, 'b', f));
      let c = ''; try { c = sha(join(assets, f)); } catch {}
      console.log(`${f}: ${a}`);
      if (a !== b) { console.error(`FAIL: ${f} differs between runs`); ok = false; }
      if (a !== c) { console.error(`FAIL: assets/${f} is stale; run npm --prefix tools run build:js`); ok = false; }
      const s = readFileSync(join(t, 'a', f), 'utf8');
      if (/https?:\/\/(?:cdn|unpkg|jsdelivr|cdnjs)/i.test(s)) { console.error(`FAIL: CDN URL in ${f}`); ok = false; }
    }
  } finally { rmSync(t, { recursive: true, force: true }); }
  console.log(ok ? 'OK: JS byte-identical and current' : 'CHECK FAILED');
  process.exit(ok ? 0 : 1);
} else { await run(assets); console.log('built', FILES.join(', ')); }
