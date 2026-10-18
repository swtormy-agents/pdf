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
w('notes.txt', new TextEncoder().encode('hello'));
console.log('fixtures in', d);
