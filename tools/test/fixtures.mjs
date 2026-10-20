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
