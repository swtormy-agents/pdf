// Verifies the licences page against the final bundles: every npm package that esbuild puts into assets/app.js or
// assets/worker.js (from the metafile), plus pdfjs-dist (copied verbatim to assets/vendor/), must be listed in the
// licenses.html table of every language, and nothing else may be listed. Full licence texts live under licenses/*.txt
// (linked from the page; not inlined in HTML).
import { build } from 'esbuild';
import { readFileSync, readdirSync } from 'node:fs';
import { join, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';

const root = join(dirname(fileURLToPath(import.meta.url)), '..', '..');
const tools = join(root, 'tools');
const pkgs = new Set(['pdfjs-dist']);
for (const [entry, format] of [['src/app.js', 'esm'], ['src/worker.js', 'iife']]) {
  const r = await build({ entryPoints: [entry], bundle: true, minify: true, write: false, metafile: true, format, absWorkingDir: tools, logLevel: 'error', outdir: 'x' });
  for (const out of Object.values(r.metafile.outputs)) for (const inp of Object.keys(out.inputs)) {
    const m = inp.match(/node_modules\/((?:@[^/]+\/)?[^/]+)\//);
    if (m) pkgs.add(m[1]);
  }
}
const embedded = ['base64-arraybuffer'];
const css = ['tailwindcss', 'daisyui'];
const txtBodies = readdirSync(join(root, 'licenses'))
  .filter((f) => f.endsWith('.txt'))
  .map((f) => readFileSync(join(root, 'licenses', f), 'utf8'))
  .join('\n');
const needles = ['Niklas von Hertzen', 'Jean-loup Gailly and Mark Adler', 'Copyright 2012 Mozilla Foundation', 'Glyph & Cog', 'Devon Govett', 'Adobe Systems', 'Apache License', 'Christopher Brown', 'Tailwind Labs', 'Pouya Saadeghi'];
let ok = true;
for (const p of ['licenses.html', 'ru/licenses.html', 'zh/licenses.html']) {
  const s = readFileSync(join(root, p), 'utf8');
  const listed = new Set([...s.matchAll(/<tr><td translate="no">([^<]+)<\/td>/g)].map((m) => m[1].replace(' (pdf.js)', '')));
  const want = new Set([...pkgs, ...embedded, ...css, '@local-pdf-tools/core']);
  for (const x of want) if (!listed.has(x)) { console.error(`FAIL ${p}: bundled ${x} not listed`); ok = false; }
  for (const x of listed) if (!want.has(x)) { console.error(`FAIL ${p}: ${x} listed but not bundled`); ok = false; }
  if (!s.includes('licenses/') || s.includes('<pre class="lic"')) {
    console.error(`FAIL ${p}: expected .txt links, not inlined <pre> licence texts`); ok = false;
  }
}
for (const needle of needles) {
  if (!txtBodies.includes(needle.replace('&amp;', '&')) && !txtBodies.includes(needle)) {
    console.error(`FAIL licenses/*.txt: notice "${needle}" missing`); ok = false;
  }
}
console.log('bundled packages:', [...pkgs].sort().join(', '));
console.log(ok ? 'OK: licences page matches the bundles' : 'CHECK FAILED');
process.exit(ok ? 0 : 1);
