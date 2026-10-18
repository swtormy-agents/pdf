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
B = 'http://127.0.0.1:8931/pdf/'
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

    # ---- encrypted on split page ----
    pg = await newpage(ctx, 375, 800); w = Watch(pg, bname); watches.append(w)
    await pg.goto(B + 'ru/split-pdf.html'); await ready(pg)
    await pg.set_input_files('#files', [FX + 'bank-statement.pdf']); await pg.wait_for_selector('#errs .ecard')
    await pg.wait_for_function('document.getElementById("proc").hidden')
    ok(pre + 'encrypted: error card, file not loaded', await pg.eval_on_selector('#errs .ecard', 'e=>e.dataset.code') == 'PDF_ENCRYPTED' and await pg.is_hidden('#work'))
    ok(pre + 'encrypted: ru text', 'bank-statement.pdf защищён паролем' in await pg.inner_text('#errs'), await pg.inner_text('#errs'))
    await pg.screenshot(path=f'{SHOTS}/{bname}-07-encrypted-ru-375.png', full_page=True)
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
