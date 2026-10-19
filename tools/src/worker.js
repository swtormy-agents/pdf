// Processing worker (classic, same-origin, CSP worker-src 'self'). Runs @local-pdf-tools/core off the main thread so
// the page stays responsive and «Cancel» can terminate the job. Messages in: {id, op, ...}; out: {id, progress} |
// {id, result} | {id, error:{code, details}}. No network: the worker only receives File/bytes and posts bytes back.
import { pdfInfo, merge, split, organize, imagesToPdf, PdfToolError, LIMITS } from '@local-pdf-tools/core';
import { PDFDocument, degrees } from 'pdf-lib';

const bytesOf = async (f) => (f instanceof Uint8Array ? f : new Uint8Array(await f.arrayBuffer()));

// User rotation for Images to PDF: applied to our own imagesToPdf() output (never to user PDFs). Loaded with
// updateMetadata:false, so no Info dictionary (Producer/Creator/dates) is added, like the core's own outputs.
async function rotatePages(bytes, rot) {
  const doc = await PDFDocument.load(bytes, { updateMetadata: false });
  doc.getPages().forEach((p, i) => { if (rot[i]) p.setRotation(degrees((p.getRotation().angle + rot[i]) % 360)); });
  return doc.save({ addDefaultPage: false });
}

// Merge / organize from the on-screen page list [{f: fileId, i: 0-based page, r: degrees}].
// 1) A file with rotated pages is rotated once with organize() (all pages, in place order).
// 2) The list becomes runs of consecutive pages of one file -> merge() items {bytes, pages:[indexes]}.
// merge() counts every item against MAX_FILES and MAX_TOTAL_BYTES, so runs are merged in chunks that stay within both
// limits and the chunks are merged again (each intermediate is smaller than its sources).
// Errors carry details.fileId (the page's file) so the UI can name the file, e.g. TOO_LARGE reason 'decompressed'.
async function tag(id, fn) {
  try { return await fn(); } catch (e) {
    if (e instanceof PdfToolError && id !== undefined) e.details = { ...(e.details || {}), fileId: id };
    throw e;
  }
}
async function mergeTagged(items) {
  try { return await merge(items.map(({ bytes, pages }) => (pages ? { bytes, pages } : { bytes }))); } catch (e) {
    const it = e instanceof PdfToolError && e.details && Number.isInteger(e.details.index) ? items[e.details.index] : null;
    if (it && it.f !== undefined) e.details = { ...e.details, fileId: it.f };
    throw e;
  }
}

async function build(files, pages, post) {
  const ids = [...new Set(pages.map((p) => p.f))];
  const src = {};
  let step = 0;
  for (const id of ids) {
    const b = await bytesOf(files[id]);
    const rot = {};
    pages.forEach((p) => { if (p.f === id && p.r % 360) rot[p.i] = p.r % 360; });
    if (Object.keys(rot).length) {
      src[id] = await tag(id, async () => {
        const { pages: n } = await pdfInfo(b);
        return organize(b, { order: [...Array(n).keys()], rotate: rot });
      });
    } else src[id] = b;
    post({ progress: { n: Math.round(((++step) / ids.length) * pages.length * 0.3), total: pages.length, pct: Math.round((step / ids.length) * 30) } });
  }
  const runs = [];
  for (const p of pages) {
    const last = runs[runs.length - 1];
    if (last && last.f === p.f) last.pages.push(p.i); else runs.push({ f: p.f, pages: [p.i] });
  }
  let items = runs.map((r) => ({ bytes: src[r.f], pages: r.pages, f: r.f }));
  let done = 0;
  while (true) {
    const chunks = [];
    let cur = [], bytes = 0;
    for (const it of items) {
      if (cur.length && (cur.length >= LIMITS.MAX_FILES || bytes + it.bytes.length > LIMITS.MAX_TOTAL_BYTES)) { chunks.push(cur); cur = []; bytes = 0; }
      cur.push(it); bytes += it.bytes.length;
    }
    chunks.push(cur);
    if (chunks.length === 1) {
      const out = await mergeTagged(chunks[0]);
      post({ progress: { n: pages.length, total: pages.length, pct: 100 } });
      return out;
    }
    const next = [];
    for (const c of chunks) {
      next.push({ bytes: await mergeTagged(c) });
      done += c.reduce((s, it) => s + (it.pages ? it.pages.length : 0), 0);
      post({ progress: { n: Math.min(done, pages.length), total: pages.length, pct: 30 + Math.round((Math.min(done, pages.length) / pages.length) * 60) } });
    }
    items = next;
  }
}

self.onmessage = async (ev) => {
  const m = ev.data;
  const post = (o) => self.postMessage({ id: m.id, ...o });
  try {
    let result;
    if (m.op === 'info') {
      result = await pdfInfo(await bytesOf(m.file));
      post({ result });
      return;
    } else if (m.op === 'build') {
      result = await build(m.files, m.pages, post);
    } else if (m.op === 'split') {
      // m.groups: [[from, to], ...] 1-based inclusive (ranges / every N); m.order: 0-based pages for «Extract pages».
      const b = await bytesOf(m.file);
      if (m.order) {
        result = await organize(b, { order: m.order });
      } else {
        post({ progress: { n: 0, total: m.total, pct: 5 } });
        // the core checks the split limits (per part, all parts, number of parts) before copying any page
        const parts = await split(b, m.groups);
        result = parts.map((x) => ({ pages: x.pages, bytes: x.bytes }));
      }
      post({ progress: { n: m.total, total: m.total, pct: 100 } });
    } else if (m.op === 'images') {
      const list = [];
      for (let k = 0; k < m.images.length; k++) {
        list.push({ bytes: await bytesOf(m.images[k]) });
        post({ progress: { n: k + 1, total: m.images.length, pct: Math.round(((k + 1) / m.images.length) * 40) } });
      }
      // page size select: 'fit' (default) | 'a4' -> core pageSize 'fit' | 'A4' (portrait, image centred); no margin in the UI
      result = await imagesToPdf(list, { pageSize: m.size === 'a4' ? 'A4' : 'fit' });
      post({ progress: { n: m.images.length, total: m.images.length, pct: 80 } });
      if (m.rot.some((r) => r)) result = await rotatePages(result, m.rot);
      post({ progress: { n: m.images.length, total: m.images.length, pct: 100 } });
    } else throw new Error('unknown op');
    const tr = Array.isArray(result) ? result.map((x) => x.bytes.buffer) : [result.buffer];
    self.postMessage({ id: m.id, result }, tr);
  } catch (e) {
    post({ error: e instanceof PdfToolError ? { code: e.code, details: e.details || {} } : { code: 'FAILED', details: {} } });
  }
};
