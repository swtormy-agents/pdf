// Writes test inputs from the core's fixture generator (@local-pdf-tools/core/fixtures) to tools/test/out/fx/.
import { writeFileSync, mkdirSync } from 'node:fs';
import { PDFDocument } from 'pdf-lib';
import { plainPdf, encryptedPdf, evilPdf, exifJpeg, plainPng, metadataPng, jpegWithSize, corruptBytes } from '@local-pdf-tools/core/fixtures';
const d = new URL('./out/fx/', import.meta.url).pathname; mkdirSync(d, { recursive: true });
const w = (n, b) => writeFileSync(d + n, b);
// page widths identify file and page in the output: contract 101-103, invoice 201-202, scan 301-303
async function sized(base, n) { const d = await PDFDocument.create(); for (let k = 1; k <= n; k++) d.addPage([base + k, 400]); return d.save(); }
w('contract.pdf', await sized(100, 3)); w('invoice.pdf', await sized(200, 2)); w('scan.pdf', await sized(300, 3)); w('long24.pdf', await plainPdf(24));
w('bank-statement.pdf', encryptedPdf()); w('evil.pdf', await evilPdf()); w('broken.pdf', corruptBytes(2000));
w('photo-gps.jpg', exifJpeg()); w('meta.png', metadataPng()); w('plain.png', plainPng(40, 30)); w('huge.jpg', jpegWithSize(10000, 6000));
// 50 MP header limit: exactly 50,000,000 px is added; 50,000,001 px (3561x14041), a JPEG whose
// second (progressive) SOF after the first scan is huge, and a PNG over the limit / with a second IHDR are not
w('edge-50mp.jpg', jpegWithSize(10000, 5000)); w('over-50mp.jpg', jpegWithSize(3561, 14041));
{ const seg = (m, p) => [0xff, m, (p.length + 2) >> 8, (p.length + 2) & 255, ...p];
  const sof = (m, wd, h) => seg(m, [8, h >> 8, h & 255, wd >> 8, wd & 255, 1, 1, 0x11, 0]);
  const sos = [...seg(0xda, [1, 1, 0, 0, 63, 0]), 0x12, 0x34];
  w('sneaky-sof.jpg', Uint8Array.from([0xff, 0xd8, ...sof(0xc0, 16, 16), ...sos, ...sof(0xc2, 20000, 20000), ...sos, 0xff, 0xd9]));
  const be = (v) => [v >>> 24, (v >> 16) & 255, (v >> 8) & 255, v & 255];
  const ch = (t, dt) => [...be(dt.length), ...Buffer.from(t, 'latin1'), ...dt, 0, 0, 0, 0];
  const ihdr = (wd, h) => ch('IHDR', [...be(wd), ...be(h), 8, 2, 0, 0, 0]);
  const png = (...c) => Uint8Array.from([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a, ...c.flat(), ...ch('IEND', [])]);
  w('over-50mp.png', png(ihdr(3561, 14041))); w('dup-ihdr.png', png(ihdr(8, 8), ihdr(20000, 20000))); }
// 6000 small pages for the split limits (1000 per part, 5000 total, 50 parts)
{ const d6 = await PDFDocument.create(); for (let k = 0; k < 6000; k++) d6.addPage([200, 200]); w('long6000.pdf', await d6.save()); }
// 60 pages: 'every 1 page' gives 60 parts (> 50 -> err_split_parts)
w('long60.pdf', await plainPdf(60));
// a HEIC file (ISO-BMFF 'ftypheic' header only): not JPG/PNG -> UNSUPPORTED_IMAGE with the HEIC -> JPG link
w('IMG_0001.heic', new Uint8Array([0, 0, 0, 24, 0x66, 0x74, 0x79, 0x70, 0x68, 0x65, 0x69, 0x63, 0, 0, 0, 0, 0x6d, 0x69, 0x66, 0x31, 0x68, 0x65, 0x69, 0x63]));
// a JPEG signature with a corrupt marker: sniffed as JPEG, header parse fails -> IMAGE_INVALID (err_image_broken_fix)
w('broken.jpg', new Uint8Array([0xff, 0xd8, 0xff, 0xe0, 0x00, 0x10, 0x4a, 0x46, 0x49, 0x46, 0x00, 0x01, 0x01, 0x00, 0x00, 0x01, 0x00, 0x01, 0x00, 0x00, 0x12, 0x34]));
// 51 small PDFs for the TOO_MANY_FILES plural (1 file not added)
for (let k = 1; k <= 51; k++) w(`m${String(k).padStart(2, '0')}.pdf`, await sized(500, 1));
w('notes.txt', new TextEncoder().encode('hello'));
console.log('fixtures in', d);

// QA M1 (398ade0): page image XObject behind a 40-hop indirect reference chain (core fails closed: PDF_INVALID refchain
// during assembly, not at open)
{
  const objs = { 1: '<< /Type /Catalog /Pages 2 0 R >>', 2: '<< /Type /Pages /Kids [3 0 R] /Count 1 >>',
    3: '<< /Type /Page /Parent 2 0 R /MediaBox [0 0 200 200] /Resources << /XObject << /Im0 10 0 R >> >> /Contents 4 0 R >>',
    4: '<< /Length 31 >>\nstream\nq 100 0 0 50 10 10 cm /Im0 Do Q\nendstream' };
  for (let k = 10; k < 50; k++) objs[k] = `${k + 1} 0 R`;
  objs[50] = '<< /Type /XObject /Subtype /Image /Width 2 /Height 2 /ColorSpace /DeviceGray /BitsPerComponent 8 /Length 4 >>\nstream\n\x00\x40\x80\xff\nendstream';
  let out = '%PDF-1.7\n'; const off = {};
  for (const n of Object.keys(objs).map(Number)) { off[n] = Buffer.byteLength(out, 'latin1'); out += `${n} 0 obj\n${objs[n]}\nendobj\n`; }
  const x = Buffer.byteLength(out, 'latin1'); out += 'xref\n0 51\n';
  for (let n = 0; n <= 50; n++) out += off[n] !== undefined ? String(off[n]).padStart(10, '0') + ' 00000 n \n' : '0000000000 65535 f \n';
  out += `trailer\n<< /Size 51 /Root 1 0 R >>\nstartxref\n${x}\n%%EOF\n`;
  w('refchain40.pdf', Buffer.from(out, 'latin1'));
}
