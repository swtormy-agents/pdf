// Builds the CSS twice and verifies the outputs are byte-identical (sha256),
// that build/app.css matches, and that it has no external url() or @import.
import { execFileSync } from 'node:child_process';
import { createHash } from 'node:crypto';
import { readFileSync, mkdtempSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';

const tools = join(dirname(fileURLToPath(import.meta.url)), '..');
const bin = join(tools, 'node_modules', '.bin', 'tailwindcss');
const tmp = mkdtempSync(join(tmpdir(), 'css-check-'));
const sha = (f) => createHash('sha256').update(readFileSync(f)).digest('hex');
let ok = true;
try {
  const outs = [1, 2].map((n) => {
    const out = join(tmp, `app${n}.css`);
    execFileSync(bin, ['-i', 'css/input.css', '-o', out, '--minify'], { cwd: tools, stdio: 'pipe' });
    const h = sha(out);
    console.log(`run ${n}: sha256 ${h}  ${readFileSync(out).length} bytes`);
    return { out, h };
  });
  if (outs[0].h !== outs[1].h) { console.error('FAIL: runs differ'); ok = false; }
  const css = readFileSync(outs[0].out, 'utf8');
  if (/url\(\s*['"]?(?:https?:)?\/\//i.test(css)) { console.error('FAIL: external url()'); ok = false; }
  if (/@import/i.test(css)) { console.error('FAIL: @import in output'); ok = false; }
  try {
    const committed = sha(join(tools, '..', 'build', 'app.css'));
    console.log(`build/app.css: sha256 ${committed}`);
    if (committed !== outs[0].h) { console.error('FAIL: build/app.css is stale; run npm --prefix tools run build:css'); ok = false; }
  } catch { console.error('FAIL: build/app.css missing'); ok = false; }
} finally { rmSync(tmp, { recursive: true, force: true }); }
console.log(ok ? 'OK: byte-identical, no external url()/@import' : 'CHECK FAILED');
process.exit(ok ? 0 : 1);
