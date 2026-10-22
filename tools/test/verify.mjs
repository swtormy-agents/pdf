// node verify.mjs <file.pdf|file.zip> -> JSON facts about the output (pages: width/height/rotation; metadata; markers)
import { readFileSync } from 'node:fs';
import { PDFDocument, PDFName } from 'pdf-lib';
import { gpsRationalBytes, EVIL_MARKER } from '@local-pdf-tools/core/fixtures';
const find = (b, n) => Buffer.from(b).indexOf(Buffer.from(n)) !== -1;
async function pdf(b) {
  const d = await PDFDocument.load(b, { updateMetadata: false });
  const info = d.context.trailerInfo.Info;
  return {
    pages: d.getPages().map((p) => ({ w: Math.round(p.getWidth()), h: Math.round(p.getHeight()), rot: p.getRotation().angle })),
    info: !!info, xmp: !!d.catalog.get(PDFName.of('Metadata')), producer: find(b, 'Producer'),
    exif: find(b, 'Exif') || find(b, Buffer.from(gpsRationalBytes(false))) || find(b, Buffer.from(gpsRationalBytes(true))),
    evil: find(b, EVIL_MARKER), bytes: b.length,
  };
}
function unzip(b) {
  const out = []; let i = 0; const v = new DataView(b.buffer, b.byteOffset, b.byteLength);
  while (i + 30 <= b.length && v.getUint32(i, true) === 0x04034b50) {
    const n = v.getUint32(i + 18, true), nl = v.getUint16(i + 26, true), el = v.getUint16(i + 28, true);
    const name = Buffer.from(b.subarray(i + 30, i + 30 + nl)).toString(); const data = b.subarray(i + 30 + nl + el, i + 30 + nl + el + n);
    out.push({ name, data }); i += 30 + nl + el + n;
  }
  return out;
}
const f = process.argv[2], b = new Uint8Array(readFileSync(f));
if (f.endsWith('.zip')) { const r = []; for (const e of unzip(b)) r.push({ name: e.name, ...(await pdf(e.data)) }); console.log(JSON.stringify({ zip: r })); }
else console.log(JSON.stringify(await pdf(b)));
