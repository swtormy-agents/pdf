// Local PDF Tools: page UI (ESM, same-origin, no network). Strings come from <script type="application/json" id="i18n">
// (Nathan Price's /workspace/i18n/pdf-tool JSON, copied by tools/gen.py). PDF writing runs in assets/worker.js
// (@local-pdf-tools/core + pdf-lib); page previews use pdf.js (assets/vendor/, own worker, loaded on first PDF).
// Limits are checked here at file selection, before parsing (core LIMITS, one source of truth with the MCP).
import { LIMITS } from '../node_modules/@local-pdf-tools/core/src/limits.js';
import { parsePageRanges } from '../node_modules/@local-pdf-tools/core/src/ranges.js';
import { imagePixels } from '../node_modules/@local-pdf-tools/core/src/images.js';
import { zip } from './zip.js';

const $ = (id) => document.getElementById(id);
const body = document.body;
const app = $('app');
if (app) init();

function init() {
  const S = JSON.parse($('i18n').textContent);
  const LANG = body.dataset.lang;
  const MODE = app.dataset.mode; // merge | split | organize | images
  const PR = new Intl.PluralRules(LANG);
  const NB = '\u00a0';
  const assetUrl = (k) => new URL(body.dataset[k], location.href).href;

  // ---------- strings ----------
  function t(key, v = {}, count) {
    let s = S[key];
    if (s && typeof s === 'object') {
      const n = count !== undefined ? count : v.n;
      s = s[PR.select(n)] ?? s.other ?? s.many ?? Object.values(s)[0];
    }
    if (typeof s !== 'string') return key;
    return s.replace(/\{(\w+)\}/g, (m, k) => (k in v ? String(v[k]) : m));
  }
  // ru: thin-space groups from 10 000 (1000 stays as is); en: 1,000; zh: no separator (Nathan's rules).
  function num(n) {
    if (LANG === 'ru') return n >= 10000 ? String(n).replace(/\B(?=(\d{3})+(?!\d))/g, '\u2009') : String(n);
    if (LANG === 'en') return new Intl.NumberFormat('en').format(n);
    return String(n);
  }
  function size(b) {
    const mb = b / (1024 * 1024);
    let s, u;
    if (mb < 1) { s = String(Math.max(1, Math.round(b / 1024))); u = t('unit_kb'); }
    else { s = mb < 10 ? mb.toFixed(1) : String(Math.round(mb)); u = t('unit_mb'); }
    if (LANG === 'ru') s = s.replace('.', ',');
    return s + NB + u;
  }
  function shortName(name, max = 42) {
    if (name.length <= max) return name;
    const k = Math.floor((max - 1) / 2);
    return name.slice(0, k) + '…' + name.slice(name.length - (max - 1 - k));
  }
  const el = (tag, cls, text) => { const e = document.createElement(tag); if (cls) e.className = cls; if (text !== undefined) e.textContent = text; return e; };
  const SVGNS = 'http://www.w3.org/2000/svg';
  function icon(paths, cls = '') {
    const s = document.createElementNS(SVGNS, 'svg');
    s.setAttribute('viewBox', '0 0 24 24'); s.setAttribute('aria-hidden', 'true'); s.setAttribute('focusable', 'false');
    s.setAttribute('fill', 'none'); s.setAttribute('stroke', 'currentColor'); s.setAttribute('stroke-width', '2');
    s.setAttribute('stroke-linecap', 'round'); s.setAttribute('stroke-linejoin', 'round');
    if (cls) s.setAttribute('class', cls);
    for (const d of paths) { const p = document.createElementNS(SVGNS, 'path'); p.setAttribute('d', d); s.appendChild(p); }
    return s;
  }
  const IC = {
    left: ['M19 12H5', 'M11 6l-6 6 6 6'], right: ['M5 12h14', 'M13 6l6 6-6 6'],
    up: ['M12 19V5', 'M6 11l6-6 6 6'], down: ['M12 5v14', 'M6 13l6 6 6-6'],
    rot: ['M20 12a8 8 0 1 1-2.34-5.66', 'M20 4v5h-5'], del: ['M4 7h16', 'M10 11v6M14 11v6', 'M6 7l1 13h10l1-13', 'M9 7V4h6v3'],
    err: ['M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18z', 'M12 8v5M12 16v.5'], info: ['M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18z', 'M12 11v5M12 8v.5'],
    x: ['M6 6l12 12M18 6L6 18'], chk: ['M5 12.5l4.5 4.5L19 7'],
  };

  // ---------- elements ----------
  const input = $('files'), drop = $('drop'), errs = $('errs'), work = $('work'), list = $('pages'), go = $('go');
  const proc = $('proc'), done = $('done'), live = $('live'), toast = $('toast'), confirmDlg = $('confirm');
  const counts = $('counts');
  // <600px the error stack is fixed at the bottom: publish its height as --errs-h (0 when empty or static) so CSS can reserve room
  const setErrsH = () => {
    const h = getComputedStyle(errs).position === 'fixed' && errs.children.length ? Math.ceil(errs.getBoundingClientRect().height) + 12 : 0;
    document.documentElement.style.setProperty('--errs-h', h + 'px');
  };
  if (window.ResizeObserver) new ResizeObserver(setErrsH).observe(errs);
  matchMedia('(max-width: 599px)').addEventListener('change', setErrsH);
  // Firefox ignores scroll-padding when focus() scrolls; make sure a focused control outside the stack ends above it (WCAG 2.4.11)
  document.addEventListener('focusin', (ev) => {
    const x = ev.target; if (!errs.children.length || errs.contains(x) || x.closest('.toast') || getComputedStyle(errs).position !== 'fixed') return;
    requestAnimationFrame(() => { const r = x.getBoundingClientRect(), top = errs.getBoundingClientRect().top - 12;
      if (r.top < 0) scrollBy(0, r.top - 12); else if (r.bottom > top) scrollBy(0, Math.min(r.bottom - top, r.top)); });
  });
  const hero = document.querySelector('.hero');

  // ---------- state ----------
  let files = []; // {id, file, name, size, pages, kind}
  let pages = []; // {k, f, i, r}
  let seq = 1, busy = false, picked = null, extractSel = new Set();
  const byId = (id) => files.find((x) => x.id === id);
  const nodes = new Map(); // page key -> li
  const thumbs = new Map(); // page key -> blob URL
  let resultUrl = null;

  // ---------- worker ----------
  let worker = null, jobs = new Map(), jobSeq = 1;
  function getWorker() {
    if (worker) return worker;
    try { worker = new Worker(assetUrl('worker')); }
    catch (e) { throw { code: navigator.onLine ? 'FAILED' : 'OFFLINE' }; }
    worker.onmessage = (ev) => {
      const m = ev.data, j = jobs.get(m.id);
      if (!j) return;
      if (m.progress) { j.onProgress && j.onProgress(m.progress); return; }
      jobs.delete(m.id);
      if (m.error) j.reject(m.error); else j.resolve(m.result);
    };
    worker.onerror = () => {
      const code = navigator.onLine ? 'FAILED' : 'OFFLINE';
      if (code === 'OFFLINE') { worker.terminate(); worker = null; }
      for (const j of jobs.values()) j.reject({ code }); jobs.clear();
    };
    return worker;
  }
  function run(msg, onProgress, transfer = []) {
    return new Promise((resolve, reject) => {
      const id = jobSeq++;
      jobs.set(id, { resolve, reject, onProgress });
      try { getWorker().postMessage({ id, ...msg }, transfer); }
      catch (e) { jobs.delete(id); reject(e && e.code ? e : { code: navigator.onLine ? 'FAILED' : 'OFFLINE' }); }
    });
  }
  function killWorker() {
    if (worker) worker.terminate();
    worker = null;
    for (const j of jobs.values()) j.reject({ code: 'CANCELLED' });
    jobs.clear();
  }

  // ---------- pdf.js previews ----------
  let pdfjsP = null;
  function pdfjs() {
    if (!pdfjsP) {
      pdfjsP = import(assetUrl('pdfjs')).then((lib) => { lib.GlobalWorkerOptions.workerSrc = assetUrl('pdfjsWorker'); return lib; })
        .catch((e) => { pdfjsP = null; throw navigator.onLine ? e : { code: 'OFFLINE' }; });
    }
    return pdfjsP;
  }
  const docs = new Map(); // file id -> Promise<PDFDocumentProxy>
  function pdfDoc(f) {
    if (!docs.has(f.id)) {
      docs.set(f.id, (async () => {
        const lib = await pdfjs();
        const data = new Uint8Array(await f.file.arrayBuffer());
        // Only same-origin pdf.js assets; no font/cMap/wasm URLs are given, so pdf.js never fetches anything.
        return lib.getDocument({ data, isOffscreenCanvasSupported: false, stopAtErrors: false }).promise;
      })());
    }
    return docs.get(f.id);
  }
  const io = 'IntersectionObserver' in window ? new IntersectionObserver((ents) => {
    for (const e of ents) if (e.isIntersecting) { io.unobserve(e.target); renderThumb(e.target.dataset.k); }
  }, { rootMargin: '300px' }) : null;
  let thumbQueue = Promise.resolve();
  function renderThumb(k) {
    const p = pages.find((x) => x.k === k);
    if (!p || thumbs.has(k)) return;
    const f = byId(p.f);
    if (f.kind === 'image') { setThumb(k, URL.createObjectURL(f.file)); return; }
    thumbQueue = thumbQueue.then(async () => {
      if (!pages.some((x) => x.k === k)) return;
      try {
        const doc = await pdfDoc(f);
        const page = await doc.getPage(p.i + 1);
        const vp0 = page.getViewport({ scale: 1 });
        const scale = Math.min(2, (220 * Math.min(2, window.devicePixelRatio || 1)) / Math.max(vp0.width, vp0.height * 0.75));
        const vp = page.getViewport({ scale });
        const c = document.createElement('canvas');
        c.width = Math.ceil(vp.width); c.height = Math.ceil(vp.height);
        const ctx = c.getContext('2d');
        ctx.fillStyle = '#fff'; ctx.fillRect(0, 0, c.width, c.height);
        await page.render({ canvasContext: ctx, canvas: c, viewport: vp }).promise;
        const blob = await new Promise((r) => c.toBlob(r, 'image/png'));
        if (blob && pages.some((x) => x.k === k)) setThumb(k, URL.createObjectURL(blob));
        page.cleanup();
      } catch (e) {
        const li = nodes.get(k); if (li) li.querySelector('.th').classList.remove('sk');
        if (e && e.code === 'OFFLINE') showOffline();
      }
    });
  }
  function setThumb(k, url) {
    thumbs.set(k, url);
    const li = nodes.get(k);
    if (!li) return;
    const th = li.querySelector('.th');
    const img = el('img'); img.alt = ''; img.decoding = 'async'; img.src = url;
    img.addEventListener('load', () => th.classList.remove('sk'), { once: true });
    th.appendChild(img);
  }

  // ---------- errors ----------
  function card(title, fix, opts = {}) {
    const c = el('div', 'ecard' + (opts.note ? ' note' : ''));
    c.appendChild(icon(opts.note ? IC.info : IC.err));
    const b = el('div', 'eb');
    const tt = el('p', 'et', title); if (opts.full) tt.title = opts.full;
    const ef = el('p', 'ef'); if (Array.isArray(fix)) ef.append(...fix); else ef.textContent = fix;
    b.append(tt, ef);
    const x = el('button', 'ib'); x.type = 'button'; x.setAttribute('aria-label', t('aria_dismiss')); x.appendChild(icon(IC.x));
    x.addEventListener('click', () => {
      const next = c.nextElementSibling || c.previousElementSibling;
      c.remove();
      const f = next && next.querySelector('.ib');
      (f || go || input).focus?.();
    });
    c.append(b, x);
    if (opts.code) c.dataset.code = opts.code;
    errs.appendChild(c);
  }
  function heicFix() {
    const tp = $('heic-strings').content, s = (k) => tp.querySelector(`[data-k="${k}"]`).textContent;
    const [a, b = ''] = s('fix').split('{link}');
    const l = el('a', 'link link-primary', s('text')); l.href = body.dataset.heicHref;
    return [a, l, b];
  }
  const isImageName = (f) => /^image\//.test(f.type) || /\.(jpe?g|png|heic|heif|webp|gif|avif|bmp|tiff?)$/i.test(f.name);
  function errFor(code, f, extra = {}) {
    const name = f ? shortName(f.name) : '';
    const full = f ? f.name : undefined;
    switch (code) {
      case 'PDF_ENCRYPTED': return card(t('err_encrypted', { file: name }), t('err_encrypted_fix'), { full, code });
      case 'PDF_INVALID': return card(t('err_invalid', { file: name }), t(f && isImageName(f) ? 'err_invalid_fix_image' : 'err_invalid_fix'), { full, code });
      // .heic/.heif on jpg-to-pdf: the fix links the converter's HEIC -> JPG page (gen.py data-heic-href + <template id=heic-strings>, Nathan's err_heic_* keys)
      case 'UNSUPPORTED_IMAGE': return card(t('err_image_invalid', { file: name }), f && /\.hei[cf]$/i.test(f.name) && body.dataset.heicHref && $('heic-strings') ? heicFix() : t('err_image_invalid_fix'), { full, code });
      case 'IMAGE_INVALID': return card(t('err_image_invalid', { file: name }), t('err_image_broken_fix'), { full, code });
      // core TOO_LARGE with details.reason 'decompressed': the file unpacks past the core's cap (Nathan's keys)
      case 'TOO_LARGE': return extra.reason === 'decompressed' && f ? card(t('err_too_large_unpacked', { file: name }), t('err_too_large_unpacked_fix'), { full, code })
        : extra.total ? card(t('err_total_large'), t('err_total_large_fix'), { code })
        : card(t('err_too_large', { file: name }), t('err_too_large_fix'), { full, code });
      case 'TOO_MANY_PAGES': return card(t('err_too_many_pages'), t('err_too_many_pages_fix', { n: num(extra.n) }, extra.n), { code });
      case 'TOO_MANY_FILES': return card(t('err_too_many_files'), t(MODE === 'images' ? 'err_too_many_files_fix_images' : 'err_too_many_files_fix', { n: num(extra.n) }, extra.n), { code });
      case 'IMAGE_TOO_LARGE': return card(t('err_image_too_large', { file: name }), t('err_image_too_large_fix'), { full, code });
      // split limits (approved 18.10): one part > 1000 pages, all parts > 5000 pages, > 50 parts
      case 'SPLIT_PART_PAGES': return card(t('err_split_part_pages'), t('err_split_part_pages_fix'), { code });
      case 'SPLIT_TOTAL_PAGES': return card(t('err_split_total_pages'), t('err_split_total_pages_fix'), { code });
      case 'SPLIT_PARTS': return card(t('err_split_parts'), t('err_split_parts_fix'), { code });
      case 'PAGE_RANGE': return card(t('err_range'), t('err_range_fix', { n: num(extra.n || 0) }, extra.n || 0), { code });
      case 'OFFLINE': return card(t('err_offline'), t('err_offline_fix'), { code });
      default: return card(t('err_failed'), t('err_failed_fix'), { code: 'FAILED' });
    }
  }
  function showOffline() {
    errs.querySelectorAll('[data-code=OFFLINE]').forEach((c) => c.remove());
    errFor('OFFLINE');
    const ib = errs.lastElementChild && errs.lastElementChild.querySelector('.ib');
    if (ib) ib.focus();
  }
  function needsWorker() { return !worker; }
  function offlineNow() { return !navigator.onLine && needsWorker(); }

  // ---------- adding files ----------
  const isPdfMode = MODE !== 'images';
  function sniff(b) {
    if (b[0] === 0xff && b[1] === 0xd8 && b[2] === 0xff) return 'jpeg';
    if (b[0] === 0x89 && b[1] === 0x50 && b[2] === 0x4e && b[3] === 0x47) return 'png';
    return null;
  }
  async function addFiles(fl) {
    if (busy || !fl.length) return;
    if (offlineNow()) { showOffline(); return; }
    let incoming = [...fl];
    if (MODE === 'split') {
      if (incoming.length > 1) card(t('err_split_one'), t('err_split_one_fix', { file: shortName(incoming[0].name) }), { note: true, full: incoming[0].name, code: 'SPLIT_ONE' });
      incoming = incoming.slice(0, 1);
    }
    // 1) limits at selection, before anything is read or parsed
    const keep = MODE === 'split' ? [] : files.slice();
    const room = LIMITS.MAX_FILES - keep.length;
    if (incoming.length > room) {
      errFor('TOO_MANY_FILES', null, { n: incoming.length - Math.max(0, room) });
      incoming = incoming.slice(0, Math.max(0, room));
    }
    let total = keep.reduce((s, f) => s + f.size, 0), totalShown = false;
    const ok = [];
    for (const f of incoming) {
      if (f.size > LIMITS.MAX_FILE_BYTES) { errFor('TOO_LARGE', f); continue; }
      if (total + f.size > LIMITS.MAX_TOTAL_BYTES) { if (!totalShown) errFor('TOO_LARGE', f, { total: true }); totalShown = true; continue; }
      total += f.size; ok.push(f);
    }
    if (!ok.length) { render(); return; }
    // 2) open: page count / encryption (core pdfInfo in the worker) or image header
    setBusy(true);
    showProc(t('proc_opening'), null);
    let cancelled = false;
    cancelOpen = () => { cancelled = true; };
    let pageTotal = MODE === 'split' ? 0 : pages.length;
    const added = [];
    for (const f of ok) {
      if (cancelled) break;
      try {
        if (isPdfMode) {
          const { pages: n } = await run({ op: 'info', file: f });
          if (MODE !== 'split' && pageTotal + n > LIMITS.MAX_PAGES) { errFor('TOO_MANY_PAGES', f, { n: pageTotal + n }); continue; }
          pageTotal += n;
          added.push({ id: seq++, file: f, name: f.name, size: f.size, pages: n, kind: 'pdf' });
        } else {
          const b = new Uint8Array(await f.arrayBuffer());
          const kind = sniff(b);
          if (!kind) { errFor('UNSUPPORTED_IMAGE', f); continue; }
          // Header-only pixel count (largest JPEG SOFn/DHP frame, single PNG IHDR), before any decode or thumbnail.
          let dim;
          try { dim = imagePixels(b, kind); } catch { errFor('IMAGE_INVALID', f); continue; }
          if (dim.pixels > LIMITS.MAX_IMAGE_PIXELS) { errFor('IMAGE_TOO_LARGE', f); continue; }
          added.push({ id: seq++, file: f, name: f.name, size: f.size, pages: 1, kind: 'image' });
        }
      } catch (e) {
        if (e && e.code === 'CANCELLED') break;
        if (e && e.code === 'OFFLINE') { showOffline(); hideProc(); setBusy(false); return; }
        errFor(e && e.code, f, { reason: e && e.details && e.details.reason });
      }
    }
    cancelOpen = null;
    hideProc(); setBusy(false);
    if (MODE === 'split' && added.length) resetFiles();
    for (const f of added) {
      files.push(f);
      for (let i = 0; i < f.pages; i++) pages.push({ k: f.id + ':' + i + ':' + seq++, f: f.id, i, r: 0 });
    }
    if (cancelled) announce(t('proc_cancelled'));
    render();
    if (added.length) focusFirstNew(added[0]);
  }
  function focusFirstNew(f) {
    const p = pages.find((x) => x.f === f.id);
    if (MODE === 'split') { const r = document.querySelector('input[name=smode]:checked'); if (r) r.focus(); return; }
    if (p) focusCard(p.k);
  }
  function resetFiles() {
    files = []; pages = []; extractSel = new Set(); picked = null;
    for (const d of docs.values()) d.then((x) => x.destroy()).catch(() => {});
    docs.clear();
    for (const u of thumbs.values()) URL.revokeObjectURL(u);
    thumbs.clear();
    for (const li of nodes.values()) li.remove();
    nodes.clear();
  }

  input.addEventListener('change', () => { const l = [...input.files]; input.value = ''; addFiles(l); });
  // drag & drop of files onto the dropzone (and onto the work area when files are loaded)
  for (const zone of [drop, work]) {
    if (!zone) continue;
    zone.addEventListener('dragover', (e) => { if (busy || !e.dataTransfer || ![...e.dataTransfer.types].includes('Files')) return; e.preventDefault(); drop.classList.add('over'); });
    zone.addEventListener('dragleave', (e) => { if (!zone.contains(e.relatedTarget)) drop.classList.remove('over'); });
    zone.addEventListener('drop', (e) => { if (!e.dataTransfer || !e.dataTransfer.files.length) return; e.preventDefault(); drop.classList.remove('over'); addFiles([...e.dataTransfer.files]); });
  }
  window.addEventListener('dragover', (e) => { if (e.dataTransfer && [...e.dataTransfer.types].includes('Files')) e.preventDefault(); });
  window.addEventListener('drop', (e) => { if (e.dataTransfer && e.dataTransfer.files.length) e.preventDefault(); });
  const addBtn = $('add'); if (addBtn) addBtn.addEventListener('click', () => input.click());
  const replaceBtn = $('replace'); if (replaceBtn) replaceBtn.addEventListener('click', () => input.click());

  // ---------- rendering ----------
  function setBusy(b) {
    busy = b;
    if (b) app.dataset.busy = ''; else delete app.dataset.busy;
    if (drop) drop.setAttribute('aria-disabled', b ? 'true' : 'false');
    input.disabled = b;
  }
  function buildCard(p) {
    const li = el('li', 'pc');
    li.dataset.k = p.k;
    const pick = el('button', 'pick'); pick.type = 'button'; pick.tabIndex = -1;
    const th = el('span', 'th sk');
    const no = el('span', 'no');
    const chk = el('span', 'chk'); chk.appendChild(icon(IC.chk));
    pick.append(th, no, chk);
    const lb = el('p', 'lb'); const lb2 = el('p', 'lb2');
    const ctl = el('div', 'ctl');
    const mk = (cls, ic, act) => { const b = el('button', 'ib ' + cls); b.type = 'button'; b.dataset.act = act; b.appendChild(icon(ic)); return b; };
    ctl.append(mk('mv-h', IC.left, 'left'), mk('mv-v', IC.up, 'up'), mk('mv-h', IC.right, 'right'), mk('mv-v', IC.down, 'down'), mk('rot', IC.rot, 'rot'), mk('del', IC.del, 'del'));
    li.append(pick, lb, lb2, ctl);
    if (thumbs.has(p.k)) { const img = el('img'); img.alt = ''; img.src = thumbs.get(p.k); th.classList.remove('sk'); th.appendChild(img); }
    else if (io) io.observe(li); else renderThumb(p.k);
    nodes.set(p.k, li);
    return li;
  }
  function render() {
    const active = document.activeElement;
    const has = pages.length > 0;
    work.hidden = !has;
    if (drop) drop.hidden = has;
    // keep DOM order = state order (moving nodes, not rebuilding, so thumbnails and focus survive)
    for (const [k, li] of nodes) if (!pages.some((p) => p.k === k)) { li.remove(); nodes.delete(k); const u = thumbs.get(k); if (u) { URL.revokeObjectURL(u); thumbs.delete(k); } }
    const showGrid = MODE !== 'split' || splitMode() === 'extract';
    list.hidden = !showGrid;
    if (showGrid) {
      pages.forEach((p, idx) => {
        const li = nodes.get(p.k) || buildCard(p);
        if (list.children[idx] !== li) list.insertBefore(li, list.children[idx] || null);
        label(li, p, idx);
      });
      if (!pages.some((p) => p.k === roving)) roving = pages[0] && pages[0].k;
      for (const [k, li] of nodes) li.querySelector('.pick').tabIndex = k === roving ? 0 : -1;
    }
    if (active && active !== document.activeElement && document.contains(active)) active.focus({ preventScroll: true });
    // toolbar + primary
    if (counts) {
      const nf = new Set(pages.map((p) => p.f)).size;
      counts.textContent = MODE === 'images' ? t('n_images', { n: num(pages.length) }, pages.length)
        : t('n_files', { n: num(nf) }, nf) + ' · ' + t('n_pages', { n: num(pages.length) }, pages.length);
    }
    if (MODE === 'split') renderSplit();
    else {
      go.textContent = MODE === 'merge' ? t('primary_merge', { n: num(pages.length) }, pages.length) : t(MODE === 'organize' ? 'primary_reorder' : 'primary_images');
      go.disabled = !has || busy;
    }
  }
  function label(li, p, idx) {
    const f = byId(p.f), pos = idx + 1, n = num(pos);
    const name = shortName(f.name, 30);
    li.querySelector('.no').textContent = n;
    const pick = li.querySelector('.pick');
    pick.setAttribute('aria-label', f.kind === 'image' ? f.name : t('aria_page', { n: p.i + 1, file: f.name }));
    if (MODE === 'split') pick.setAttribute('aria-pressed', extractSel.has(p.k) ? 'true' : 'false'); else pick.removeAttribute('aria-pressed');
    li.classList.toggle('sel', MODE === 'split' && extractSel.has(p.k));
    const th = li.querySelector('.th');
    th.classList.remove('r90', 'r180', 'r270');
    if (p.r % 360) th.classList.add('r' + (p.r % 360));
    const lb = li.querySelector('.lb');
    lb.textContent = '';
    if (f.kind === 'image') { const b = el('b', '', name); b.title = f.name; lb.appendChild(b); }
    else {
      const parts = t('page_caption', { n: num(p.i + 1), file: '\u0000' }).split('\u0000');
      const b = el('b', '', name); b.title = f.name;
      lb.append(parts[0], b, parts[1] || '');
    }
    const lb2 = li.querySelector('.lb2');
    lb2.textContent = '';
    const n1 = el('span', 'n1', n + '. ' + name); n1.title = f.name;
    lb2.append(n1, el('span', 'n2', f.kind === 'image' ? '' : t('page_row', { n: num(p.i + 1) })));
    const btn = (a) => li.querySelector(`[data-act=${a}]`);
    const last = idx === pages.length - 1;
    btn('left').disabled = idx === 0; btn('up').disabled = idx === 0;
    btn('right').disabled = last; btn('down').disabled = last;
    const al = { left: 'aria_left', right: 'aria_right', up: 'aria_up', down: 'aria_down', rot: 'aria_rotate', del: 'aria_delete' };
    for (const a in al) { const b = btn(a); b.setAttribute('aria-label', t(al[a], { n: pos })); b.title = t({ left: 'btn_left', right: 'btn_right', up: 'btn_up', down: 'btn_down', rot: 'btn_rotate', del: 'btn_delete' }[a]); }
  }

  // ---------- page actions ----------
  let roving = null;
  function setRoving(k) { roving = k; for (const [kk, li] of nodes) li.querySelector('.pick').tabIndex = kk === k ? 0 : -1; }
  // .pick is display:contents below 600px (no box, cannot take focus): fall back to the card's delete button
  function focusCard(k) {
    const li = nodes.get(k); if (!li) return;
    setRoving(k);
    const pk = li.querySelector('.pick');
    (pk.getClientRects().length ? pk : li.querySelector('[data-act=del]')).focus();
  }
  function focusPage(k) { const li = nodes.get(k); if (li) { setRoving(k); li.querySelector('.pick').focus(); } }
  function move(k, to, announceIt = true) {
    const from = pages.findIndex((p) => p.k === k);
    if (from < 0) return;
    to = Math.max(0, Math.min(pages.length - 1, to));
    if (to === from) return;
    const [p] = pages.splice(from, 1);
    pages.splice(to, 0, p);
    render();
    if (announceIt) announce(t('aria_live_moved', { from: from + 1, to: to + 1, total: pages.length }));
  }
  function rotate(k) {
    const p = pages.find((x) => x.k === k); if (!p) return;
    p.r = (p.r + 90) % 360;
    render();
    announce(t('aria_live_rotated', { n: pages.indexOf(p) + 1, deg: p.r }));
  }
  let undoTimer = null;
  const UNDO_MS = 10000; // founder decision 21.10: 10 s as in the FAQ; paused while Undo has focus or hover (WCAG 2.2.1)
  let undoNow = null; // Undo of the visible toast, for Ctrl/Cmd+Z
  function del(k) {
    const idx = pages.findIndex((p) => p.k === k); if (idx < 0) return;
    const [p] = pages.splice(idx, 1);
    const nextK = (pages[idx] || pages[idx - 1] || {}).k;
    render();
    const u = showUndo(p, idx);
    if (nextK) {
      // focus stays in the grid (serial deleting); the next Tab from here reaches Undo, which sits right after the grid
      setRoving(nextK); const d = nodes.get(nextK).querySelector('[data-act=del]'); d.focus();
      const toUndo = (ev) => { if (ev.key === 'Tab' && !ev.shiftKey && !toast.hidden && u.isConnected) { ev.preventDefault(); u.focus(); } };
      d.addEventListener('keydown', toUndo); d.addEventListener('blur', () => d.removeEventListener('keydown', toUndo), { once: true });
    } else u.focus(); // last page deleted (QA M1): Undo, or the file input once the toast is gone
  }
  function showUndo(p, idx) {
    clearTimeout(undoTimer);
    toast.textContent = '';
    // DOM right after the page grid (or after #work once it is hidden) so it is next in tab order; the toast stays fixed on screen
    (work.hidden ? work : list).after(toast);
    const hold = { focus: false, hover: false };
    const close = () => {
      clearTimeout(undoTimer); undoNow = null; const had = toast.contains(document.activeElement);
      toast.hidden = true; toast.textContent = ''; dropFileIfUnused();
      if (had || document.activeElement === document.body) { if (roving && nodes.get(roving) && !work.hidden) focusCard(roving); else input.focus(); } // focusCard: .pick has no box below 600px (Olivia UX b458eda)
    };
    const arm = () => { clearTimeout(undoTimer); if (!hold.focus && !hold.hover) undoTimer = setTimeout(close, UNDO_MS); };
    const a = el('div', 'alert');
    const msg = el('span', '', t('toast_deleted', { n: idx + 1 }));
    const u = el('button', 'btn btn-sm btn-primary min-h-11', t('undo')); u.type = 'button';
    const undo = () => {
      clearTimeout(undoTimer); undoNow = null; toast.hidden = true; toast.textContent = '';
      const at = Math.min(idx, pages.length);
      pages.splice(at, 0, p);
      render(); focusCard(p.k);
      announce(t('org_restored', { n: at + 1 }));
    };
    u.addEventListener('click', undo); undoNow = undo;
    // the auto-dismiss timer pauses while Undo has focus or hover; Esc closes the toast
    u.addEventListener('focus', () => { hold.focus = true; arm(); });
    u.addEventListener('blur', () => { hold.focus = false; if (!toast.hidden) arm(); });
    u.addEventListener('mouseenter', () => { hold.hover = true; arm(); });
    u.addEventListener('mouseleave', () => { hold.hover = false; if (!toast.hidden) arm(); });
    u.addEventListener('keydown', (ev) => { if (ev.key === 'Escape') { ev.preventDefault(); close(); } });
    a.append(msg, u); toast.appendChild(a); toast.hidden = false;
    announce(t('toast_deleted', { n: idx + 1 }));
    arm();
    return u;
  }
  document.addEventListener('keydown', (ev) => {
    if (!undoNow || toast.hidden || ev.shiftKey || ev.altKey || !(ev.ctrlKey || ev.metaKey) || ev.key.toLowerCase() !== 'z') return;
    if (ev.target.closest && ev.target.closest('input[type=text], input:not([type]), textarea, [contenteditable]')) return;
    ev.preventDefault(); undoNow();
  });
  function dropFileIfUnused() { files = files.filter((f) => pages.some((p) => p.f === f.id)); render(); }

  list.addEventListener('click', (e) => {
    if (suppressClick) { suppressClick = false; e.preventDefault(); return; }
    const b = e.target.closest('button'); if (!b || busy) return;
    const li = b.closest('.pc'); const k = li.dataset.k; const idx = pages.findIndex((p) => p.k === k);
    if (b.classList.contains('pick')) {
      setRoving(k);
      if (MODE === 'split') toggleSel(k);
      return;
    }
    const a = b.dataset.act;
    if (a === 'left' || a === 'up') { move(k, idx - 1); keepFocus(k, a); }
    else if (a === 'right' || a === 'down') { move(k, idx + 1); keepFocus(k, a); }
    else if (a === 'rot') { rotate(k); keepFocus(k, a); }
    else if (a === 'del') del(k);
  });
  function keepFocus(k, a) {
    const li = nodes.get(k); if (!li) return;
    let b = li.querySelector(`[data-act=${a}]`);
    if (b.disabled) b = li.querySelector(`[data-act=${{ left: 'right', up: 'down', right: 'left', down: 'up' }[a]}]`);
    b.focus();
  }
  function toggleSel(k) {
    if (extractSel.has(k)) extractSel.delete(k); else extractSel.add(k);
    render();
  }
  function cols() {
    const lis = [...list.children]; if (lis.length < 2) return 1;
    const top = lis[0].offsetTop; let c = 0;
    for (const li of lis) { if (li.offsetTop !== top) break; c++; }
    return Math.max(1, c);
  }
  list.addEventListener('keydown', (e) => {
    const pick = e.target.closest('.pick'); if (!pick || busy) return;
    const k = pick.closest('.pc').dataset.k, idx = pages.findIndex((p) => p.k === k), c = cols();
    const step = { ArrowLeft: -1, ArrowRight: 1, ArrowUp: -c, ArrowDown: c, Home: -idx, End: pages.length - 1 - idx }[e.key];
    if (step !== undefined) {
      e.preventDefault();
      if (picked === k && MODE !== 'split') { move(k, idx + step); pick.focus(); }
      else { const nk = pages[Math.max(0, Math.min(pages.length - 1, idx + step))].k; focusPage(nk); }
      return;
    }
    if (e.key === ' ' || e.key === 'Enter') {
      e.preventDefault();
      if (MODE === 'split') { toggleSel(k); return; }
      if (picked === k) { picked = null; nodes.get(k).classList.remove('picked'); announce(t('aria_live_dropped', { to: idx + 1 })); }
      else { if (picked) cancelPick(); picked = k; pickedFrom = idx; nodes.get(k).classList.add('picked'); announce(t('aria_live_picked', { n: idx + 1 })); }
      return;
    }
    if (e.key === 'Escape' && picked === k) { e.preventDefault(); cancelPick(); pick.focus(); return; }
    if (MODE === 'split') return;
    if (e.key === 'Delete' || e.key === 'Backspace') { e.preventDefault(); if (picked === k) picked = null; del(k); return; }
    if ((e.key === 'r' || e.key === 'R' || e.key === 'к' || e.key === 'К') && !e.ctrlKey && !e.metaKey && !e.altKey) { e.preventDefault(); rotate(k); pick.focus(); }
  });
  let pickedFrom = 0;
  function cancelPick() {
    const k = picked; picked = null;
    const li = nodes.get(k); if (li) li.classList.remove('picked');
    move(k, pickedFrom, false);
    announce(t('aria_live_cancelled'));
  }
  // leaving the list drops a picked page in place; checked after the event loop turn, because moving a card in the DOM
  // fires focusout (relatedTarget null) before render() puts the focus back on it
  list.addEventListener('focusout', () => {
    setTimeout(() => {
      if (picked && !list.contains(document.activeElement)) { const li = nodes.get(picked); if (li) li.classList.remove('picked'); picked = null; }
    }, 0);
  });

  // pointer drag (pointer events, so mouse, pen and touch work; 8 px threshold; auto-scroll near the edges)
  let drag = null, suppressClick = false;
  list.addEventListener('pointerdown', (e) => {
    const pick = e.target.closest('.pick');
    if (!pick || busy || MODE === 'split' || e.button !== 0 || pages.length < 2) return;
    const li = pick.closest('.pc');
    drag = { li, k: li.dataset.k, x: e.clientX, y: e.clientY, on: false, id: e.pointerId };
  });
  window.addEventListener('pointermove', (e) => {
    if (!drag || e.pointerId !== drag.id) return;
    const dx = e.clientX - drag.x, dy = e.clientY - drag.y;
    if (!drag.on) {
      if (Math.hypot(dx, dy) < 8) return;
      startDrag(e);
    }
    e.preventDefault();
    drag.cx = e.clientX; drag.cy = e.clientY;
    drag.li.style.transform = `translate(${e.clientX - drag.ox}px, ${e.clientY - drag.oy}px)`;
    placeSlot(e.clientX, e.clientY);
  }, { passive: false });
  function startDrag(e) {
    const r = drag.li.getBoundingClientRect();
    drag.on = true;
    drag.slot = el('li', 'pc slot'); drag.slot.setAttribute('aria-hidden', 'true');
    drag.slot.style.height = r.height + 'px';
    drag.li.after(drag.slot);
    drag.ox = e.clientX - r.left; drag.oy = e.clientY - r.top;
    drag.li.classList.add('dragging');
    drag.li.style.width = r.width + 'px'; drag.li.style.height = r.height + 'px';
    drag.li.style.left = '0px'; drag.li.style.top = '0px';
    drag.li.style.position = 'fixed';
    drag.li.style.transform = `translate(${r.left}px, ${r.top}px)`;
    document.documentElement.classList.add('dragging-page');
    try { drag.li.setPointerCapture?.(drag.id); } catch {}
    const tick = () => {
      if (!drag || !drag.on) return;
      const m = 56, y = drag.cy;
      if (y !== undefined) { if (y < m) window.scrollBy(0, -12); else if (y > window.innerHeight - m) window.scrollBy(0, 12); }
      drag.raf = requestAnimationFrame(tick);
    };
    drag.raf = requestAnimationFrame(tick);
  }
  function placeSlot(x, y) {
    const t0 = document.elementFromPoint(x, y);
    const over = t0 && t0.closest && t0.closest('.pc');
    if (!over || over === drag.slot || over === drag.li || !list.contains(over)) return;
    const r = over.getBoundingClientRect();
    const grid = cols() > 1;
    const after = grid ? x > r.left + r.width / 2 : y > r.top + r.height / 2;
    if (after) over.after(drag.slot); else over.before(drag.slot);
  }
  function endDrag(commit) {
    const d = drag; drag = null;
    if (!d || !d.on) return;
    cancelAnimationFrame(d.raf);
    document.documentElement.classList.remove('dragging-page');
    d.li.classList.remove('dragging');
    for (const p of ['position', 'left', 'top', 'width', 'height', 'transform']) d.li.style.removeProperty(p);
    const from = pages.findIndex((p) => p.k === d.k);
    let to = from;
    if (commit) {
      const seqKeys = [...list.children].filter((x) => x !== d.li).map((x) => (x === d.slot ? d.k : x.dataset.k));
      to = seqKeys.indexOf(d.k);
    }
    d.slot.remove();
    suppressClick = true; setTimeout(() => { suppressClick = false; }, 0);
    if (to !== from && to >= 0) move(d.k, to); else render();
    if (commit) announce(t('aria_live_dropped', { to: to + 1 }));
    focusPage(d.k);
  }
  window.addEventListener('pointerup', (e) => { if (drag && e.pointerId === drag.id) { if (drag.on) endDrag(true); else drag = null; } });
  window.addEventListener('pointercancel', (e) => { if (drag && e.pointerId === drag.id) { if (drag.on) endDrag(false); else drag = null; } });
  window.addEventListener('keydown', (e) => { if (drag && drag.on && e.key === 'Escape') endDrag(false); });

  // ---------- clear ----------
  const clearBtn = $('clear');
  if (clearBtn) clearBtn.addEventListener('click', () => { if (confirmDlg.showModal) confirmDlg.showModal(); });
  $('cfno').addEventListener('click', () => confirmDlg.close());
  $('cfok').addEventListener('click', () => { confirmDlg.close(); resetFiles(); render(); input.focus(); });

  // ---------- split ----------
  const rangesIn = $('ranges'), everyIn = $('every'), rerr = $('rerr'), sres = $('sres'), xcount = $('xcount');
  function splitMode() { const r = document.querySelector('input[name=smode]:checked'); return r ? r.value : 'ranges'; }
  // Split limits (approved 18.10), from the core's LIMITS: MAX_PAGES pages per part, MAX_SPLIT_TOTAL_PAGES over all
  // parts, MAX_SPLIT_PARTS parts. Checked here while typing; the core checks them again before copying any page.
  const SPLIT = { part: LIMITS.MAX_PAGES, total: LIMITS.MAX_SPLIT_TOTAL_PAGES, parts: LIMITS.MAX_SPLIT_PARTS };
  // -> 'SPLIT_PARTS' | 'SPLIT_PART_PAGES' | 'SPLIT_TOTAL_PAGES' | null (extract = one part)
  function splitOver(plan) {
    const sizes = plan.order ? [plan.order.length] : plan.groups.map(([a, b]) => b - a + 1);
    if (sizes.length > SPLIT.parts) return 'SPLIT_PARTS';
    if (sizes.some((n) => n > SPLIT.part)) return 'SPLIT_PART_PAGES';
    if (plan.total > SPLIT.total) return 'SPLIT_TOTAL_PAGES';
    return null;
  }
  // core TOO_MANY_PAGES / TOO_MANY_FILES during split -> one of the three split cards, chosen by the core's
  // details.limit ('part' | 'total' | 'parts'); core 047da26 always sets it.
  const SPLIT_ERR = { part: 'SPLIT_PART_PAGES', total: 'SPLIT_TOTAL_PAGES', parts: 'SPLIT_PARTS' };
  function splitErrCode(e) {
    const d = (e && e.details) || {};
    return SPLIT_ERR[d.limit] || null;
  }
  let splitPlan = null, lastErr = '';
  const rlive = $('rlive'); // {groups:[[from,to]...]} | {order:[...]}
  function renderSplit() {
    const f = files[0];
    if (!f) { go.disabled = true; go.textContent = t('primary_split'); return; }
    $('sfname').textContent = f.name;
    $('sfsub').textContent = t('n_pages', { n: num(f.pages) }, f.pages) + ' · ' + size(f.size);
    const m = splitMode();
    let tooMany = false;
    document.querySelectorAll('.optb').forEach((b) => { b.hidden = b.dataset.for !== m; });
    rerr.hidden = true; rerr.textContent = ''; rangesIn.removeAttribute('aria-invalid'); everyIn.removeAttribute('aria-invalid');
    splitPlan = null; sres.textContent = '';
    go.textContent = t(m === 'extract' ? 'primary_extract' : 'primary_split');
    const listOf = (groups) => groups.map(([a, b]) => (a === b ? t('range_item_one', { a: num(a) }) : t('range_item_many', { a: num(a), b: num(b) }))).join(LANG === 'zh-Hans' ? '、' : ', ');
    if (m === 'ranges') {
      const v = rangesIn.value.replace(/\u2014/g, '-');
      if (v.trim()) {
        try {
          // cap = the split total (5000): core 047da26 stops a long or duplicated spec with TOO_MANY_PAGES as soon as the
          // running total passes it -> err_split_total_pages; per-part / parts limits are checked below with the real plan
          const g = parsePageRanges(v, f.pages, SPLIT.total).map((x) => [x[0] + 1, x[x.length - 1] + 1]);
          splitPlan = { groups: g, total: g.reduce((s, [a, b]) => s + b - a + 1, 0) };
          sres.textContent = g.length === 1 ? t('split_result_single', { list: listOf(g) }) : t('split_result_zip', { n: num(g.length), list: listOf(g) }, g.length);
        } catch (e) {
          rangesIn.setAttribute('aria-invalid', 'true'); rerr.hidden = false;
          if (e && e.code === 'TOO_MANY_PAGES') { rerr.dataset.code = 'SPLIT_TOTAL_PAGES'; tooMany = true; rerr.textContent = t('err_split_total_pages') + ' · ' + t('err_split_total_pages_fix'); }
          else rerr.textContent = t('err_range') + ' · ' + t('err_range_fix', { n: num(f.pages) }, f.pages);
        }
      }
    } else if (m === 'every') {
      const k = Number(everyIn.value);
      if (Number.isInteger(k) && k >= 1 && k <= f.pages) {
        const g = []; for (let a = 1; a <= f.pages; a += k) g.push([a, Math.min(f.pages, a + k - 1)]);
        splitPlan = { groups: g, total: f.pages };
        sres.textContent = g.length === 1 ? t('split_result_single', { list: listOf(g) }) : t('every_result', { n: num(g.length), k: num(k) }, k);
      } else if (everyIn.value !== '' || everyIn.validity.badInput) { // 0, a fraction, or text the number field rejects
        everyIn.setAttribute('aria-invalid', 'true'); rerr.hidden = false;
        rerr.textContent = t('err_every_n', { pageCount: num(f.pages) });
      }
      if (rerr.parentElement !== everyIn.closest('.optb')) everyIn.closest('.optb').appendChild(rerr);
    } else {
      const order = pages.filter((p) => extractSel.has(p.k)).map((p) => p.i);
      xcount.textContent = t('extract_count', { n: num(order.length), total: num(f.pages) });
      if (order.length) splitPlan = { order, total: order.length };
    }
    if (m === 'ranges' && rerr.parentElement !== rangesIn.closest('.optb')) rangesIn.closest('.optb').appendChild(rerr);
    const over = splitPlan && splitOver(splitPlan);
    if (over) {
      sres.textContent = ''; splitPlan = null; rerr.hidden = false; rerr.dataset.code = over;
      const k = 'err_' + over.toLowerCase(); rerr.textContent = t(k) + ' · ' + t(k + '_fix');
    } else if (!tooMany) delete rerr.dataset.code;
    rangesIn.setAttribute('aria-describedby', rerr.hidden ? 'rhint' : 'rhint rerr');
    // #rerr moves between blocks and is cleared on every render; #rlive never moves (Olivia 6) and is emptied once the error is resolved (QA L3)
    const emsg = rerr.hidden ? '' : rerr.textContent;
    if (emsg && emsg !== lastErr) rlive.textContent = rlive.textContent === emsg ? emsg + NB : emsg;
    else if (!emsg && rlive.textContent) rlive.textContent = '';
    lastErr = emsg;
    go.disabled = !splitPlan || busy;
  }
  if (MODE === 'split') {
    rangesIn.addEventListener('input', renderSplit);
    everyIn.addEventListener('input', renderSplit);
    document.querySelectorAll('input[name=smode]').forEach((r) => r.addEventListener('change', render));
  }

  // ---------- processing ----------
  const ptitle = $('ptitle'), pbar = $('pbar'), ptext = $('ptext');
  let cancelOpen = null, lastPct = -10;
  function showProc(title, pct) {
    proc.hidden = false; ptitle.textContent = title; lastPct = -10;
    if (pct === null) { pbar.removeAttribute('value'); ptext.textContent = ''; } else setProgress({ pct: 0, n: 0, total: 0 });
  }
  function hideProc() { proc.hidden = true; }
  function setProgress(p) {
    pbar.value = p.pct;
    pbar.setAttribute('aria-valuenow', String(p.pct));
    ptext.textContent = (p.total ? t('proc_page', { n: num(p.n), total: num(p.total) }) + ' · ' : '') + p.pct + '%';
    pbar.setAttribute('aria-valuetext', ptext.textContent);
    if (p.pct - lastPct >= 10) { lastPct = p.pct - (p.pct % 10); announce(t('aria_live_progress', { pct: p.pct })); }
  }
  $('pcancel').addEventListener('click', () => {
    if (cancelOpen) { cancelOpen(); killWorker(); return; }
    killWorker();
  });
  go.addEventListener('click', start);
  async function start() {
    if (busy || go.disabled) return;
    if (offlineNow()) { showOffline(); return; }
    setBusy(true);
    work.hidden = true; errs.querySelectorAll('[data-code=FAILED]').forEach((c) => c.remove());
    const title = { merge: 'proc_merge', organize: 'proc_reorder', images: 'proc_images', split: 'proc_split' }[MODE];
    showProc(t(title), 0);
    proc.querySelector('#pcancel').focus();
    try {
      let out;
      if (MODE === 'split') {
        const f = files[0];
        const r = await run(splitPlan.order ? { op: 'split', file: f.file, order: splitPlan.order, total: splitPlan.total } : { op: 'split', file: f.file, groups: splitPlan.groups, total: splitPlan.total }, setProgress);
        if (splitPlan.order) out = { name: 'pages.pdf', blob: new Blob([r], { type: 'application/pdf' }), pages: splitPlan.order.length, kind: 'extract' };
        else if (r.length === 1) out = { name: 'pages.pdf', blob: new Blob([r[0].bytes], { type: 'application/pdf' }), pages: r[0].pages.length, kind: 'split1' };
        else {
          const pad = String(f.pages).length;
          const entries = r.map((x) => { const a = x.pages[0], b = x.pages[x.pages.length - 1]; const z = (v) => String(v).padStart(pad, '0'); return { name: a === b ? `page-${z(a)}.pdf` : `pages-${z(a)}-${z(b)}.pdf`, data: x.bytes }; });
          out = { name: 'split.zip', blob: new Blob([zip(entries)], { type: 'application/zip' }), files: r.length, pages: splitPlan.total, kind: 'zip' };
        }
      } else if (MODE === 'images') {
        const r = await run({ op: 'images', images: pages.map((p) => byId(p.f).file), rot: pages.map((p) => p.r % 360), size: $('psize').value }, setProgress);
        out = { name: 'images.pdf', blob: new Blob([r], { type: 'application/pdf' }), pages: pages.length };
      } else {
        const fm = {}; for (const f of files) fm[f.id] = f.file;
        const r = await run({ op: 'build', files: fm, pages: pages.map((p) => ({ f: p.f, i: p.i, r: p.r })) }, setProgress);
        out = { name: MODE === 'merge' ? 'merged.pdf' : 'organized.pdf', blob: new Blob([r], { type: 'application/pdf' }), pages: pages.length, files: new Set(pages.map((p) => p.f)).size };
      }
      showDone(out);
    } catch (e) {
      hideProc(); work.hidden = false;
      if (e && e.code === 'CANCELLED') { announce(t('proc_cancelled')); flash(t('proc_cancelled')); go.focus(); }
      else if (e && e.code === 'OFFLINE') { showOffline(); }
      else {
        const d = (e && e.details) || {};
        // which file failed: images -> page index; build -> fileId tagged by the worker; split or one file -> that file
        const f = d.fileId !== undefined ? byId(d.fileId) : d.index !== undefined && MODE === 'images' ? byId(pages[d.index].f) : files.length === 1 ? files[0] : null;
        if (e && ['PDF_ENCRYPTED', 'PDF_INVALID', 'IMAGE_INVALID', 'IMAGE_TOO_LARGE'].includes(e.code) && f) errFor(e.code, f.file);
        else if (e && MODE === 'split' && splitErrCode(e)) errFor(splitErrCode(e));
        else if (e && (e.code === 'TOO_MANY_PAGES')) errFor('TOO_MANY_PAGES', null, { n: pages.length });
        else if (e && e.code === 'TOO_LARGE' && d.reason === 'decompressed' && f) errFor('TOO_LARGE', f.file, { reason: 'decompressed' });
        else if (e && e.code === 'TOO_LARGE' && d.reason === 'decompressed') errFor('FAILED');
        else if (e && e.code === 'TOO_LARGE') errFor('TOO_LARGE', null, { total: true });
        else errFor('FAILED');
        errs.lastElementChild && errs.lastElementChild.querySelector('.ib').focus();
      }
    } finally { setBusy(false); hideProc(); render(); if (!done.hidden) work.hidden = true; }
  }
  function flash(msg) {
    clearTimeout(undoTimer); undoNow = null; toast.textContent = '';
    const a = el('div', 'alert', msg); toast.appendChild(a); toast.hidden = false;
    undoTimer = setTimeout(() => { toast.hidden = true; toast.textContent = ''; }, 5000);
  }
  function showDone(out) {
    if (resultUrl) URL.revokeObjectURL(resultUrl);
    resultUrl = URL.createObjectURL(out.blob);
    const dl = $('dl'); dl.href = resultUrl; dl.download = out.name;
    dl.textContent = out.kind === 'zip' ? t('download_zip', { n: num(out.files) }, out.files) : t('download_pdf');
    const msg = MODE === 'merge' ? t('done_merge', { pages: num(out.pages), files: num(out.files) }, out.pages)
      : MODE === 'organize' ? t('done_reorder') : MODE === 'images' ? t('done_images', { n: num(out.pages) }, out.pages)
      : out.kind === 'extract' ? t('done_extract', { n: num(out.pages) }, out.pages) : t('done_split', { n: num(out.files || 1) }, out.files || 1);
    $('dtext').textContent = msg;
    $('dname').textContent = t('result_line', { name: out.name, pages: num(out.pages), size: size(out.blob.size) }, out.pages);
    done.hidden = false; work.hidden = true; proc.hidden = true;
    dl.focus();
  }
  $('again').addEventListener('click', () => { done.hidden = true; render(); const k = roving || (pages[0] && pages[0].k); if (k && nodes.get(k) && !list.hidden) focusPage(k); else go.focus(); });
  $('restart').addEventListener('click', () => { done.hidden = true; if (resultUrl) URL.revokeObjectURL(resultUrl); resultUrl = null; resetFiles(); render(); input.focus(); });

  // ---------- live region ----------
  let liveT = null;
  function announce(msg) { clearTimeout(liveT); live.textContent = ''; liveT = setTimeout(() => { live.textContent = msg; }, 50); }

  window.addEventListener('online', () => {
    const c = errs.querySelector('[data-code=OFFLINE]'); if (!c) return;
    c.remove();
    // re-try loading only; do NOT auto-run the user's job
    try { getWorker(); } catch {}
    pdfjs().then(() => render()).catch(() => {});
    if (go && !go.disabled) go.focus(); else input.focus();
  });

  render();
  // test hook for QA (no network, no data): lets Playwright confirm the app booted
  app.dataset.ready = '1';
}
