// Runs the built assets/worker.js in Node with a fake `self` and checks that a core error raised while merging is
// tagged with the failing file's id (details.fileId), which the UI uses to name the file on the error card.
import { readFileSync } from 'node:fs';
import vm from 'node:vm';
const fx = new URL('./out/fx/', import.meta.url);
const read = (n) => new Uint8Array(readFileSync(new URL(n, fx)));
const out = [];
const self = { postMessage: (m) => out.push(m) };
vm.runInNewContext(readFileSync(new URL('../../assets/worker.js', import.meta.url), 'utf8'), { self, console, TextEncoder, TextDecoder, Uint8Array, ArrayBuffer, DataView, Promise, setTimeout, clearTimeout, queueMicrotask, structuredClone, CompressionStream: globalThis.CompressionStream, DecompressionStream: globalThis.DecompressionStream, Blob, Response });
const ask = async (m) => { out.length = 0; await self.onmessage({ data: { id: 1, ...m } }); for (let i = 0; i < 50 && !out.some((x) => x.result || x.error); i++) await new Promise((r) => setTimeout(r, 20)); return out.find((x) => x.result || x.error); };
let fail = 0;
const check = (name, cond, info) => { console.log((cond ? 'PASS ' : 'FAIL ') + name + (cond ? '' : ' ' + JSON.stringify(info))); if (!cond) fail++; };
const files = { 7: read('contract.pdf'), 9: read('bank-statement.pdf') };
let r = await ask({ op: 'build', files, pages: [{ f: 7, i: 0, r: 0 }, { f: 9, i: 0, r: 0 }] });
check('merge: error of 2nd file tagged fileId 9', r.error && r.error.code === 'PDF_ENCRYPTED' && r.error.details.fileId === 9, r.error);
r = await ask({ op: 'build', files, pages: [{ f: 7, i: 0, r: 0 }, { f: 9, i: 0, r: 90 }] });
check('rotated file: error tagged fileId 9', r.error && r.error.code === 'PDF_ENCRYPTED' && r.error.details.fileId === 9, r.error);
r = await ask({ op: 'build', files, pages: [{ f: 7, i: 1, r: 0 }, { f: 7, i: 0, r: 90 }] });
check('merge of good file still works', r.result && r.result.length > 100, r.error);
process.exit(fail ? 1 : 0);
