#!/usr/bin/env python3
"""End-to-end tests for Local PDF Tools (Playwright, chromium/firefox/webkit).
Needs: python3 tools/test/serve.py 8931 running, node tools/test/fixtures.mjs done.
Usage: python3 tools/test/e2e.py [chromium firefox webkit] ; screenshots -> $SHOTS (default /workspace/tmp/pdf-site)."""
import asyncio, json, os, re, subprocess, sys, tempfile
from playwright.async_api import async_playwright, Page

# Playwright's WebKit screenshot code injects a <style>body {}</style> into the page (verified
# with a MutationObserver); the page's CSP correctly refuses it. Violations raised while the harness
# is taking a screenshot are counted separately and are not attributed to the site.
# WebKit also reports a style violation for its own <select> internals on any CSP page that has a
# <select> (reproduced with a bare two-line page); only jpg-to-pdf has one. Counted as ENGINE_CSP.
SHOOTING = {'n': 0}; HARNESS_CSP = []; ENGINE_CSP = []
_shot = Page.screenshot
async def _screenshot(self, *a, **k):
    SHOOTING['n'] += 1
    try:
        r = await _shot(self, *a, **k); await self.wait_for_timeout(150); return r
    finally:
        SHOOTING['n'] -= 1
Page.screenshot = _screenshot
PORT = os.environ.get('E2E_PORT', '8931')  # shared box: another checkout may hold 8931
B = f'http://127.0.0.1:{PORT}/pdf/'
HERE = os.path.dirname(os.path.abspath(__file__)); FX = HERE + '/out/fx/'
SHOTS = os.environ.get('SHOTS', '/workspace/tmp/pdf-site')
RES = []
def ok(name, cond, info=''):
    RES.append((name, bool(cond), info)); print(('PASS ' if cond else 'FAIL ') + name + (('  ' + str(info)) if info and not cond else ''))
def verify(path):
    return json.loads(subprocess.run(['node', HERE + '/verify.mjs', path], capture_output=True, text=True, cwd=HERE).stdout)

class Watch:
    def __init__(s, page, bname):
        s.ext, s.csp, s.errors, s.nonget, s.reqs = [], [], [], [], []
        s.page = page; s.bname = bname; page.on('request', s.req); page.on('console', s.con); page.on('pageerror', lambda e: s.errors.append(str(e)))
    def req(s, r):
        s.reqs.append(r.url)
        if not (r.url.startswith(B) or r.url.startswith('blob:') or r.url.startswith('data:') or r.url == 'about:blank'): s.ext.append(r.url)
        if r.method != 'GET': s.nonget.append(r.method + ' ' + r.url)
    def con(s, m):
        if s.bname == 'webkit' and s.page.url.endswith('jpg-to-pdf.html') and ('CSPV style-src-attr' in m.text or 'apply a stylesheet' in m.text): ENGINE_CSP.append(m.text); return
        if SHOOTING['n'] and ('CSPV style-src' in m.text or 'apply a stylesheet' in m.text): HARNESS_CSP.append(m.text); return
        if m.text.startswith('CSPV '): s.csp.append(m.text + ' @' + s.page.url)
        elif m.type == 'error' and 'Content Security Policy' in m.text: s.csp.append(m.text[:60] + ' @' + s.page.url)
INIT = "document.addEventListener('securitypolicyviolation',e=>console.error('CSPV '+e.violatedDirective+' '+e.blockedURI+' '+e.sourceFile+':'+e.lineNumber+' '+(e.sample||'').slice(0,80)))"

async def newpage(ctx, w=1280, h=900):
    pg = await ctx.new_page(); await pg.set_viewport_size({'width': w, 'height': h}); return pg
async def ready(pg):
    await pg.wait_for_selector('#app[data-ready="1"]', timeout=15000)
async def loaded(pg, n=None):
    await pg.wait_for_selector('#work:not([hidden])', timeout=20000)
    await pg.wait_for_function('document.getElementById("proc").hidden', timeout=20000)
async def screen_pages(pg):
    """[(base width of page, rotation)] from the DOM labels, i.e. what the user sees."""
    return await pg.evaluate("""() => [...document.querySelectorAll('#pages > .pc')].map(li => {
        const t = li.querySelector('.lb').textContent, f = li.querySelector('.lb b').title;
        const n = +(t.match(/(\\d+)\\s*$/) || t.match(/(\\d+)/g).slice(-1))[t.match(/(\\d+)\\s*$/) ? 1 : 0];
        const th = li.querySelector('.th'); const r = ['r90','r180','r270'].find(c => th.classList.contains(c));
        return [f, n, r ? +r.slice(1) : 0]; })""")
BASE = {'contract.pdf': 100, 'invoice.pdf': 200, 'scan.pdf': 300, 'long24.pdf': 100}
async def download(pg, tmp, name):
    async with pg.expect_download(timeout=30000) as d:
        await pg.click('#dl')
    dl = await d.value; p = os.path.join(tmp, name + '-' + dl.suggested_filename); await dl.save_as(p); return dl.suggested_filename, p
async def overflow(pg):
    return await pg.evaluate('document.documentElement.scrollWidth - window.innerWidth')

async def run(bname, p, tmp):
    bt = getattr(p, bname)
    try: browser = await bt.launch()
    except Exception as e: ok(f'{bname}: launch', False, str(e)[:200]); return
    pre = bname + ': '
    ctx = await browser.new_context(accept_downloads=True); await ctx.add_init_script(INIT)
    watches = []

    # ---- QA M1/L1 (398ade0): build-time refchain error names the file; all files rejected -> no pageerror ----
    pg = await newpage(ctx); w = Watch(pg, bname); watches.append(w)
    await pg.goto(B + 'merge-pdf.html'); await ready(pg)
    await pg.set_input_files('#files', [FX + 'contract.pdf', FX + 'refchain40.pdf']); await loaded(pg)
    await pg.click('#go'); await pg.wait_for_selector('#errs .ecard', timeout=30000); await pg.wait_for_selector('#proc', state='hidden')
    codes = await pg.eval_on_selector_all('#errs .ecard', 'e => e.map(x => x.dataset.code)'); etxt = await pg.inner_text('#errs')
    ok(pre + 'merge: refchain-40 in a 2-file merge -> PDF_INVALID card naming the file, no FAILED', codes == ['PDF_INVALID'] and 'refchain40.pdf' in etxt, (codes, etxt[:120]))
    big = os.path.join(tmp, 'big101.pdf')
    if not os.path.exists(big):
        with open(big, 'wb') as fh: fh.truncate(101 * 1024 * 1024)
    n0 = len(w.errors)
    pg2 = await newpage(ctx); w2 = Watch(pg2, bname); watches.append(w2)
    await pg2.goto(B + 'merge-pdf.html'); await ready(pg2)
    await pg2.set_input_files('#files', [big]); await pg2.wait_for_selector('#errs .ecard'); await pg2.wait_for_timeout(300)
    codes = await pg2.eval_on_selector_all('#errs .ecard', 'e => e.map(x => x.dataset.code)')
    ok(pre + 'merge: all files rejected (101 MB) -> TOO_LARGE card, no pageerror', codes == ['TOO_LARGE'] and not w2.errors and len(w.errors) == n0, (codes, w2.errors))
    await pg.close(); await pg2.close()

    # ---- merge (ru): errors + reorder by button, keyboard, drag, delete+undo; output order/rotation = screen ----
    pg = await newpage(ctx); w = Watch(pg, bname); watches.append(w)
    await pg.goto(B + 'ru/merge-pdf.html'); await ready(pg)
    await pg.set_input_files('#files', [FX + x for x in ('contract.pdf', 'invoice.pdf', 'scan.pdf', 'bank-statement.pdf', 'photo-gps.jpg')])
    await loaded(pg)
    codes = await pg.eval_on_selector_all('#errs .ecard', 'e => e.map(x => x.dataset.code)')
    ok(pre + 'merge: encrypted + image-in-PDF-mode cards, valid files kept', codes == ['PDF_ENCRYPTED', 'PDF_INVALID'] and await pg.locator('#pages > .pc').count() == 8, codes)
    ok(pre + 'merge: image card uses the Images-to-PDF hint', 'Изображения в PDF' in (await pg.inner_text('#errs')).replace('\xa0', ' '))
    ok(pre + 'merge: primary label plural', (await pg.inner_text('#go')).strip() == 'Объединить 8 страниц', await pg.inner_text('#go'))
    await pg.wait_for_timeout(800)
    await pg.screenshot(path=f'{SHOTS}/{bname}-03-merge-loaded-ru-1280.png', full_page=True)
    # button move: page 1 -> right
    await pg.locator('#pages > .pc').nth(0).locator('[data-act=right]').click()
    # keyboard: focus page 2, R rotates, Space pick, ArrowRight x2, Space drop
    pick = pg.locator('#pages > .pc').nth(1).locator('.pick'); await pick.focus()
    await pg.keyboard.press('r'); await pg.keyboard.press('Space'); await pg.keyboard.press('ArrowRight'); await pg.keyboard.press('ArrowRight'); await pg.keyboard.press('Space')
    await pg.wait_for_timeout(150); live = await pg.inner_text('#live')
    kb = await screen_pages(pg)
    ok(pre + 'merge: keyboard Space/Arrow/Space moves the page 2 places + R rotated it', kb[3][2] == 90, kb[:4])
    # Esc cancels a pick
    before = await screen_pages(pg)
    await pg.keyboard.press('Space'); await pg.keyboard.press('ArrowLeft'); await pg.keyboard.press('Escape')
    ok(pre + 'merge: Esc cancels a keyboard move', await screen_pages(pg) == before)
    # drag page 8 onto page 1 (mouse, pointer events)
    a = await pg.locator('#pages > .pc').nth(7).locator('.th').bounding_box(); t = await pg.locator('#pages > .pc').nth(0).locator('.th').bounding_box()
    await pg.mouse.move(a['x'] + 20, a['y'] + 20); await pg.mouse.down()
    for k in range(1, 16): await pg.mouse.move(a['x'] + 20 + (t['x'] + 10 - a['x'] - 20) * k / 15, a['y'] + 20 + (t['y'] + 30 - a['y'] - 20) * k / 15)
    await pg.wait_for_timeout(100); await pg.mouse.up(); await pg.wait_for_timeout(200)
    after_drag = await screen_pages(pg)
    ok(pre + 'merge: mouse drag moved last page to the front', after_drag[0] == before[-1] if before else False, after_drag[:2])
    # Delete with undo, then Delete for real
    await pg.locator('#pages > .pc').nth(2).locator('.pick').focus(); s0 = await screen_pages(pg)
    await pg.keyboard.press('Delete'); await pg.wait_for_selector('#toast:not([hidden])')
    ok(pre + 'merge: Delete removes, toast with Undo', await pg.locator('#pages > .pc').count() == 7)
    await pg.click('#toast button'); ok(pre + 'merge: Undo restores', await screen_pages(pg) == s0)
    await pg.locator('#pages > .pc').nth(3).locator('[data-act=del]').click()
    screen = await screen_pages(pg)
    ok(pre + 'merge: live announcements', bool(live), live)
    await pg.click('#go')
    await pg.wait_for_selector('#done:not([hidden])', timeout=30000)
    await pg.screenshot(path=f'{SHOTS}/{bname}-06-merge-done-ru-1280.png', full_page=True)
    name, path = await download(pg, tmp, 'merge'); v = verify(path)
    exp = [(BASE[f] + n, r) for f, n, r in screen]; got = [(x['w'], x['rot']) for x in v['pages']]
    ok(pre + 'merge: download merged.pdf, order + rotation = screen', name == 'merged.pdf' and exp == got, (exp, got))
    ok(pre + 'merge: no Info/XMP in output', not v['info'] and not v['xmp'], v)
    ok(pre + 'merge: done text + result line', '7' in await pg.inner_text('#dname') and 'merged.pdf' in await pg.inner_text('#dname'), await pg.inner_text('#dname'))
    await pg.click('#again'); ok(pre + 'merge: Change order returns to the list', await pg.is_visible('#pages'))
    for wd in (320, 375):
        await pg.set_viewport_size({'width': wd, 'height': 800}); await pg.wait_for_timeout(200)
        ok(pre + f'merge loaded: no horizontal overflow at {wd}', await overflow(pg) <= 0, await overflow(pg))
        await pg.screenshot(path=f'{SHOTS}/{bname}-03-merge-loaded-ru-{wd}.png', full_page=True)
    # mobile buttons up/down are the visible ones
    vis_up = await pg.locator('#pages > .pc').nth(1).locator('[data-act=up]').is_visible(); vis_left = await pg.locator('#pages > .pc').nth(1).locator('[data-act=left]').is_visible()
    ok(pre + 'merge <600: ↑↓ buttons instead of ←→', vis_up and not vis_left)
    small = await pg.evaluate("""() => [...document.querySelectorAll('button, a, input, select, summary, label.drop')].filter(e => { const r = e.getBoundingClientRect(); const cs = getComputedStyle(e);
        return r.width > 0 && r.height > 0 && cs.visibility !== 'hidden' && !e.closest('[hidden]') && !e.classList.contains('sr-only') && !(e.closest('details:not([open])') && e.tagName !== 'SUMMARY') && !e.closest('.lb,.lb2') && (r.width < 44 || r.height < 44) && !(e.tagName==='A' && e.closest('main p')); }).map(e => e.outerHTML.slice(0, 80))""")
    ok(pre + 'merge <600: all targets >= 44x44', not small, small[:5])
    await pg.click('details.settings summary'); await pg.wait_for_timeout(300)
    menu = await pg.evaluate("[...document.querySelectorAll('.settings .menu a')].map(a => Math.round(a.getBoundingClientRect().height))")
    ok(pre + 'language menu open: links >= 44 px tall', menu and min(menu) >= 44, menu)
    await pg.keyboard.press('Escape')
    await pg.close()

    # ---- clear confirm ----
    pg = await newpage(ctx); w = Watch(pg, bname); watches.append(w)
    await pg.goto(B + 'organize-pdf.html'); await ready(pg)
    await pg.set_input_files('#files', [FX + 'contract.pdf']); await loaded(pg)
    await pg.click('#clear'); ok(pre + 'organize: Clear asks for confirmation', await pg.is_visible('#confirm'))
    await pg.click('#cfno'); ok(pre + 'organize: confirm Cancel keeps pages', await pg.locator('#pages > .pc').count() == 3)
    await pg.close()

    # ---- organize (zh): evil.pdf, rotate + delete, metadata/scripts cleaned ----
    pg = await newpage(ctx); w = Watch(pg, bname); watches.append(w)
    await pg.goto(B + 'zh/organize-pdf.html'); await ready(pg)
    await pg.set_input_files('#files', [FX + 'evil.pdf']); await loaded(pg)
    await pg.locator('#pages > .pc').nth(0).locator('[data-act=rot]').click()
    await pg.locator('#pages > .pc').nth(1).locator('[data-act=del]').click()
    await pg.click('#go'); await pg.wait_for_selector('#done:not([hidden])', timeout=30000)
    name, path = await download(pg, tmp, 'org'); v = verify(path)
    ok(pre + 'organize: 1 page, rotated 90, file name', name == 'organized.pdf' and [(x['w'], x['rot']) for x in v['pages']] == [(300, 90)], (name, v['pages']))
    ok(pre + 'organize: no Info/XMP/JS markers', not v['info'] and not v['xmp'] and not v['evil'], v)
    await pg.close()

    # ---- split (en): ranges, invalid, every N, extract ----
    pg = await newpage(ctx); w = Watch(pg, bname); watches.append(w)
    await pg.goto(B + 'split-pdf.html'); await ready(pg)
    # two files dropped onto the dropzone (the input itself is single-file in split)
    files = [[n, list(open(FX + n, 'rb').read())] for n in ('long24.pdf', 'contract.pdf')]
    await pg.evaluate('''fs => { const dt = new DataTransfer(); for (const [n, b] of fs) dt.items.add(new File([new Uint8Array(b)], n, {type: 'application/pdf'}));
        document.getElementById('drop').dispatchEvent(new DragEvent('drop', {dataTransfer: dt, bubbles: true, cancelable: true})); }''', files)
    await loaded(pg)
    ok(pre + 'split: two files -> first kept + notice', 'long24.pdf' in await pg.inner_text('#sfname') and 'SPLIT_ONE' in await pg.eval_on_selector_all('#errs .ecard', 'e=>e.map(x=>x.dataset.code).join()'))
    await pg.fill('#ranges', '30'); inv = await pg.is_visible('#rerr'); dis = await pg.is_disabled('#go')
    ok(pre + 'split: invalid range -> inline error, primary disabled', inv and dis and '24' in await pg.inner_text('#rerr'), await pg.inner_text('#rerr'))
    await pg.fill('#ranges', '1-3, 5, 8–10')
    ok(pre + 'split: live result line', await pg.inner_text('#sres') == "You'll get 3 files: pp. 1–3, p. 5, pp. 8–10, in a ZIP.", await pg.inner_text('#sres'))
    await pg.screenshot(path=f'{SHOTS}/{bname}-04-split-en-1280.png', full_page=True)
    await pg.click('#go'); await pg.wait_for_selector('#done:not([hidden])', timeout=30000)
    ok(pre + 'split: Download ZIP (3 files)', (await pg.inner_text('#dl')).strip() == 'Download ZIP (3 files)', await pg.inner_text('#dl'))
    name, path = await download(pg, tmp, 'split'); v = verify(path)
    ok(pre + 'split ranges: split.zip with pages 1-3 | 5 | 8-10', name == 'split.zip' and [[p['w'] - 100 for p in z['pages']] for z in v['zip']] == [[1, 2, 3], [5], [8, 9, 10]], v)
    await pg.click('#again')
    await pg.check('input[name=smode][value=every]'); await pg.fill('#every', '10')
    ok(pre + 'split every N: result line', '3 files' in await pg.inner_text('#sres'), await pg.inner_text('#sres'))
    await pg.click('#go'); await pg.wait_for_selector('#done:not([hidden])', timeout=30000)
    name, path = await download(pg, tmp, 'every'); v = verify(path)
    ok(pre + 'split every 10: 3 files of 10/10/4', [len(z['pages']) for z in v['zip']] == [10, 10, 4], [len(z['pages']) for z in v.get('zip', [])])
    await pg.click('#again')
    await pg.check('input[name=smode][value=extract]'); await pg.wait_for_selector('#pages > .pc')
    await pg.locator('#pages > .pc').nth(1).locator('.pick').click(); await pg.locator('#pages > .pc').nth(4).locator('.pick').focus(); await pg.keyboard.press('Space')
    ok(pre + 'split extract: count', '2 of 24' in await pg.inner_text('#xcount'), await pg.inner_text('#xcount'))
    await pg.click('#go'); await pg.wait_for_selector('#done:not([hidden])', timeout=30000)
    name, path = await download(pg, tmp, 'extract'); v = verify(path)
    ok(pre + 'split extract: pages.pdf with pages 2, 5', name == 'pages.pdf' and [p['w'] for p in v['pages']] == [102, 105], (name, v.get('pages')))
    await pg.close()

    # ---- result_line plural (organize): 2 pages vs 1 page, en/ru/zh; done_* never says "1 pages" ----
    for lang, two, one in (('', ' · 2 pages · ', ' · 1 page · '), ('ru/', ' · 2 стр. · ', ' · 1 стр. · '), ('zh/', ' · 2 页 · ', ' · 1 页 · ')):
        pg = await newpage(ctx); w = Watch(pg, bname); watches.append(w)
        await pg.goto(B + lang + 'organize-pdf.html'); await ready(pg)
        await pg.set_input_files('#files', [FX + 'invoice.pdf']); await loaded(pg)
        await pg.click('#go'); await pg.wait_for_selector('#done:not([hidden])', timeout=30000)
        d2 = (await pg.inner_text('#dname')).replace('\xa0', ' ')
        await pg.click('#again'); await pg.locator('#pages > .pc').nth(1).locator('[data-act=del]').click()
        await pg.click('#go'); await pg.wait_for_selector('#done:not([hidden])', timeout=30000)
        d1 = (await pg.inner_text('#dname')).replace('\xa0', ' ')
        ok(pre + f'result_line plural {lang or "en/"}: 2 vs 1 page', two in d2 and one in d1 and '1 pages' not in d1, (d2, d1))
        await pg.close()
    pg = await newpage(ctx); w = Watch(pg, bname); watches.append(w)
    await pg.goto(B + 'split-pdf.html'); await ready(pg)
    await pg.set_input_files('#files', [FX + 'long24.pdf']); await loaded(pg)
    await pg.fill('#ranges', '5'); await pg.click('#go'); await pg.wait_for_selector('#done:not([hidden])', timeout=30000)
    dn = await pg.inner_text('#dname')
    ok(pre + 'split single page (en): result line "1 page", no "1 pages"', ' · 1 page · ' in dn and '1 pages' not in dn, dn)
    await pg.close()

    # ---- split option descriptions (en/ru/zh): visible under each radio, linked by aria-describedby ----
    src = {l: json.load(open(f'{HERE}/../i18n/{l}.json', encoding='utf-8')) for l in ('en', 'ru', 'zh')}
    for lang, l in (('', 'en'), ('ru/', 'ru'), ('zh/', 'zh')):
        pg = await newpage(ctx); w = Watch(pg, bname); watches.append(w)
        await pg.goto(B + lang + 'split-pdf.html'); await ready(pg)
        await pg.set_input_files('#files', [FX + 'long24.pdf']); await loaded(pg)
        got = await pg.evaluate("""() => ['ranges','every','extract'].map(m => { const r = document.querySelector(`input[name=smode][value=${m}]`); const d = document.getElementById(r.getAttribute('aria-describedby'));
            return d ? [d.textContent, d.getBoundingClientRect().height > 0] : null; })""")
        want = [[src[l][f'split_{m}_desc'], True] for m in ('ranges', 'every', 'extract')]
        ok(pre + f'split option descriptions {l}: present, visible, aria-describedby', got == want, got)
        await pg.close()

    # ---- split limits: 1000 pages per part, 5000 total, 50 parts (6000-page file); 2500 pages over 3 parts works ----
    pg = await newpage(ctx); w = Watch(pg, bname); watches.append(w)
    await pg.goto(B + 'split-pdf.html'); await ready(pg)
    await pg.set_input_files('#files', [FX + 'long6000.pdf']); await loaded(pg)
    async def rerr(): return (await pg.get_attribute('#rerr', 'data-code'), (await pg.inner_text('#rerr')).replace('\xa0', ' '), await pg.is_disabled('#go'))
    await pg.fill('#ranges', '1-1001'); c, tx, dis = await rerr()
    ok(pre + 'split limit: part > 1000 pages -> err_split_part_pages', c == 'SPLIT_PART_PAGES' and 'A file has more than 1,000 pages' in tx and dis, (c, tx))
    await pg.check('input[name=smode][value=every]'); await pg.fill('#every', '1000'); c, tx, dis = await rerr()
    ok(pre + 'split limit: total > 5000 pages -> err_split_total_pages', c == 'SPLIT_TOTAL_PAGES' and 'All files together exceed 5,000 pages' in tx and dis, (c, tx))
    await pg.fill('#every', '100'); c, tx, dis = await rerr()
    ok(pre + 'split limit: > 50 parts -> err_split_parts', c == 'SPLIT_PARTS' and 'More than 50 files' in tx and dis, (c, tx))
    await pg.check('input[name=smode][value=ranges]'); await pg.fill('#ranges', '1-1000, 1001-2000, 2001-2500'); c, tx, dis = await rerr()
    ok(pre + 'split limit: 2500 pages in 3 parts allowed', c is None and not dis, (c, tx))
    await pg.click('#go'); await pg.wait_for_selector('#done:not([hidden])', timeout=60000)
    ok(pre + 'split 2500 pages / 3 parts: ZIP of 3 files (batched core calls)', (await pg.inner_text('#dl')).strip() == 'Download ZIP (3 files)', await pg.inner_text('#dl'))
    await pg.close()
    # ru texts for the three limits (no placeholders)
    pg = await newpage(ctx); w = Watch(pg, bname); watches.append(w)
    await pg.goto(B + 'ru/split-pdf.html'); await ready(pg)
    await pg.set_input_files('#files', [FX + 'long6000.pdf']); await loaded(pg)
    await pg.fill('#ranges', '1-1001'); c, tx, _ = await rerr()
    ok(pre + 'split limit ru: part text', 'В одном файле больше 1000 страниц' in tx, tx)
    await pg.close()

    # ---- split: core errors carry details.limit ('part' | 'total' | 'parts', core 047da26) -> the matching split card ----
    real_w = open(os.path.join(HERE, '..', '..', 'assets', 'worker.js')).read()
    for limit, ccode, code in (('part', 'TOO_MANY_PAGES', 'SPLIT_PART_PAGES'), ('total', 'TOO_MANY_PAGES', 'SPLIT_TOTAL_PAGES'), ('parts', 'TOO_MANY_FILES', 'SPLIT_PARTS')):
        shim2 = real_w + """
;(() => { const real = self.onmessage; self.onmessage = (ev) => { const m = ev.data;
  if (m.op === 'split') return self.postMessage({ id: m.id, error: { code: '%s', details: { limit: '%s' } } });
  return real(ev); }; })();""" % (ccode, limit)
        pg = await newpage(ctx); w = Watch(pg, bname); watches.append(w)
        await pg.route('**/pdf/assets/worker.js', (lambda b: lambda r: r.fulfill(status=200, content_type='text/javascript', body=b))(shim2))  # Playwright passes (route, request) to 2-arg handlers
        await pg.goto(B + 'split-pdf.html'); await ready(pg)
        await pg.set_input_files('#files', [FX + 'long24.pdf']); await loaded(pg)
        await pg.fill('#ranges', '1-3, 4-6'); await pg.click('#go'); await pg.wait_for_selector('#errs .ecard', timeout=15000)
        got = await pg.eval_on_selector('#errs .ecard', 'e=>e.dataset.code')
        ok(pre + f'split core error {ccode} details.limit={limit} -> {code}', got == code, got)
        await pg.close()

    # ---- the three split errors as inline text (en/ru/zh), and 'every 1 page' on a 60-page file -> err_split_parts ----
    for lang, l in (('', 'en'), ('ru/', 'ru'), ('zh/', 'zh')):
        pg = await newpage(ctx); w = Watch(pg, bname); watches.append(w)
        await pg.goto(B + lang + 'split-pdf.html'); await ready(pg)
        await pg.set_input_files('#files', [FX + 'long6000.pdf']); await loaded(pg)
        got = []
        for v, code in (('1-1001', 'SPLIT_PART_PAGES'), ('1-1000, 1001-2000, 2001-3000, 3001-4000, 4001-5000, 5001-5001', 'SPLIT_TOTAL_PAGES')):
            await pg.fill('#ranges', v); c, tx, dis = await rerr(); k = 'err_' + code.lower()
            got.append(c == code and dis and src[l][k].replace('\xa0', ' ') in tx and src[l][k + '_fix'].replace('\xa0', ' ') in tx)
        await pg.close()
        pg = await newpage(ctx); w = Watch(pg, bname); watches.append(w)
        await pg.goto(B + lang + 'split-pdf.html'); await ready(pg)
        await pg.set_input_files('#files', [FX + 'long60.pdf']); await loaded(pg)
        await pg.check('input[name=smode][value=every]'); await pg.fill('#every', '1'); c, tx, dis = await rerr()
        got.append(c == 'SPLIT_PARTS' and dis and src[l]['err_split_parts'].replace('\xa0', ' ') in tx)
        ok(pre + f'split errors {l}: part / total texts, every 1 page on 60 pages -> err_split_parts', all(got), (got, tx))
        await pg.close()

    # ---- PAGE_RANGE is written to a stable polite region (#rlive: never moved, cleared once resolved) ----
    pg = await newpage(ctx); w = Watch(pg, bname); watches.append(w)
    await pg.goto(B + 'split-pdf.html'); await ready(pg)
    await pg.set_input_files('#files', [FX + 'long24.pdf']); await loaded(pg)
    par0 = await pg.evaluate("document.getElementById('rlive').parentElement.tagName + (document.getElementById('rlive').getAttribute('aria-live'))")
    await pg.fill('#ranges', '30'); await pg.wait_for_timeout(50)
    l1 = await pg.inner_text('#rlive')
    await pg.fill('#ranges', '1-3'); l2 = await pg.inner_text('#rlive')
    await pg.check('input[name=smode][value=every]'); await pg.fill('#every', '30'); l3 = await pg.inner_text('#rlive')
    par1 = await pg.evaluate("document.getElementById('rlive').parentElement.tagName + (document.getElementById('rlive').getAttribute('aria-live'))")
    ok(pre + 'split PAGE_RANGE: error text in #rlive (polite), emptied when the error is resolved (element kept), region not moved',
       src['en']['err_range'] in l1 and '24' in l1 and l2 == '' and await pg.locator('#rlive').count() == 1 and l3 == src['en']['err_every_n'].replace('{pageCount}', '24') and par0 == par1 == 'FIELDSETpolite', (par0, par1, l1, l2, l3))
    await pg.close()

    # ---- organize at 375 (.pick is display:contents) and 1280: delete -> neighbour's delete button; Undo -> restored card, announced ----
    for wd in (375, 1280):
        pg = await newpage(ctx, wd, 800); w = Watch(pg, bname); watches.append(w)
        await pg.goto(B + 'organize-pdf.html'); await ready(pg)
        await pg.set_input_files('#files', [FX + 'contract.pdf']); await loaded(pg)
        await pg.locator('#pages > .pc').nth(1).locator('[data-act=del]').click()
        f1 = await pg.evaluate("(() => { const a = document.activeElement; const li = a.closest('.pc'); return [a.dataset.act || a.className, li ? [...li.parentElement.children].indexOf(li) : -1]; })()")
        await pg.click('#toast button'); await pg.wait_for_timeout(120)
        f2 = await pg.evaluate("(() => { const a = document.activeElement; const li = a.closest('.pc'); return [a.tagName, li ? [...li.parentElement.children].indexOf(li) : -1, a.getClientRects().length > 0]; })()")
        lv = await pg.inner_text('#live')
        ok(pre + f'organize {wd}: delete focuses the neighbour delete button, Undo focuses the restored card + org_restored',
           f1 == ['del', 1] and f2[0] == 'BUTTON' and f2[1] == 1 and f2[2] and lv == 'Page 2 restored', (f1, f2, lv))
        await pg.close()

    # ---- organize 375 (<600, .pick display:contents): Esc on Undo and timer close focus a card, not body (Olivia UX FAIL b458eda) ----
    pg = await newpage(ctx, 375, 800); w = Watch(pg, bname); watches.append(w)
    await pg.goto(B + 'organize-pdf.html'); await ready(pg)
    await pg.set_input_files('#files', [FX + 'contract.pdf']); await loaded(pg)
    FOC = "(() => { const a = document.activeElement; return [a.tagName, !!a.closest('#pages > .pc'), a.getClientRects().length > 0]; })()"
    await pg.locator('#pages > .pc').nth(1).locator('[data-act=del]').click()
    await pg.keyboard.press('Tab'); intoast = await pg.evaluate("!!document.activeElement.closest('#toast')")
    await pg.keyboard.press('Escape'); await pg.wait_for_timeout(120)
    fe = await pg.evaluate(FOC); he = await pg.is_visible('#toast')
    ok(pre + 'organize 375: Esc on Undo closes the toast and focuses a card (not body)', intoast and not he and fe[0] != 'BODY' and fe[1] and fe[2], (intoast, he, fe))
    await pg.locator('#pages > .pc').nth(0).locator('[data-act=del]').click(); await pg.mouse.move(1, 1)
    await pg.evaluate("document.activeElement.blur()"); await pg.wait_for_timeout(10800)
    ft = await pg.evaluate(FOC); ht = await pg.is_visible('#toast')
    ok(pre + 'organize 375: timer close focuses a card (not body)', not ht and ft[0] != 'BODY' and ft[1] and ft[2], (ht, ft))
    await pg.close()

    # ---- Undo toast (v1 scope 3): DOM after the grid, Tab reaches it, 10 s, paused on focus/hover, Ctrl/Cmd+Z, last page -> Undo ----
    pg = await newpage(ctx); w = Watch(pg, bname); watches.append(w)
    await pg.goto(B + 'organize-pdf.html'); await ready(pg)
    await pg.set_input_files('#files', [FX + 'contract.pdf']); await loaded(pg)
    n0 = await pg.locator('#pages > .pc').count()
    await pg.locator('#pages > .pc').nth(0).locator('[data-act=del]').click()
    dom = await pg.evaluate("document.getElementById('pages').nextElementSibling && document.getElementById('pages').nextElementSibling.id")
    await pg.keyboard.press('Tab'); tab = await pg.evaluate("!!document.activeElement.closest('#toast')")
    ok(pre + 'undo: toast is the next DOM sibling of the page grid, next Tab reaches Undo', dom == 'toast' and tab, (dom, tab))
    await pg.wait_for_timeout(11000)
    ok(pre + 'undo: timer paused while Undo has focus (11 s)', await pg.is_visible('#toast'))
    await pg.click('#toast button'); await pg.wait_for_timeout(100)
    ok(pre + 'undo: Undo after pause restores', await pg.locator('#pages > .pc').count() == n0)
    await pg.locator('#pages > .pc').nth(0).locator('[data-act=del]').click()
    await pg.hover('#toast button'); await pg.wait_for_timeout(10800)
    hov = await pg.is_visible('#toast'); await pg.mouse.move(1, 1)
    ok(pre + 'undo: timer paused while Undo is hovered', hov)
    await pg.click('#toast button'); await pg.wait_for_timeout(100)
    await pg.locator('#pages > .pc').nth(0).locator('[data-act=del]').click(); await pg.mouse.move(1, 1)
    await pg.wait_for_timeout(9300); v9 = await pg.is_visible('#toast')
    await pg.wait_for_timeout(1500); v11 = await pg.is_visible('#toast')
    ok(pre + 'undo: toast visible at 9.3 s, gone at 10.8 s (10 s timeout)', v9 and not v11, (v9, v11))
    n1 = await pg.locator('#pages > .pc').count()
    await pg.locator('#pages > .pc').nth(0).locator('[data-act=del]').click()
    await pg.keyboard.press('Meta+z' if bname == 'webkit' else 'Control+z'); await pg.wait_for_timeout(100)
    ok(pre + 'undo: Ctrl/Cmd+Z undoes while the toast is visible', await pg.locator('#pages > .pc').count() == n1 and not await pg.is_visible('#toast'))
    while await pg.locator('#pages > .pc').count() > 1:
        await pg.locator('#pages > .pc').nth(0).locator('[data-act=del]').click(); await pg.wait_for_timeout(50)
    await pg.locator('#pages > .pc').nth(0).locator('[data-act=del]').click(); await pg.wait_for_timeout(100)
    lastf = await pg.evaluate("!!document.activeElement.closest('#toast')")
    ok(pre + 'undo M1: deleting the last page focuses Undo', lastf)
    await pg.close()

    # ---- mode tabs 2x2 grid below 600px, inactive tab + licences th contrast, language menu 44px ----
    CONTRAST = """(sel) => { const el = document.querySelector(sel); const cv = document.createElement('canvas'); cv.width = cv.height = 1; const c = cv.getContext('2d', { willReadFrequently: true });
      const rgb = (col) => { c.clearRect(0, 0, 1, 1); c.fillStyle = '#fff'; c.fillRect(0, 0, 1, 1); c.fillStyle = col; c.fillRect(0, 0, 1, 1); return [...c.getImageData(0, 0, 1, 1).data].slice(0, 3); };
      const bgs = []; for (let n = el; n; n = n.parentElement) { const b = getComputedStyle(n).backgroundColor; if (b && b !== 'transparent' && b !== 'rgba(0, 0, 0, 0)') bgs.unshift(b); }
      c.clearRect(0, 0, 1, 1); c.fillStyle = '#fff'; c.fillRect(0, 0, 1, 1); for (const b of bgs) { c.fillStyle = b; c.fillRect(0, 0, 1, 1); }
      const bg = [...c.getImageData(0, 0, 1, 1).data].slice(0, 3); c.fillStyle = getComputedStyle(el).color; c.fillRect(0, 0, 1, 1); const fg = [...c.getImageData(0, 0, 1, 1).data].slice(0, 3);
      const L = (a) => { const v = a.map((x) => { x /= 255; return x <= 0.03928 ? x / 12.92 : ((x + 0.055) / 1.055) ** 2.4; }); return 0.2126 * v[0] + 0.7152 * v[1] + 0.0722 * v[2]; };
      const a = L(fg), b = L(bg); return Math.round((Math.max(a, b) + 0.05) / (Math.min(a, b) + 0.05) * 100) / 100; }"""
    for scheme in ('light', 'dark'):
        c3 = await browser.new_context(color_scheme=scheme); await c3.add_init_script(INIT)
        for wd in (375, 599):
            pg = await newpage(c3, wd, 800); w = Watch(pg, bname); watches.append(w)
            await pg.goto(B + 'merge-pdf.html'); await ready(pg)
            g = await pg.evaluate("""() => { const t = document.querySelector('.tabs.modetabs'); const r = [...t.querySelectorAll('.tab')].map(x => x.getBoundingClientRect());
                return [getComputedStyle(t).display, new Set(r.map(x => Math.round(x.top))).size, new Set(r.map(x => Math.round(x.left))).size, r.length]; }""")
            ok(pre + f'mode tabs {scheme} {wd}: 2x2 grid', g == ['grid', 2, 2, 4], g)
            if wd == 375:
                cr = await pg.evaluate(CONTRAST, '.tabs.modetabs > .tab:not(.tab-active)')
                ok(pre + f'mode tabs {scheme}: inactive tab contrast >= 4.5', cr >= 4.5, cr)
            await pg.close()
        pg = await newpage(c3, 1280, 800); w = Watch(pg, bname); watches.append(w)
        await pg.goto(B + 'licenses.html'); await pg.wait_for_load_state('load')
        cr = await pg.evaluate(CONTRAST, '.table thead th')
        ok(pre + f'licences {scheme}: table header contrast >= 4.5', cr >= 4.5, cr)
        await c3.close()
    pg = await newpage(ctx, 375, 800); w = Watch(pg, bname); watches.append(w)
    await pg.goto(B + 'ru/'); await pg.wait_for_load_state('load')
    await pg.click('details.settings summary'); await pg.wait_for_timeout(100)
    hs = await pg.evaluate("[...document.querySelectorAll('details.settings a[hreflang]')].map(a => Math.round(a.getBoundingClientRect().height))")
    ok(pre + 'language menu: touch targets >= 44px', hs and min(hs) >= 44, hs)
    await pg.close()

    # ---- FAQ visible == FAQPage JSON-LD on every page; ru privacy Metadata paragraph keeps U+00A0 typography ----
    pg = await newpage(ctx); w = Watch(pg, bname); watches.append(w)
    bad = []
    for lang in ('', 'ru/', 'zh/'):
        for pth in ('', 'merge-pdf.html', 'split-pdf.html', 'organize-pdf.html', 'jpg-to-pdf.html'):
            await pg.goto(B + lang + pth); await pg.wait_for_load_state('load')
            r = await pg.evaluate("""() => { const vis = [...document.querySelectorAll('.faq details')].map(d => [d.querySelector('summary').textContent, d.querySelector('.collapse-content').textContent]);
                const ld = [...document.querySelectorAll('script[type="application/ld+json"]')].map(x => JSON.parse(x.textContent)).flat().find(x => x['@type'] === 'FAQPage');
                const l = ld ? ld.mainEntity.map(q => [q.name, q.acceptedAnswer.text]) : null; const n = (s) => s.replace(/\u00a0/g, ' ');
                return !!l && vis.length === l.length && vis.every((v, i) => n(v[0]) === l[i][0] && n(v[1]) === l[i][1]); }""")
            if not r: bad.append(lang + pth)
    ok(pre + 'FAQ: visible text == FAQPage JSON-LD word for word (15 pages)', not bad, bad)
    await pg.goto(B + 'organize-pdf.html'); await pg.wait_for_load_state('load')
    ok(pre + 'FAQ organize: Undo 10 seconds', 'undo it for 10 seconds' in await pg.evaluate("document.querySelector('.faq').textContent"))
    await pg.goto(B + 'ru/privacy.html'); await pg.wait_for_load_state('load')
    mp = await pg.evaluate("[...document.querySelectorAll('main p')].map(p => p.textContent).find(t => t.startsWith('Метаданные.'))")
    ok(pre + 'ru privacy Metadata: Counsel text with U+00A0 typography', bool(mp) and '\u00a0' in mp and mp.replace('\u00a0', ' ').startswith('Метаданные. Сохранённый PDF всегда создаётся как новый документ') and mp.replace('\u00a0', ' ').endswith('Сам текст и содержимое страниц не меняются.'), mp)
    await pg.close()

    # ---- encrypted card on merge: closeable, the file stays out of the list ----
    pg = await newpage(ctx); w = Watch(pg, bname); watches.append(w)
    await pg.goto(B + 'merge-pdf.html'); await ready(pg)
    await pg.set_input_files('#files', [FX + 'contract.pdf', FX + 'bank-statement.pdf']); await loaded(pg)
    c0 = await pg.eval_on_selector_all('#errs .ecard', 'e => e.map(x => x.dataset.code)')
    await pg.click('#errs .ecard[data-code=PDF_ENCRYPTED] button'); await pg.wait_for_timeout(100)
    c1 = await pg.locator('#errs .ecard').count(); n = await pg.locator('#pages > .pc').count()
    names = await pg.eval_on_selector_all('#pages > .pc .lb b', 'e => [...new Set(e.map(x => x.title))]')
    ok(pre + 'encrypted card: closeable, file not in the list', c0 == ['PDF_ENCRYPTED'] and c1 == 0 and n == 3 and names == ['contract.pdf'], (c0, c1, n, names))
    await pg.close()

    # ---- primary label plural 1 vs 2 pages (merge, en/ru/zh) ----
    for lang, l in (('', 'en'), ('ru/', 'ru'), ('zh/', 'zh')):
        pg = await newpage(ctx); w = Watch(pg, bname); watches.append(w)
        await pg.goto(B + lang + 'merge-pdf.html'); await ready(pg)
        await pg.set_input_files('#files', [FX + 'invoice.pdf']); await loaded(pg)
        g2 = (await pg.inner_text('#go')).strip()
        await pg.locator('#pages > .pc').nth(1).locator('[data-act=del]').click(); g1 = (await pg.inner_text('#go')).strip()
        pm = src[l]['primary_merge']; want2 = pm.get('few', pm.get('other')).replace('{n}', '2'); want1 = pm.get('one', pm.get('other')).replace('{n}', '1')
        ok(pre + f'merge primary plural {l}: 2 vs 1 page', g2 == want2 and g1 == want1, (g2, g1, want2, want1))
        await pg.close()

    # ---- HEIC on jpg-to-pdf: UNSUPPORTED_IMAGE card links the converter's HEIC -> JPG page (en/ru/zh) ----
    for lang, l in (('', 'en'), ('ru/', 'ru'), ('zh/', 'zh')):
        pg = await newpage(ctx); w = Watch(pg, bname); watches.append(w)
        await pg.goto(B + lang + 'jpg-to-pdf.html'); await ready(pg)
        await pg.set_input_files('#files', [FX + 'IMG_0001.heic', FX + 'notes.txt'])
        await pg.wait_for_selector('#errs .ecard:nth-child(2)'); await pg.wait_for_selector('#proc', state='hidden')
        info = await pg.eval_on_selector_all('#errs .ecard', "e => e.map(x => [x.dataset.code, (x.querySelector('.ef a') || {}).href || null, (x.querySelector('.ef a') || {}).textContent || null])")
        href = src[l]['err_heic_url']  # absolute noclaudkit.com URL as in the JSON
        ok(pre + f'HEIC card {l}: link to the HEIC -> JPG converter, other unsupported files without it',
           info == [['UNSUPPORTED_IMAGE', href, src[l]['err_heic_link_text']], ['UNSUPPORTED_IMAGE', None, None]], info)
        fx = await pg.eval_on_selector('#errs .ecard:nth-child(1) .ef', 'e => e.textContent')
        want_fx = src[l]['err_heic_fix'].replace('{link}', src[l]['err_heic_link_text'])
        ok(pre + f'HEIC card {l}: fix text keeps Nathan\'s string' + (' with U+00A0' if l == 'ru' else ''),
           fx == want_fx and (l != 'ru' or '\xa0' in fx), (fx, want_fx))
        await pg.close()

    # ---- Nathan 20.10 strings: FAQ HEIC link, broken image hint, every-N error, Other PDF tools H2, plurals, huge spec ----
    for lang, l in (('', 'en'), ('ru/', 'ru'), ('zh/', 'zh')):
        pg = await newpage(ctx); w = Watch(pg, bname); watches.append(w)
        await pg.goto(B + lang + 'jpg-to-pdf.html'); await ready(pg)
        a = await pg.evaluate("""() => [...document.querySelectorAll('.faq .collapse-content a')].map(x => [x.getAttribute('href'), x.textContent])""")
        ld = await pg.evaluate("""() => [...document.querySelectorAll('script[type="application/ld+json"]')].map(x => x.textContent).join('')""")
        want = [[src[l]['err_heic_url'], src[l]['err_heic_link_text'].replace('\xa0', ' ')]]
        ok(pre + f'jpg FAQ {l}: converter name linked to heic-to-jpg, FAQPage text without the URL', a == want and 'heic-to-jpg' not in ld and want[0][1] in ld, (a, want))
        h2 = await pg.evaluate("""() => { const hs = [...document.querySelectorAll('main h2, h2')].map(h => h.id); const s = document.querySelector('section.others');
            return [hs.indexOf('faq-h') < hs.indexOf('others-h'), s && s.querySelector('h2').textContent, s && s.querySelector('h2').className === document.getElementById('faq-h').className,
                    s ? [...s.querySelectorAll('.mcard')].map(x => x.getAttribute('href')) : null]; }""")
        ok(pre + f'jpg-to-pdf {l}: H2 other_tools after the FAQ, FAQ heading style, 3 other tools', h2[0] and h2[1] == src[l]['other_tools'] and h2[2] and len(h2[3]) == 3 and not any('jpg-to-pdf' in x for x in h2[3]), h2)
        await pg.set_input_files('#files', [FX + 'broken.jpg']); await pg.wait_for_selector('#errs .ecard'); await pg.wait_for_selector('#proc', state='hidden')
        tx = (await pg.inner_text('#errs .ecard .ef')).replace('\xa0', ' ')
        ok(pre + f'IMAGE_INVALID {l}: err_image_broken_fix', await pg.eval_on_selector('#errs .ecard', 'e=>e.dataset.code') == 'IMAGE_INVALID' and tx == src[l]['err_image_broken_fix'].replace('\xa0', ' '), tx)
        await pg.close()
        pg = await newpage(ctx); w = Watch(pg, bname); watches.append(w)
        await pg.goto(B + lang); await pg.wait_for_load_state('load')
        ok(pre + f'hub {l}: no Other PDF tools H2', await pg.locator('section.others').count() == 0 and await pg.locator('.modecards .mcard').count() == 4)
        await pg.close()
        pg = await newpage(ctx); w = Watch(pg, bname); watches.append(w)
        await pg.goto(B + lang + 'split-pdf.html'); await ready(pg)
        await pg.set_input_files('#files', [FX + 'long24.pdf']); await loaded(pg)
        await pg.check('input[name=smode][value=every]')
        want = src[l]['err_every_n'].replace('{pageCount}', '24').replace('\xa0', ' ')
        got = []
        for v in ('0', '2.5'):
            await pg.fill('#every', v); got.append((await pg.inner_text('#rerr')).replace('\xa0', ' '))
        await pg.fill('#every', '1'); r1 = (await pg.inner_text('#sres')).replace('\xa0', ' ')
        ev = src[l]['every_result']; ev = ev if isinstance(ev, dict) else {'other': ev}; w1 = ev.get('one', ev.get('other')).replace('{n}', '24').replace('{k}', '1').replace('\xa0', ' ')
        ok(pre + f'every N {l}: 0 and 2.5 -> err_every_n, every 1 -> every_result plural for k=1', got == [want, want] and r1 == w1, (got, want, r1, w1))
        await pg.check('input[name=smode][value=ranges]'); await pg.fill('#ranges', ','.join(['1-24'] * 300))
        c, tx, dis = await rerr()
        ok(pre + f'split {l}: duplicated huge spec (core TOO_MANY_PAGES) -> err_split_total_pages', c == 'SPLIT_TOTAL_PAGES' and dis and src[l]['err_split_total_pages'].replace('\xa0', ' ') in tx, (c, tx))
        await pg.close()
        pg = await newpage(ctx); w = Watch(pg, bname); watches.append(w)
        await pg.goto(B + lang + 'merge-pdf.html'); await ready(pg)
        await pg.set_input_files('#files', [FX + f'm{k:02d}.pdf' for k in range(1, 52)]); await loaded(pg)
        tx = (await pg.inner_text('#errs .ecard .ef')).replace('\xa0', ' ')
        fx = src[l]['err_too_many_files_fix']; fx = fx if isinstance(fx, dict) else {'other': fx}; w1 = fx.get('one', fx.get('other')).replace('{n}', '1').replace('\xa0', ' ')
        ok(pre + f'TOO_MANY_FILES {l}: fix text plural for 1 file not added', tx == w1, (tx, w1))
        await pg.close()

    # ---- sitemap: 21 URLs, each with en/ru/zh/x-default alternates ----
    pg = await newpage(ctx); w = Watch(pg, bname); watches.append(w)
    r = await pg.goto(B + 'sitemap.xml'); sx = await r.text()
    locs = re.findall(r'<loc>([^<]+)</loc>', sx)
    ok(pre + 'sitemap: 21 unique URLs, 4 hreflang alternates each', len(locs) == 21 == len(set(locs)) and sx.count('hreflang=') == 21 * 4, (len(locs), sx.count('hreflang=')))
    await pg.close()

    # ---- encrypted on split page ----
    pg = await newpage(ctx, 375, 800); w = Watch(pg, bname); watches.append(w)
    await pg.goto(B + 'ru/split-pdf.html'); await ready(pg)
    await pg.set_input_files('#files', [FX + 'bank-statement.pdf']); await pg.wait_for_selector('#errs .ecard')
    await pg.wait_for_function('document.getElementById("proc").hidden')
    ok(pre + 'encrypted: error card, file not loaded', await pg.eval_on_selector('#errs .ecard', 'e=>e.dataset.code') == 'PDF_ENCRYPTED' and await pg.is_hidden('#work'))
    ok(pre + 'encrypted: ru text', 'bank-statement.pdf защищён паролем' in await pg.inner_text('#errs'), await pg.inner_text('#errs'))
    await pg.screenshot(path=f'{SHOTS}/{bname}-07-encrypted-ru-375.png', full_page=True)
    await pg.close()

    # ---- TOO_LARGE reason 'decompressed' (core 500 MB unpack cap): the real worker is wrapped so it reports
    # that error for invoice.pdf at add time and for the 2nd file at merge time; plain TOO_LARGE keeps err_total_large ----
    real_worker = open(os.path.join(HERE, '..', '..', 'assets', 'worker.js')).read()
    shim = real_worker + """
;(() => { const real = self.onmessage; self.onmessage = (ev) => { const m = ev.data;
  const err = (details) => self.postMessage({ id: m.id, error: { code: 'TOO_LARGE', details } });
  if (m.op === 'info' && m.file && m.file.name === 'invoice.pdf') return err({ reason: 'decompressed' });
  if (m.op === 'build' && self.name !== 'x') { const ids = [...new Set(m.pages.map((p) => p.f))];
    return err(ids.length > 1 ? { reason: 'decompressed', fileId: ids[1] } : {}); }
  return real(ev); }; })();"""
    for lang, want_add, want_fix in (('', 'invoice.pdf is too complex to process', 'Re-save or compress it in another PDF app'),
                                     ('ru/', 'invoice.pdf: слишком сложный для обработки', 'Пересохраните или сожмите его'),
                                     ('zh/', 'invoice.pdf 过于复杂，无法处理', '请在其他 PDF 程序中重新保存')):
        pg = await newpage(ctx); w = Watch(pg, bname); watches.append(w)
        await pg.route('**/pdf/assets/worker.js', lambda r: r.fulfill(status=200, content_type='text/javascript', body=shim))
        await pg.goto(B + lang + 'merge-pdf.html'); await ready(pg)
        await pg.set_input_files('#files', [FX + 'contract.pdf', FX + 'invoice.pdf', FX + 'scan.pdf']); await loaded(pg)
        txt = (await pg.inner_text('#errs')).replace('\u00a0', ' ')
        codes = await pg.eval_on_selector_all('#errs .ecard', 'e => e.map(x => x.dataset.code)')
        ok(pre + f'decompressed {lang or "en/"}: add-time card names the file with the unpack text', codes == ['TOO_LARGE'] and want_add in txt and want_fix in txt and '100' not in txt, (codes, txt))
        n = await pg.locator('#pages > .pc').count()
        await pg.click('#errs .ecard button'); await pg.click('#go'); await pg.wait_for_selector('#errs .ecard', timeout=15000)
        txt = (await pg.inner_text('#errs')).replace('\u00a0', ' ')
        ok(pre + f'decompressed {lang or "en/"}: merge-time card names the 2nd file (scan.pdf), list kept', 'scan.pdf' in txt and want_fix in txt and await pg.locator('#pages > .pc').count() == n == 6, (txt, n))
        if lang == '':
            await pg.screenshot(path=f'{SHOTS}/{bname}-08-decompressed-en-1280.png')
            await pg.click('#errs .ecard button')
            for k in (5, 4, 3): await pg.locator('#pages > .pc').nth(k).locator('[data-act=del]').click()
            await pg.click('#go'); await pg.wait_for_selector('#errs .ecard', timeout=15000)
            txt = (await pg.inner_text('#errs')).replace('\u00a0', ' ')
            ok(pre + 'plain TOO_LARGE (no reason) keeps the total-size card', 'too complex' not in txt and await pg.eval_on_selector('#errs .ecard', 'e=>e.dataset.code') == 'TOO_LARGE', txt)
        await pg.close()

    # ---- images (en): GPS JPEG, PNGs, too large, wrong type; A4 and fit ----
    pg = await newpage(ctx); w = Watch(pg, bname); watches.append(w)
    await pg.goto(B + 'jpg-to-pdf.html'); await ready(pg)
    await pg.set_input_files('#files', [FX + x for x in ('photo-gps.jpg', 'plain.png', 'meta.png', 'huge.jpg', 'notes.txt')]); await loaded(pg)
    codes = await pg.eval_on_selector_all('#errs .ecard', 'e => e.map(x => x.dataset.code)')
    ok(pre + 'images: IMAGE_TOO_LARGE + wrong type cards, 3 images kept', codes == ['IMAGE_TOO_LARGE', 'UNSUPPORTED_IMAGE'] and await pg.locator('#pages > .pc').count() == 3, codes)
    ok(pre + 'images: metadata notice visible', await pg.is_visible('.metanote'))
    await pg.wait_for_timeout(500); await pg.screenshot(path=f'{SHOTS}/{bname}-03-images-en-1280.png', full_page=True)
    await pg.locator('#pages > .pc').nth(1).locator('[data-act=rot]').click()
    await pg.click('#go'); await pg.wait_for_selector('#done:not([hidden])', timeout=30000)
    name, path = await download(pg, tmp, 'img-fit'); v = verify(path)
    ok(pre + 'images fit: images.pdf, 3 pages, 2nd rotated, no EXIF/GPS, no Info', name == 'images.pdf' and len(v['pages']) == 3 and v['pages'][1]['rot'] == 90 and not v['exif'] and not v['info'], v)
    await pg.click('#again'); await pg.select_option('#psize', 'a4')
    await pg.click('#go'); await pg.wait_for_selector('#done:not([hidden])', timeout=30000)
    name, path = await download(pg, tmp, 'img-a4'); v = verify(path)
    ok(pre + 'images A4: pages 595x842, no EXIF/GPS', all((x['w'], x['h']) == (595, 842) for x in v['pages']) and not v['exif'], v['pages'])
    await pg.close()

    # ---- 50 MP header limit (IMAGE_TOO_LARGE), en/ru/zh error cards ----
    for l in ('en', 'ru', 'zh'):
        pg = await newpage(ctx); w = Watch(pg, bname); watches.append(w)
        await pg.goto(B + ('' if l == 'en' else l + '/') + 'jpg-to-pdf.html'); await ready(pg)
        await pg.set_input_files('#files', [FX + x for x in ('edge-50mp.jpg', 'over-50mp.jpg', 'sneaky-sof.jpg', 'over-50mp.png', 'dup-ihdr.png', 'plain.png')]); await loaded(pg)
        codes = await pg.eval_on_selector_all('#errs .ecard', 'e => e.map(x => x.dataset.code)')
        tx = (await pg.inner_text('#errs')).replace('\xa0', ' ')
        want = [src[l]['err_image_too_large'].replace('{file}', n).replace('\xa0', ' ') for n in ('over-50mp.jpg', 'sneaky-sof.jpg', 'over-50mp.png')]
        fix = src[l]['err_image_too_large_fix'].replace('\xa0', ' ')
        n = await pg.locator('#pages > .pc').count()
        ok(pre + f'50 MP {l}: 50,000,000 px added, 50,000,001 px / 2nd SOF / PNG over -> IMAGE_TOO_LARGE cards, dup IHDR -> IMAGE_INVALID',
           codes == ['IMAGE_TOO_LARGE', 'IMAGE_TOO_LARGE', 'IMAGE_TOO_LARGE', 'IMAGE_INVALID'] and all(x in tx for x in want) and tx.count(fix) == 3 and n == 2, (codes, n, tx))
        if l == 'en': await pg.screenshot(path=f'{SHOTS}/{bname}-09-image-50mp-en-1280.png', full_page=True)
        await pg.close()

    # ---- cancel during processing (big job) ----
    pg = await newpage(ctx); w = Watch(pg, bname); watches.append(w)
    await pg.goto(B + 'merge-pdf.html'); await ready(pg)
    await pg.set_input_files('#files', [FX + 'long24.pdf'] * 20); await loaded(pg)
    await pg.click('#go')
    try:
        await pg.wait_for_selector('#proc:not([hidden])', timeout=2000); await pg.click('#pcancel', timeout=2000)
        await pg.wait_for_selector('#work:not([hidden])', timeout=10000)
        ok(pre + 'processing: Cancel returns to the list, files kept', await pg.locator('#pages > .pc').count() == 480)
    except Exception as e:
        ok(pre + 'processing: Cancel (job finished before cancel could be clicked)', await pg.is_visible('#done'), str(e)[:100])
    await pg.close()

    # ---- CLS at 320 when an error card appears (Olivia M1): neighbours must not move ----
    # Playwright's set_input_files marks shifts as hadRecentInput, so the raw sum of all entries is used (stricter).
    for page_, first, bad, code in (('jpg-to-pdf.html', ['plain.png'], ['over-50mp.jpg'], 'IMAGE_TOO_LARGE'), ('merge-pdf.html', ['m01.pdf', 'm02.pdf'], ['broken.pdf'], 'PDF_INVALID')):
        pg = await newpage(ctx, 320, 800); w = Watch(pg, bname); watches.append(w)
        await pg.goto(B + page_); await ready(pg)
        await pg.set_input_files('#files', [FX + f for f in first]); await loaded(pg); await pg.wait_for_timeout(500)
        await pg.evaluate("""() => { window.__cls = 0; const top = (s) => Math.round(document.querySelector(s).getBoundingClientRect().top + scrollY);
            window.__pos = () => [top('#work'), top('#pages > .pc')]; window.__p0 = window.__pos();
            if (window.PerformanceObserver && PerformanceObserver.supportedEntryTypes.includes('layout-shift'))
                new PerformanceObserver((l) => { for (const e of l.getEntries()) window.__cls += e.value; }).observe({ type: 'layout-shift' }); else window.__cls = null; }""")
        await pg.set_input_files('#files', [FX + f for f in bad]); await pg.wait_for_selector(f'#errs .ecard[data-code={code}]', timeout=20000); await pg.wait_for_timeout(800)
        cls, p0, p1 = await pg.evaluate('[window.__cls, window.__p0, window.__pos()]')
        ok(pre + f'CLS 320 {page_} {code}: work area does not move' + ('' if cls is None else ', CLS < 0.01'), p0 == p1 and (cls is None or cls < 0.01), (cls, p0, p1))
        await pg.close()

    # ---- <600 error stack with 3 cards (Olivia 952e205 F1-F3): footer reachable, focus not obscured, Undo above the stack, 40vh when h<420 ----
    bad3 = [{'name': f'broken-{i}.pdf', 'mimeType': 'application/pdf', 'buffer': open(FX + 'broken.pdf', 'rb').read()} for i in (1, 2, 3)]
    for vw, vh in ((320, 800), (568, 320)):
        tag = f'stack {vw}x{vh} 3 cards: '
        pg = await newpage(ctx, vw, vh); w = Watch(pg, bname); watches.append(w)
        await pg.goto(B + 'merge-pdf.html'); await ready(pg)
        await pg.set_input_files('#files', [FX + 'm01.pdf', FX + 'm02.pdf']); await loaded(pg)
        await pg.set_input_files('#files', bad3); await pg.wait_for_selector('#errs .ecard:nth-child(3)', timeout=20000); await pg.wait_for_timeout(400)
        st = await pg.evaluate("""() => { const e = document.getElementById('errs').getBoundingClientRect();
            return { h: e.height, vh: innerHeight, pos: getComputedStyle(errs).position, v: getComputedStyle(document.documentElement).getPropertyValue('--errs-h').trim() }; }""")
        ok(pre + tag + 'stack is fixed and --errs-h is set', st['pos'] == 'fixed' and st['v'] not in ('', '0px'), st)
        if vh < 420: ok(pre + tag + 'stack height <= 40vh', st['h'] <= 0.4 * vh + 0.5, st)
        await pg.evaluate("scrollTo(0, document.documentElement.scrollHeight)"); await pg.wait_for_timeout(200)
        fv = await pg.evaluate("""() => { const f = document.querySelector('footer').getBoundingClientRect(), e = document.getElementById('errs').getBoundingClientRect();
            return [Math.round(f.top), Math.round(f.bottom), Math.round(e.top)]; }""")
        # if the footer is taller than the room above the stack (568x320: 204 px vs 180 px), its end must still clear the stack
        ok(pre + tag + 'footer fully visible above the stack at end of scroll' + (' (footer taller than free area: end clears the stack)' if fv[1] - fv[0] > fv[2] else ''),
           fv[1] <= fv[2] and (fv[0] >= 0 or fv[1] - fv[0] > fv[2]), fv)
        hid = await pg.evaluate("""async () => { const errs = document.getElementById('errs'), bad = [];
            const els = [...document.querySelectorAll('a[href],button,input,select,textarea,summary,[tabindex]:not([tabindex="-1"])')]
                .filter((x) => !x.disabled && !errs.contains(x) && !x.closest('#toast') && x.getClientRects().length && getComputedStyle(x).visibility !== 'hidden');
            for (const x of els) { x.focus(); if (document.activeElement !== x) continue; await new Promise((r) => requestAnimationFrame(() => requestAnimationFrame(r)));
                const r = x.getBoundingClientRect(); if (r.width < 1 || r.height < 1) continue;
                const cx = Math.min(Math.max(r.left + r.width / 2, 0), innerWidth - 1), cy = Math.min(Math.max(r.top + r.height / 2, 0), innerHeight - 1);
                const hit = document.elementFromPoint(cx, cy);
                if (!hit || errs.contains(hit) || r.bottom <= 0 || r.top >= innerHeight) bad.push((x.id || x.tagName) + ':' + (x.getAttribute('aria-label') || x.textContent).trim().slice(0, 30)); }
            return [els.length, bad]; }""")
        ok(pre + tag + f'no focused element is covered by #errs ({hid[0]} checked)', hid[0] > 5 and not hid[1], hid[1][:8])
        await pg.evaluate("scrollTo(0, 0)"); n0 = await pg.locator('#pages > .pc').count()
        await pg.locator('#pages > .pc').nth(0).locator('[data-act=del]').click(); await pg.wait_for_selector('#toast:not([hidden])')
        tv = await pg.evaluate("""() => { const b = document.querySelector('#toast button').getBoundingClientRect(), t = document.getElementById('toast').getBoundingClientRect(),
            e = document.getElementById('errs').getBoundingClientRect(), hit = document.elementFromPoint(b.left + b.width / 2, b.top + b.height / 2);
            return [Math.round(t.bottom), Math.round(e.top), !!(hit && hit.closest('#toast')), t.top >= 0]; }""")
        ok(pre + tag + 'Undo toast is above the stack and hit-testable', tv[0] <= tv[1] and tv[2] and tv[3], tv)
        await pg.click('#toast button', timeout=3000); await pg.wait_for_timeout(150)
        ok(pre + tag + 'Undo click restores the page', await pg.locator('#pages > .pc').count() == n0)
        await pg.close()

    # ---- layout: every page, 320/375/1280, light/dark; header/brand gap ----
    for scheme in ('light', 'dark'):
        c2 = await browser.new_context(color_scheme=scheme); await c2.add_init_script(INIT)
        for path in ('', 'ru/', 'zh/', 'merge-pdf.html', 'ru/split-pdf.html', 'zh/organize-pdf.html', 'ru/jpg-to-pdf.html', 'ru/privacy.html', 'licenses.html', 'zh/licenses.html'):
            for wd in (320, 375, 1280):
                pg = await newpage(c2, wd, 800); w = Watch(pg, bname); watches.append(w)
                await pg.goto(B + path); await pg.wait_for_load_state('load')
                o = await overflow(pg)
                gap = await pg.evaluate("() => { const b = document.querySelector('.brand').getBoundingClientRect(), s = document.querySelector('details.settings summary').getBoundingClientRect(); return [Math.round(s.left - b.right), Math.round(b.height)]; }")
                ok(pre + f'layout {scheme} {wd} /{path}: no h-overflow, brand one line, gap >=16', o <= 0 and gap[0] >= 16 and gap[1] <= 44, (o, gap))
                if path in ('', 'ru/', 'zh/', 'merge-pdf.html', 'ru/split-pdf.html') and (wd != 375 or path == 'ru/'):
                    nm = (path.replace('/', '-').replace('.html', '') or 'en-').strip('-') or 'hub-en'
                    await pg.screenshot(path=f'{SHOTS}/{bname}-{nm}-{wd}-{scheme}.png', full_page=True)
                await pg.close()
        ok(pre + f'no cookies ({scheme})', await c2.cookies() == [])
        await c2.close()
    ok(pre + 'no cookies', await ctx.cookies() == [])
    ext = sum((x.ext for x in watches), []); csp = sum((x.csp for x in watches), []); errs = sum((x.errors for x in watches), []); ng = sum((x.nonget for x in watches), [])
    ok(pre + 'zero external requests', not ext, ext[:5]); ok(pre + 'zero non-GET requests (no uploads)', not ng, ng[:5])
    ok(pre + 'zero CSP violations', not csp, csp[:5]); ok(pre + 'no page errors', not errs, errs[:5])
    await browser.close()

async def main():
    names = sys.argv[1:] or ['chromium', 'firefox', 'webkit']
    os.makedirs(SHOTS, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        async with async_playwright() as p:
            for n in names: await run(n, p, tmp)
    f = [r for r in RES if not r[1]]
    print(f'\n{len(RES) - len(f)}/{len(RES)} passed')
    print(f'harness-only CSP reports during WebKit screenshots (Playwright <style>body {{}}</style>): {len(HARNESS_CSP)}; WebKit <select> engine reports on jpg-to-pdf: {len(ENGINE_CSP)}')
    json.dump([{'test': a, 'pass': b, 'info': str(c)[:300]} for a, b, c in RES], open(f'{SHOTS}/e2e-results.json', 'w'), ensure_ascii=False, indent=1)
    sys.exit(1 if f else 0)
asyncio.run(main())
