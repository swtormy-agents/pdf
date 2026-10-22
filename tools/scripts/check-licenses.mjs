// Verifies the licences page against the final bundles: every npm package that esbuild puts into assets/app.js or
// assets/worker.js (from the metafile), plus pdfjs-dist (copied verbatim to assets/vendor/), must be listed in the
// licenses.html table of every language, and nothing else may be listed. Also checks that the embedded notices from
// THIRD-PARTY.md (base64-arraybuffer, pako zlib, pdf.js/XPDF decoders, pdfkit, font metrics) are on the page.
import { build } from 'esbuild';
import { readFileSync } from 'node:fs';
import { join, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';

const tools = join(dirname(fileURLToPath(import.meta.url)), '..');
const pkgs = new Set(['pdfjs-dist']);
for (const [entry, format] of [['src/app.js', 'esm'], ['src/worker.js', 'iife']]) {
  const r = await build({ entryPoints: [entry], bundle: true, minify: true, write: false, metafile: true, format, absWorkingDir: tools, logLevel: 'error', outdir: 'x' });
  for (const out of Object.values(r.metafile.outputs)) for (const inp of Object.keys(out.inputs)) {
    const m = inp.match(/node_modules\/((?:@[^/]+\/)?[^/]+)\//);
    if (m) pkgs.add(m[1]);
  }
}
const embedded = ['base64-arraybuffer']; // inlined inside pdf-lib / standard-fonts, no own package
const css = ['tailwindcss', 'daisyui']; // compiled into build/app.css
let ok = true;
for (const p of ['licenses.html', 'ru/licenses.html', 'zh/licenses.html']) {
  const s = readFileSync(join(tools, '..', p), 'utf8');
  const listed = new Set([...s.matchAll(/<tr><td translate="no">([^<]+)<\/td>/g)].map((m) => m[1].replace(' (pdf.js)', '')));
  const want = new Set([...pkgs, ...embedded, ...css]);
  for (const x of want) if (!listed.has(x)) { console.error(`FAIL ${p}: bundled ${x} not listed`); ok = false; }
  for (const x of listed) if (!want.has(x)) { console.error(`FAIL ${p}: ${x} listed but not bundled`); ok = false; }
  for (const needle of ['Niklas von Hertzen', 'Jean-loup Gailly and Mark Adler', 'Copyright 2012 Mozilla Foundation', 'Glyph &amp; Cog, LLC', 'Devon Govett', 'Adobe Systems Incorporated', 'Apache License', 'Christopher Brown', 'Tailwind Labs, Inc.', 'Pouya Saadeghi']) {
    if (!s.includes(needle)) { console.error(`FAIL ${p}: notice "${needle}" missing`); ok = false; }
  }
}
console.log('bundled packages:', [...pkgs].sort().join(', '));
console.log(ok ? 'OK: licences page matches the bundles' : 'CHECK FAILED');
process.exit(ok ? 0 : 1);
