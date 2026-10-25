#!/usr/bin/env python3
"""Generates every page of Local PDF Tools (en at the root, ru/ and zh/ copies) plus sitemap.xml.
Run: python3 tools/gen.py   (re-running without source changes gives zero diff).
Strings: tools/i18n/ (synced from their owners by tools/sync_i18n.py at the start of every run; see that file).
Plain-text strings are HTML-escaped here; U+00A0 appears only in visible text, never in tags, attributes, <title>, meta
or JSON-LD (plain_meta() enforces it)."""
import os,re,json,html,subprocess,sys,hashlib
os.chdir(os.path.join(os.path.dirname(__file__),'..'))
sys.path.insert(0,'tools'); import sync_i18n; sync_i18n.main()

BASE='https://noclaudkit.com/pdf/'
ROOT='/pdf/'
REPO='https://github.com/swtormy-agents/pdf'
CSP="default-src 'none'; script-src 'self'; style-src 'self'; img-src 'self' blob:; worker-src 'self'; base-uri 'none'; form-action 'none'; object-src 'none'"
LANGS=['en','ru','zh']
HREFLANG={'en':'en','ru':'ru','zh':'zh-Hans'}
LANG_NAME={'en':'English','ru':'Русский','zh':'中文'}
LANG_CODE={'en':'EN','ru':'RU','zh':''}
OG_LOCALE={'en':'en_US','ru':'ru_RU','zh':'zh_CN'}
NB='\u00a0'
def load(n): return json.load(open(f'tools/i18n/{n}',encoding='utf-8'))
UI={l:load(f'{l}.json') for l in LANGS}; SEO=load('seo.json'); FAQ=load('faq.json'); PRIV=load('privacy.json'); HDR=load('header.json')
T={l:{**UI[l],**HDR[l]} for l in LANGS}

# page file -> (seo key, app mode, faq key)
TOOLS=[('index.html','hub','merge'),('merge-pdf.html','merge','merge'),('split-pdf.html','split','split'),('organize-pdf.html','organize','organize'),('jpg-to-pdf.html','jpg','images')]
MODE_PAGE={'merge':'merge-pdf.html','split':'split-pdf.html','organize':'organize-pdf.html','images':'jpg-to-pdf.html'}
MODE_KEY={'merge':'mode_merge','split':'mode_split','organize':'mode_reorder','images':'mode_images'}
DOC=['privacy.html','licenses.html']

e=lambda s:html.escape(str(s),quote=True)
RU_SHORT='не|и|с|в|на|к|о|у|а|из|за|по|от|до|я|ни|но|же|ли'
def ru_nbsp(s): return re.sub(r'(?<![\w\u0400-\u04ff])('+RU_SHORT+r') ',lambda m:m.group(1)+NB,s,flags=re.I)
NBH='\u2011'
def vis(lang,s):  # visible text: ru gets U+00A0 after short words and U+2011 in «PDF-…» (sources for head/meta are plain-space)
    return ru_nbsp(s).replace('PDF-','PDF'+NBH) if lang=='ru' else s
def plain(s): return s.replace(NB,' ').replace('\u2011','-')
def lp(l): return '' if l=='en' else l+'/'
def url(l,p): return BASE+lp(l)+('' if p=='index.html' else p)
def rel(p): return './' if p=='index.html' else p
OG_SEP={'en':'. ','ru':'. ','zh':'。'}
def og_img(lang):  # absolute, same BASE as canonical; ?v= = sha256[:8] of the committed PNG (tools/scripts/og.py), as in the converter
    with open(f'assets/og/og-{lang}.png','rb') as f: b=f.read()
    assert b[:8]==b'\x89PNG\r\n\x1a\n' and int.from_bytes(b[16:20],'big')==1200 and int.from_bytes(b[20:24],'big')==630, f'og-{lang}.png must be a 1200x630 PNG'
    return BASE+f'assets/og/og-{lang}.png?v={hashlib.sha256(b).hexdigest()[:8]}'
def og_alt(lang):  # plain text of the OG image: hub H1 + promise line (both approved UI strings)
    a=plain(T[lang]['h1_home']).strip()
    return a+('' if a[-1:] in '.。!?！？' else OG_SEP[lang])+plain(T[lang]['lede']).strip()

# ---------- icons (from the approved prototype, design/pdf-tool/proto/gen.py) ----------
def svg(body,cls='size-5',sw='2',fill='none'): return f'<svg class="{cls}" viewBox="0 0 24 24" aria-hidden="true" focusable="false" fill="{fill}" stroke="currentColor" stroke-width="{sw}" stroke-linecap="round" stroke-linejoin="round">{body}</svg>'
LOGO='<svg viewBox="0 0 28 28" aria-hidden="true" focusable="false" class="size-7 shrink-0 text-primary" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="1" y="1" width="26" height="26" rx="7"/><path d="M9 7h7l4 4v10H9z"/><path d="M16 7v4h4"/></svg>'
GLOBE='<svg class="ico-globe size-5 shrink-0" viewBox="0 0 24 24" aria-hidden="true" focusable="false" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><path d="M2 12h20M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z"/></svg>'
CHEV_S='<svg class="ico-chev hidden sm:block size-3.5 shrink-0 opacity-70" viewBox="0 0 24 24" aria-hidden="true" focusable="false" fill="none" stroke="currentColor" stroke-width="2"><path d="m6 9 6 6 6-6"/></svg>'
CHECK='<svg class="ms-auto size-4 shrink-0" viewBox="0 0 24 24" aria-hidden="true" focusable="false" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><path d="M5 12.5l4.5 4.5L19 7"/></svg>'
UPL=svg('<path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8z"/><path d="M14 3v5h5M12 18v-6M9 15l3-3 3 3"/>','upl size-9 text-primary','1.8')
INFO=svg('<circle cx="12" cy="12" r="9"/><path d="M12 11v5M12 8v.5"/>','size-5 shrink-0 text-info')
OK=svg('<circle cx="12" cy="12" r="9"/><path d="m8 12 3 3 5-6"/>','size-6 shrink-0 text-success')

def pg(x,y,w=34,h=44,cls='pg',lines=4):
    r=f'<rect class="{cls}" x="{x}" y="{y}" width="{w}" height="{h}" rx="3"/>'
    for i in range(lines):
        ww=(w-12)*(0.6 if i==0 else (0.85 if i%2 else 1))
        r+=f'<rect class="{"ln2" if i==0 else "ln"}" x="{x+6}" y="{y+8+i*8}" width="{ww:g}" height="3" rx="1.5"/>'
    return r
def pdfbadge(x,y): return f'<rect class="pdf" x="{x}" y="{y}" width="22" height="12" rx="3"/><rect class="pdft" x="{x+5}" y="{y+5}" width="12" height="2" rx="1"/>'
def SV(body,vb='0 0 120 80'): return f'<svg class="ill" viewBox="{vb}" aria-hidden="true" focusable="false">{body}</svg>'
ILLS={
 'merge':SV(pg(8,6)+pg(14,12)+pg(78,18,w=34,h=50,lines=5)+'<path class="acs" d="M52 38h18M64 32l6 6-6 6"/>'+pg(20,22,lines=3)+pdfbadge(84,60)),
 'split':SV(pg(8,16,w=34,h=50,lines=5)+'<path class="acs" d="M50 41h12M56 28v26"/><path class="acs" d="M62 34l6-6M62 48l6 6"/>'+pg(74,4,w=30,h=34,lines=3)+pg(74,44,w=30,h=34,lines=3)),
 'organize':SV(pg(10,18)+pg(46,18)+pg(82,18)+'<rect class="ac" x="46" y="18" width="34" height="5" rx="2"/><path class="acs" d="M27 70c0 6 40 6 40 0M63 66l4 4-4 4"/><path class="acs" d="M63 12c0-6-40-6-36 0M31 8l-4 4 4 4"/>'),
 'images':SV('<rect class="pg" x="6" y="10" width="40" height="32" rx="4"/><rect class="sky" x="10" y="14" width="32" height="24" rx="2"/><path class="hill" d="M10 38l10-12 8 8 5-5 9 9z"/><circle class="ac" cx="35" cy="20" r="3"/><rect class="pg" x="14" y="40" width="40" height="32" rx="4"/><rect class="sky" x="18" y="44" width="32" height="24" rx="2"/><path class="hill" d="M18 68l10-12 8 8 5-5 9 9z"/><path class="acs" d="M62 41h12M68 35l6 6-6 6"/>'+pg(80,16,w=34,h=50,lines=5)+pdfbadge(86,58)),
}
HERO_ART='<svg class="ill art" viewBox="0 0 320 240" aria-hidden="true" focusable="false"><rect class="sky" x="20" y="20" width="280" height="200" rx="28"/>'+pg(54,58,w=70,h=92,lines=7)+pg(70,74,w=70,h=92,lines=7)+pg(86,90,w=70,h=92,lines=7)+'<path class="acs" d="M168 136h34M190 124l12 12-12 12"/>'+pg(214,70,w=76,h=118,lines=9)+'<rect class="pdf" x="236" y="168" width="40" height="20" rx="5"/><circle class="ac" cx="262" cy="52" r="6"/><circle class="ln2" cx="48" cy="196" r="9"/></svg>'

# ---------- head + header (selectors v2 variant B, markup as in the converter) ----------
def jsonld(objs):
    out=''
    for d in objs:
        j=json.dumps(d,ensure_ascii=False).replace('<','\\u003c').replace('>','\\u003e').replace('&','\\u0026')
        out+=f'<script type="application/ld+json">{j}</script>\n'
    return out
def head(L,lang,page,title,desc,ld='',bodyattrs='',doc=False):
    t=T[lang]; P='' if lang=='en' else '../'
    alts=''.join(f'<link rel="alternate" hreflang="{HREFLANG[l]}" href="{url(l,page)}">' for l in LANGS)+f'<link rel="alternate" hreflang="x-default" href="{url("en",page)}">'
    def li(l):
        cur=l==lang
        tail=CHECK if cur else (f'<span class="ms-auto text-xs text-base-content/70">{LANG_CODE[l]}</span>' if LANG_CODE[l] else '')
        return (f'<li><a class="min-h-[44px] items-center'+(' menu-active' if cur else '')+f'" href="{ROOT}{lp(l)}{"" if page=="index.html" else page}" hreflang="{HREFLANG[l]}" lang="{HREFLANG[l]}"'
                +(' aria-current="page"' if cur else '')+f'>{e(LANG_NAME[l])}{" "+tail if tail else ""}</a></li>')
    radios=''.join(f'<input class="join-item btn btn-ghost flex-1 min-h-11 theme-opt" type="radio" name="theme" value="{v}" aria-label="{e(t[v])}" title="{e(t[v])}"'+(' checked' if v=='system' else '')+'>' for v in ('system','light','dark'))
    aria=''.join(f' data-l-{k}="{e(t["settings_aria_"+k])}"' for k in ('system','light','dark','mobile'))
    nav=(f'<details class="settings dropdown dropdown-end"><summary class="btn btn-outline border-base-300 min-h-11 min-w-11 px-2.5 gap-1.5 font-medium whitespace-nowrap" aria-label="{e(t["settings_aria_system"])}" aria-haspopup="true" aria-expanded="false"{aria}>'
         f'{GLOBE}<span lang="{HREFLANG[lang]}">{e(t["lang_code"])}</span><span class="sep hidden sm:block w-px h-6 bg-base-300 mx-1" aria-hidden="true"></span><span class="ico-theme hidden sm:block size-5" aria-hidden="true"></span>{CHEV_S}</summary>'
         '<div class="dropdown-content z-20 mt-2 w-56 rounded-box border border-base-300 bg-base-100 p-2 shadow-lg">'
         f'<nav aria-labelledby="lang-h"><p id="lang-h" class="px-3 pt-2 pb-1 text-xs font-medium text-base-content/80">{e(t["lang_nav"])}</p><ul class="menu w-full p-0">'+''.join(li(l) for l in LANGS)+'</ul></nav>'
         f'<div class="theme-sec hidden sm:block"><hr class="my-1.5 mx-1 border-base-300"><fieldset><legend id="theme-h" class="px-3 pt-2 pb-1 text-xs font-medium text-base-content/80">{e(t["theme"])}</legend>'
         f'<div class="join flex w-full p-0.5 border border-base-300 rounded-field" role="radiogroup" aria-labelledby="theme-h">{radios}</div></fieldset></div></div></details>')
    zh_meta = ('<meta name="applicable-device" content="pc,mobile">\n'
               '<meta http-equiv="Cache-Control" content="no-transform">\n'
               '<meta http-equiv="Content-Language" content="zh-CN">\n') if lang == 'zh' else ''
    return f'''<!doctype html><html lang="{HREFLANG[lang]}"><head><meta charset="utf-8">
<meta http-equiv="Content-Security-Policy" content="{CSP}">
<meta name="referrer" content="no-referrer">
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
{zh_meta}<title>{e(plain(title))}</title><meta name="description" content="{e(plain(desc))}">
<link rel="canonical" href="{url(lang,page)}">
{alts}
<meta property="og:type" content="website"><meta property="og:site_name" content="Local PDF Tools"><meta property="og:locale" content="{OG_LOCALE[lang]}"><meta property="og:title" content="{e(plain(title))}"><meta property="og:description" content="{e(plain(desc))}"><meta property="og:url" content="{url(lang,page)}">
<meta property="og:image" content="{og_img(lang)}"><meta property="og:image:width" content="1200"><meta property="og:image:height" content="630"><meta property="og:image:type" content="image/png"><meta property="og:image:alt" content="{e(og_alt(lang))}">
<meta name="twitter:card" content="summary_large_image"><meta name="twitter:image" content="{og_img(lang)}"><meta name="twitter:image:alt" content="{e(og_alt(lang))}">
<meta name="color-scheme" content="light dark">
{ld}<script src="{P}theme.js"></script><link rel="icon" href="{P}favicon.svg"><link rel="stylesheet" href="{P}build/app.css"></head><body class="min-h-screen flex flex-col bg-base-100 text-base-content antialiased{' doc' if doc else ''}"{bodyattrs}>
<header class="top bg-base-100 border-b border-base-300"><div class="navbar mx-auto max-w-5xl px-3 min-[360px]:px-4 sm:px-6 gap-2 min-h-16">
<div class="navbar-start min-w-0 w-auto grow"><a class="brand flex items-center gap-2 min-h-11 font-semibold text-sm sm:text-lg whitespace-nowrap" href="./" translate="no">{LOGO}<span>Local{NB}PDF{NB}Tools</span></a></div>
<div class="navbar-end w-auto">{nav}</div></div></header>
<main id="main" class="mx-auto w-full max-w-5xl px-4 sm:px-6 py-8 sm:py-12 grow">
'''

def foot(lang,page):
    t=T[lang]
    links=[(ROOT+lp(lang),t['f_pdf'],page=='index.html'),('/image-converter/'+lp(lang),t['f_conv'],False),('privacy.html',t['f_priv'],page=='privacy.html'),
           (REPO,t['f_src'],False),(REPO+'/issues',t['f_contact'],False),('licenses.html',t['f_lic'],page=='licenses.html')]
    return (f'</main>\n<footer class="bg-base-200 mt-12"><div class="footer sm:footer-horizontal mx-auto max-w-5xl px-4 sm:px-6 py-6 text-base-content"><div class="max-w-xl text-sm space-y-1"><p>{e(t["foot"])}</p><p>{e(t["legal"])}</p></div><ul class="flinks flex flex-wrap gap-x-4">'
            +''.join(f'<li><a class="link link-hover min-h-11 min-w-11 inline-flex items-center justify-center whitespace-nowrap" href="{h}"'+(' aria-current="page"' if cur else '')+f'>{e(x)}</a></li>' for h,x,cur in links)+'</ul></div></footer></body></html>\n')

# ---------- tool section ----------
def tabs(lang,mode):
    t=T[lang]
    return (f'<nav class="modetabs tabs tabs-box mt-6" aria-label="{e(t["aria_modes"])}">'
            +''.join(f'<a class="tab min-h-11'+(' tab-active' if m==mode else '')+f'" href="{p}"'+(' aria-current="page"' if m==mode else '')+f'>{e(t[MODE_KEY[m]])}</a>' for m,p in MODE_PAGE.items())+'</nav>\n')
def modecards(lang,skip=None):
    t=T[lang]
    return ('<ul class="modecards" role="list">'+''.join(
        f'<li><a class="mcard" href="{p}"><span class="pv">{ILLS[m]}</span><span class="tx"><span class="mt">{e(t[MODE_KEY[m]])}</span><span class="md">{e(t[MODE_KEY[m]+"_desc"])}</span></span></a></li>' for m,p in MODE_PAGE.items() if m!=skip)+'</ul>\n')
def dropzone(lang,mode):
    t=T[lang]
    if mode=='images': title,hint,btn,acc,mult=t['drop_img'],t['drop_hint_img'],t['choose_files'],'image/jpeg,image/png',True
    elif mode=='split': title,hint,btn,acc,mult=t['drop_pdf_one'],t['drop_hint_pdf_one'],t['choose_file'],'application/pdf,.pdf',False
    else: title,hint,btn,acc,mult=t['drop_pdf'],t['drop_hint_pdf'],t['choose_files'],'application/pdf,.pdf',True
    meta=f'<span class="dz-meta text-sm text-base-content/80">{e(t["meta_notice"])}</span>' if mode=='images' else ''
    return (f'<label class="drop" id="drop" for="files"><input class="sr-only" id="files" name="files" type="file"{" multiple" if mult else ""} accept="{acc}">{UPL}'
            f'<span class="dz-t">{e(title)}</span><span class="dz-h">{e(hint)}</span>{meta}<span class="btn btn-primary min-h-11 px-5 pointer-events-none" aria-hidden="true">{e(btn)}</span></label>\n')
def app(lang,mode,hub=False):
    t=T[lang]
    dz=dropzone(lang,mode)
    size=(f'<label class="psize flex items-center gap-2 text-sm"><span>{e(t["page_size"])}</span><select id="psize" name="page-size" class="select select-sm min-h-11 w-auto">'
          f'<option value="fit">{e(t["page_size_fit"])}</option><option value="a4">{e(t["page_size_a4"])}</option></select></label>') if mode=='images' else ''
    metanote=f'<p class="metanote">{INFO}<span>{e(t["meta_notice"])}</span></p>' if mode=='images' else ''
    hint=f'<p class="rhint hidden sm:block text-sm text-base-content/80 mt-2">{e(t["reorder_hint"])}</p>' if mode in('merge','organize','images') else ''
    splitopts=''
    if mode=='split':
        splitopts=(f'<div class="filerow"><div class="min-w-0"><p class="fname" id="sfname"></p><p class="fsub text-sm text-base-content/80" id="sfsub"></p></div><button type="button" class="btn btn-outline min-h-11" id="replace">{e(t["replace_file"])}</button></div>'
          f'<fieldset class="sopts card card-border bg-base-100 mt-4 p-2 sm:p-4"><legend class="sr-only">{e(t["aria_split"])}</legend>'
          f'<div class="opt"><label class="optl"><input type="radio" class="radio radio-primary" name="smode" value="ranges" checked aria-describedby="sd-ranges"><span class="font-semibold">{e(t["split_ranges"])}</span></label><p class="sdesc text-sm text-base-content/80 ms-9" id="sd-ranges">{e(t["split_ranges_desc"])}</p>'
          f'<div class="optb" data-for="ranges"><label class="block text-sm font-medium mt-2" for="ranges">{e(t["range_label"])}</label><input class="input w-full max-w-xs min-h-11 mt-1" id="ranges" name="ranges" type="text" inputmode="text" autocomplete="off" spellcheck="false" placeholder="{e(t["ph_range"])}" aria-describedby="rhint rerr"><p class="text-sm text-base-content/80 mt-1" id="rhint">{e(t["range_hint"])}</p><p class="rerr text-sm text-error mt-1" id="rerr" hidden></p></div></div>'
          f'<div class="opt"><label class="optl"><input type="radio" class="radio radio-primary" name="smode" value="every" aria-describedby="sd-every"><span class="font-semibold">{e(t["split_every"])}</span></label><p class="sdesc text-sm text-base-content/80 ms-9" id="sd-every">{e(t["split_every_desc"])}</p>'
          f'<div class="optb" data-for="every" hidden><label class="block text-sm font-medium mt-2" for="every">{e(t["every_label"])}</label><input class="input w-28 min-h-11 mt-1" id="every" name="every" type="number" inputmode="numeric" min="1" step="1" value="1" autocomplete="off"></div></div>'
          f'<div class="opt"><label class="optl"><input type="radio" class="radio radio-primary" name="smode" value="extract" aria-describedby="sd-extract"><span class="font-semibold">{e(t["split_extract"])}</span></label><p class="sdesc text-sm text-base-content/80 ms-9" id="sd-extract">{e(t["split_extract_desc"])}</p>'
          f'<div class="optb" data-for="extract" hidden><p class="text-sm text-base-content/80 mt-2">{e(t["extract_hint"])}</p><p class="text-sm font-medium mt-1" id="xcount"></p></div></div>'
          f'<p class="sres" id="sres" aria-live="polite"></p><p class="sr-only" id="rlive" aria-live="polite"></p></fieldset>')
    toolbar=('' if mode=='split' else
          f'<div class="tbar"><p class="counts" id="counts"></p><div class="tbtn">{size}<button type="button" class="btn btn-outline min-h-11" id="add">{e(t["add_files"])}</button><button type="button" class="btn btn-outline min-h-11" id="clear">{e(t["clear"])}</button></div></div>{metanote}')
    return (f'<section class="app" id="app" data-mode="{mode}" aria-labelledby="h1">'
      f'<div class="errs" id="errs" role="alert"></div>\n'
      +('' if hub else dz)+
      f'<div class="work" id="work" hidden>{toolbar}{splitopts}{hint}<ol class="pages" id="pages"></ol>'
      f'<div class="pbar"><button type="button" class="btn btn-primary min-h-11 px-6" id="go" disabled></button></div></div>\n'
      f'<div class="proc card card-border bg-base-100 p-4 sm:p-6 mt-6" id="proc" hidden aria-busy="true"><h2 class="text-lg font-semibold" id="ptitle"></h2>'
      f'<progress class="progress progress-primary w-full mt-4" id="pbar" max="100" value="0" aria-labelledby="ptitle"></progress><p class="mt-2 tabular-nums" id="ptext"></p>'
      f'<p class="text-sm text-base-content/80 mt-2">{e(t["proc_note"])}</p><div class="mt-4"><button type="button" class="btn btn-outline min-h-11" id="pcancel">{e(t["proc_cancel"])}</button></div></div>\n'
      f'<div class="done" id="done" hidden><div class="alert alert-success alert-outline mt-6" role="status">{OK}<div><p class="font-semibold">{e(t["done"])}</p><p class="text-sm" id="dtext"></p></div></div>'
      f'<div class="card card-border bg-base-100 p-4 sm:p-6 mt-4"><p class="font-semibold break-words" id="dname"></p><div class="acts"><a class="btn btn-primary min-h-11 px-6" id="dl" href="#" download></a>'
      f'<button type="button" class="btn btn-outline min-h-11" id="again">{e(t["change_order"])}</button><button type="button" class="btn btn-outline min-h-11" id="restart">{e(t["start_over"])}</button></div></div></div>\n'
      f'<p class="sr-only" id="live" aria-live="polite"></p><div class="toast toast-center z-30" id="toast" hidden></div>'
      f'<dialog class="modal" id="confirm" aria-labelledby="cft"><div class="modal-box"><h2 class="text-lg font-semibold" id="cft">{e(t["clear_confirm_title"])}</h2><p class="mt-2">{e(t["clear_confirm_text"])}</p>'
      f'<div class="modal-action"><button type="button" class="btn btn-outline min-h-11" id="cfno">{e(t["cancel"])}</button><button type="button" class="btn btn-error min-h-11" id="cfok">{e(t["clear_confirm_ok"])}</button></div></div></dialog>'
      '</section>\n'+(dz if False else ''))

HEIC_HREF='/image-converter/{lp}heic-to-jpg.html'  # verified in swtormy-agents/image-converter main: heic-to-jpg.html, ru/, zh/
def heic_href(lang):
    """Nathan's err_heic_url must point at the same converter page; it is emitted as a same-site path."""
    h=UI[lang]['err_heic_url']; assert h=='https://noclaudkit.com'+HEIC_HREF.format(lp=lp(lang)), f'err_heic_url mismatch in {lang}'
    return h  # absolute, as in Nathan's JSON (UX review 8a1d857: JSON wins)
def heic_attrs(lang):
    """jpg-to-pdf only: the UNSUPPORTED_IMAGE card for a .heic/.heif file links to the converter's HEIC -> JPG page in the
    same language (SEO §6, UX review: only there and in the formats FAQ answer). Text from Nathan's keys err_heic_fix
    ({link} placeholder) and err_heic_link_text; these keys are NOT in the page-wide i18n block (see i18n_block)."""
    t=T[lang]
    return f' data-heic-href="{heic_href(lang)}"'
def heic_template(lang):
    """Card texts as visible-text nodes (not attributes) so ru keeps Nathan's U+00A0; app.js reads template.content textContent."""
    t=T[lang]
    return f'<template id="heic-strings"><span data-k="fix">{e(t["err_heic_fix"])}</span><span data-k="text">{e(t["err_heic_link_text"])}</span></template>\n'
def heic_faq_links(lang,a):
    """jpg formats FAQ answer: the converter name (= err_heic_link_text) becomes a link in the visible FAQ only."""
    lt=T[lang]['err_heic_link_text'].replace(NB,' ')  # FAQ text uses plain spaces
    return a.replace(lt,f'[{lt}]({heic_href(lang)})',1) if lt in a and '](' not in a else a

# FAQ answers may carry links as [text](/path) or [text](https://noclaudkit.com/...): rendered as <a> in the visible FAQ,
# plain link text in FAQPage JSON-LD, so the two still match word for word.
FAQ_LINK=re.compile(r'\[([^\]]+)\]\(((?:https://noclaudkit\.com)?/[^)\s]*)\)')
def faq_plain(a): return FAQ_LINK.sub(lambda m:m.group(1),a)
def faq_answer_html(a):
    out,pos='',0
    for m in FAQ_LINK.finditer(a):
        out+=e(a[pos:m.start()])+f'<a class="link link-primary" href="{e(m.group(2))}">{e(m.group(1))}</a>'; pos=m.end()
    return out+e(a[pos:])
def faq_html(lang,items,heic=False):
    t=T[lang]
    if heic: items=[{'q':x['q'],'a':heic_faq_links(lang,x['a'])} for x in items]
    return (f'<section class="faq mt-12" aria-labelledby="faq-h"><h2 id="faq-h" class="text-2xl font-semibold">{e(t["faq_h"])}</h2><div class="mt-4 space-y-2">'
            +''.join(f'<details class="collapse collapse-arrow bg-base-200"><summary class="collapse-title font-semibold min-h-11">{e(x["q"])}</summary><div class="collapse-content"><p>{faq_answer_html(x["a"])}</p></div></details>' for x in items)+'</div></section>\n')

def i18n_block(lang):
    """UI strings for assets/app.js as a JSON data block (type=application/json is never executed, so CSP script-src
    'self' is unaffected). U+00A0 of visible ru strings is written as the escape \\u00a0, never as a raw character."""
    keys=[k for k in UI[lang] if not k.startswith(('licenses_','f_','foot','mode_','drop','h1_','lede','err_heic_'))]  # err_heic_*: jpg-to-pdf data attributes only
    d={k:UI[lang][k] for k in keys}
    j=json.dumps(d,ensure_ascii=False,sort_keys=True).replace(NB,'\\u00a0').replace('<','\\u003c').replace('>','\\u003e').replace('&','\\u0026')
    return f'<script type="application/json" id="i18n">{j}</script>\n'

def tool_page(lang,page,key,mode):
    t=T[lang]; s=SEO[lang][key]; hub=page=='index.html'
    h1=t['h1_home'] if hub else s['h1']
    faqs=FAQ[lang][key]
    ld=[{'@context':'https://schema.org','@type':'WebApplication','name':'Local PDF Tools','description':plain(s['meta']),'url':url(lang,page),'inLanguage':HREFLANG[lang],
         'applicationCategory':'UtilitiesApplication','operatingSystem':'Any','browserRequirements':'Requires JavaScript','isAccessibleForFree':True,'offers':{'@type':'Offer','price':'0','priceCurrency':'USD'}}]
    ld.append({'@context':'https://schema.org','@type':'FAQPage','mainEntity':[{'@type':'Question','name':x['q'],'acceptedAnswer':{'@type':'Answer','text':faq_plain(x['a'])}} for x in faqs]})
    P='' if lang=='en' else '../'
    attrs=(heic_attrs(lang) if mode=='images' else '')+f' data-lang="{HREFLANG[lang]}" data-worker="{P}assets/worker.js" data-pdfjs="{P}assets/vendor/pdf.min.js" data-pdfjs-worker="{P}assets/vendor/pdf.worker.min.js"'
    out=head(T,lang,page,s['title'],s['meta'],jsonld(ld),attrs)
    if hub:
        out+=(f'<section class="hero"><div class="hero-l"><h1 id="h1" class="h1">{e(vis(lang,h1))}</h1><p class="lede">{e(t["lede"])}</p>{dropzone(lang,"merge")}</div>{HERO_ART}</section>\n'
              +app(lang,mode,hub=True)+modecards(lang))
    else:
        out+=(f'<h1 id="h1" class="h1">{e(vis(lang,h1))}</h1><p class="lede">{e(vis(lang,s["meta"]))}</p>\n'+tabs(lang,mode)+app(lang,mode)+(heic_template(lang) if mode=='images' else ''))
    out+=faq_html(lang,faqs,heic=mode=='images')
    # task pages: H2 'Other PDF tools' (Nathan's other_tools) after the FAQ, same heading style, the 3 other tools only
    if not hub: out+=(f'<section class="others mt-12" aria-labelledby="others-h"><h2 id="others-h" class="text-2xl font-semibold">{e(t["other_tools"])}</h2><div class="mt-4">'
                      +modecards(lang,skip=mode)+'</div></section>\n')
    out+=i18n_block(lang)+f'<script type="module" src="{P}assets/app.js"></script>\n'
    return out+foot(lang,page)

# ---------- privacy + licences ----------
def md_inline(s):
    s=e(s)
    s=re.sub(r'\*\*(.+?)\*\*',r'<b>\1</b>',s); s=re.sub(r'`([^`]+)`',r'<code>\1</code>',s)
    return s
LIBS=None
# Counsel PASS 20.10 (Sarah; zh proofread by Nathan): the Metadata paragraph is replaced by this exact HTML (ru: only NBSP typography via vis()).
PRIV_META={
 'en':'<p><b>Metadata.</b> The saved PDF is always a new document with no document information (author, title, subject, keywords, creating program, dates) and no XMP metadata. Metadata in JPEG images (EXIF including GPS location, XMP, IPTC, comments) is removed, both from images in your PDF pages and from photos added with &quot;JPG and photos to PDF&quot;; from PNG images only the pixels are kept. Data needed to display the pages is kept and may contain incidental information: for example, embedded fonts (which may include the font author&#x27;s name), ICC colour profiles, and metadata inside JPEG 2000 images and inline images. The text and content of the pages are not changed.</p>',
 'ru':'<p><b>Метаданные.</b> Сохранённый PDF всегда создаётся как новый документ: в нём нет сведений о документе (автор, название, тема, ключевые слова, программа, даты) и метаданных XMP. Из JPEG-изображений удаляются метаданные (EXIF, включая GPS-координаты, XMP, IPTC, комментарии) — и из изображений на страницах ваших PDF, и из фото, добавленных через «Фото и JPG в PDF»; из PNG в файл попадают только пиксели. Данные, нужные для отображения страниц, сохраняются и могут содержать служебные сведения: например, встроенные шрифты (в них бывает имя автора шрифта), цветовые профили ICC, а также метаданные внутри изображений JPEG 2000 и встроенных (inline) изображений. Сам текст и содержимое страниц не меняются.</p>',
 'zh':'<p><b>元数据。</b>保存的 PDF 始终是一个新文档，不含文档信息（作者、标题、主题、关键词、生成程序、日期），也不含 XMP 元数据。JPEG 图片中的元数据会被删除，包括 EXIF（含 GPS 位置信息）、XMP、IPTC 和注释；这适用于您 PDF 页面中的图片以及通过“JPG 和照片转 PDF”添加的照片。PNG 图片只保留像素数据。显示页面所需的数据会被保留，其中可能包含附带信息，例如嵌入的字体（可能含有字体作者的姓名）、ICC 颜色配置文件，以及 JPEG 2000 图片和内嵌（inline）图片中的元数据。页面的文字和内容不会被更改。</p>'}
META_HEAD=('**Metadata.**','**Метаданные.**','**元数据。**')
def privacy_page(lang):
    t=T[lang]; P=PRIV[lang]; libs='pdf-lib, pdf.js' if lang!='zh' else 'pdf-lib、pdf.js'
    paras=[]; fixed=0
    for p in P['privacy'][1:]:
        if p.startswith(META_HEAD):
            fixed+=1; paras.append(vis(lang,PRIV_META[lang]).replace(' —',NB+'—') if lang=='ru' else PRIV_META[lang]); continue
        p=p.replace('{pdf-lib, pdf.js}',libs).replace('{pdf-lib、pdf.js}',libs)
        # No offline claim until a service worker ships (spec §7, Lucas §8): the offline sentence is not published.
        p=re.sub(r'\s*(After the page has loaded, the tool also works offline\.|После загрузки страницы инструмент работает и без интернета\.|页面加载完成后，本工具也可离线使用。)','',p)
        paras.append(f'<p>{vis(lang,md_inline(p))}</p>')
    assert fixed==1, f'privacy {lang}: Metadata paragraph not found (Counsel text changed?)'
    assert not re.search(r're-encoded|перекодируются|重新编码|offline|без интернета|离线',' '.join(paras)), f'privacy {lang}: unverified claim left'
    h1=re.sub(r'\*','',P['privacy'][0]); dh=re.sub(r'\*','',P['disclaimer'][0])
    body=(f'<h1 id="h1">{e(vis(lang,h1))}</h1>\n'+'\n'.join(paras)+f'\n<h2>{e(dh)}</h2>\n'+'\n'.join(f'<p>{vis(lang,md_inline(p))}</p>' for p in P['disclaimer'][1:])+'\n')
    body=body.replace('GitHub Privacy Statement','<a href="https://docs.github.com/site-policy/privacy-policies/github-general-privacy-statement">GitHub Privacy Statement</a>')
    body=body.replace('Заявление о конфиденциальности GitHub','<a href="https://docs.github.com/site-policy/privacy-policies/github-general-privacy-statement">Заявление о конфиденциальности GitHub</a>')
    body=body.replace('《GitHub 隐私声明》','<a href="https://docs.github.com/site-policy/privacy-policies/github-general-privacy-statement">《GitHub 隐私声明》</a>')
    body=re.sub(r'(open an issue in the GitHub repository|создайте issue в\S? ?репозитории на\S? ?GitHub|在 GitHub 仓库中提交 issue)',lambda m:f'<a href="{REPO}/issues">{m.group(1)}</a>',body)
    return head(T,lang,'privacy.html',t['privacy_title'],t['privacy_desc'],doc=True)+body+foot(lang,'privacy.html')

def licenses_page(lang):
    t=T[lang]
    rows=''.join(f'<tr><td translate="no">{e(n)}</td><td class="tabular-nums">{e(v)}</td><td translate="no">{e(l)}</td></tr>' for n,v,l,_ in LIBS['libs'])
    texts=''.join(f'<h3 translate="no">{e(h)}</h3><pre class="lic" lang="en" translate="no">{e(txt)}</pre>\n' for h,txt in LIBS['texts'])
    body=(f'<h1 id="h1">{e(vis(lang,re.split(r' [–—] |｜| · ',t["licenses_title"])[0]))}</h1>\n<p>{e(t["licenses_body"])}</p>\n'
          f'<h2>{e(t["lic_h_libs"])}</h2><div class="overflow-x-auto"><table class="table"><thead><tr><th>{e(t["lic_col_pkg"])}</th><th>{e(t["lic_col_ver"])}</th><th>{e(t["lic_col_lic"])}</th></tr></thead><tbody>{rows}</tbody></table></div>\n'
          f'<h2>{e(t["lic_h_texts"])}</h2>\n{texts}')
    return head(T,lang,'licenses.html',t['licenses_title'],t['licenses_desc'],doc=True)+body+foot(lang,'licenses.html')

def load_libs():
    """Exact bundled libraries. Source of truth for the core's tree and its embedded notices = THIRD-PARTY.md of
    @local-pdf-tools/core (spec «Licences page update»); versions come from tools/node_modules, full licence texts from
    the packages themselves. tools/scripts/check-licenses.mjs verifies the table against the built bundles."""
    nm='tools/node_modules'
    def ver(p): return json.load(open(f'{nm}/{p}/package.json'))['version']
    def rd(p): return open(f'{nm}/{p}',encoding='utf-8').read().strip()
    tp=rd('@local-pdf-tools/core/THIRD-PARTY.md')
    rows=[]
    for line in tp.split('## Bundled',1)[0].splitlines():
        c=[x.strip() for x in line.strip().strip('|').split('|')]
        if len(c)==5 and c[0] not in ('Package','---') and not set(c[0])<={'-'}:
            assert c[1]==ver(c[0]), f'THIRD-PARTY.md says {c[0]} {c[1]}, installed {ver(c[0])}'
            rows.append((c[0],c[1],c[2],c[3]))
    libs=[('@local-pdf-tools/core',ver('@local-pdf-tools/core'),'MIT','Copyright (c) 2026 swtormy-agents')]+rows+[
          ('base64-arraybuffer','0.1.5','MIT','Copyright (c) 2012 Niklas von Hertzen'),
          ('pdfjs-dist (pdf.js)',ver('pdfjs-dist'),'Apache-2.0','Copyright Mozilla Foundation'),
          # compiled into build/app.css (QA M4)
          ('tailwindcss',ver('tailwindcss'),'MIT','Copyright (c) Tailwind Labs, Inc.'),
          ('daisyui',ver('daisyui'),'MIT','Copyright (c) 2020 Pouya Saadeghi')]
    # embedded notices: every ### section under «Bundled / nested notices», code blocks verbatim (+ the font lists)
    notes=[]
    bund=tp.split('## Bundled / nested notices',1)[1]
    apache=bund.split('## Apache License 2.0',1)
    for sec in re.split(r'\n### ',apache[0])[1:]:
        title=sec.split('\n',1)[0].strip()
        if 'font metrics' in title.lower(): title='@pdf-lib/standard-fonts: font metrics notices'
        blocks=re.findall(r'```\n(.*?)\n```(?:\n(\([^)\n]*\)))?',sec,re.S)
        assert blocks, title
        notes.append((title,'\n\n'.join(b+('\n'+f if f else '') for b,f in blocks)))
    texts=[('@local-pdf-tools/core (MIT)',rd('@local-pdf-tools/core/LICENSE')),('pdf-lib (MIT)',rd('pdf-lib/LICENSE.md')),
           ('@pdf-lib/standard-fonts (MIT)',rd('@pdf-lib/standard-fonts/LICENSE.md')),('@pdf-lib/upng (MIT)',rd('@pdf-lib/upng/LICENSE')),
           ('pako (MIT AND Zlib)',rd('pako/LICENSE')),('tslib (0BSD)',rd('tslib/LICENSE.txt'))]+notes
    # @pdf-lib/standard-fonts README: licence of the original repo it is based on (QA M4), verbatim
    sf=re.search(r"## Original Repo's License\n\n(.*?)\s*$",rd('@pdf-lib/standard-fonts/README.md'),re.S).group(1).strip()
    assert 'Christopher Brown' in sf, 'standard-fonts original licence notice changed'
    texts+=[('@pdf-lib/standard-fonts: original repo licence',sf),('Tailwind CSS (MIT)',rd('tailwindcss/LICENSE')),('daisyUI (MIT)',rd('daisyui/LICENSE'))]
    if len(apache)>1: texts.append(('Apache License 2.0 (pdf-lib stream decoders)',re.search(r'```\n(.*?)\n```',apache[1],re.S).group(1).strip()))
    texts.append(('pdf.js / pdfjs-dist (Apache-2.0)',rd('pdfjs-dist/LICENSE')))
    return {'libs':libs,'texts':texts}

# ---------- checks ----------
def plain_meta(s):
    for m in re.finditer(r'<[^>]*>|<title>.*?</title>|<script type="application/ld\+json">.*?</script>',s,re.S): assert NB not in m.group(0), 'U+00A0 in markup/meta: '+m.group(0)[:80]
    return s
BANNED=re.compile(r'adobe|acrobat|ilovepdf|smallpdf|sejda|pdf24|unlock|donat|boosty|поддержать проект|iphone|offline|офлайн|离线|онлайн',re.I)
def check_page(lang,p,s):
    vis_txt=re.sub(r'<pre class="lic".*?</pre>','',s,flags=re.S) if p=='licenses.html' else s
    vis_txt=re.sub(r'<script type="application/json" id="i18n">.*?</script>','',vis_txt,flags=re.S)
    vis_txt=vis_txt.replace('are not unlocked','')  # Counsel's privacy text denies unlocking; that is allowed
    if p=='jpg-to-pdf.html':  # the UNSUPPORTED_IMAGE card's HEIC -> JPG link data must be present exactly once
        assert s.count(heic_attrs(lang))==1, f'HEIC card link data missing in {lang}/{p}'
        assert s.count(heic_template(lang))==1, f'HEIC card strings template missing in {lang}/{p}'
        assert f'<a class="link link-primary" href="{heic_href(lang)}">' in s, f'HEIC FAQ link missing in {lang}/{p}'
    assert '\u2011' not in ''.join(re.findall(r'<head>.*?</head>|<[^>]*>|<script type="application/ld\+json">.*?</script>',s,re.S)), f'U+2011 in markup/meta in {lang}/{p}'
    m=BANNED.search(vis_txt); assert not m, f'banned word {m.group(0)!r} in {lang}/{p}'
    for j in re.findall(r'<script type="application/ld\+json">(.*?)</script>',s,re.S):
        d=json.loads(j); assert 'aggregateRating' not in j
        if d['@type']=='FAQPage':
            vq=[html.unescape(x) for x in re.findall(r'<summary class="collapse-title[^"]*">(.*?)</summary>',s)]; va=[html.unescape(re.sub(r'<[^>]+>','',x)) for x in re.findall(r'<div class="collapse-content"><p>(.*?)</p>',s)]
            assert vq==[q['name'] for q in d['mainEntity']] and va==[q['acceptedAnswer']['text'] for q in d['mainEntity']], f'FAQ JSON-LD != visible FAQ in {lang}/{p}'
def selftest():
    bad='<script>alert(1)</script>'
    global T,SEO,FAQ
    oT,oS,oF=T,SEO,FAQ
    T={l:{k:(v+bad if isinstance(v,str) else v) for k,v in T[l].items()} for l in LANGS}
    SEO={l:{k:{kk:vv+bad for kk,vv in v.items()} for k,v in SEO[l].items()} for l in LANGS}
    FAQ={l:{k:[{'q':x['q']+bad,'a':x['a']+bad} for x in v] for k,v in FAQ[l].items()} for l in LANGS}
    try:
        for page,key,mode in TOOLS:
            s=tool_page('ru',page,key,mode)
            assert '<script>alert' not in s, f'unescaped test string in {page}'
            for m in re.findall(r'<script type="application/ld\+json">(.*?)</script>',s,re.S): assert '<' not in m and '>' not in m and '&' not in m
    finally: T,SEO,FAQ=oT,oS,oF

LIBS=load_libs()
selftest()
for k in SEO['ru']: assert 'онлайн' not in SEO['ru'][k]['title'].lower()
pages=[]
for lang in LANGS:
    if lang!='en': os.makedirs(lang,exist_ok=True)
    out={p:tool_page(lang,p,k,m) for p,k,m in TOOLS}
    out['privacy.html']=privacy_page(lang); out['licenses.html']=licenses_page(lang)
    for p,s in out.items():
        plain_meta(s); check_page(lang,p,s)
        f=lp(lang)+p
        if not os.path.exists(f) or open(f,encoding='utf-8').read()!=s: open(f,'w',encoding='utf-8').write(s)
        pages.append((lang,p))

def lastmod(l,p):
    """Last commit date of the page's content sources (not of gen.py); falls back to the newest commit date."""
    src=[f'tools/i18n/{l}.json','tools/i18n/seo.json','tools/i18n/faq.json']
    d=subprocess.run(['git','log','-1','--format=%cs','--',*src],capture_output=True,text=True).stdout.strip()
    if not d: d=subprocess.run(['git','log','-1','--format=%cs'],capture_output=True,text=True).stdout.strip()
    assert re.fullmatch(r'\d{4}-\d{2}-\d{2}',d), 'no git date'
    return d
SM=[(l,p) for l,p in pages]  # all 21 pages incl. privacy + licences (converter convention, SEO review 38054b6 #4)
assert len(SM)==21, len(SM)
sm=('<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9" xmlns:xhtml="http://www.w3.org/1999/xhtml">\n'
 +''.join(f'<url><loc>{url(l,p)}</loc><lastmod>{lastmod(l,p)}</lastmod>'+''.join(f'<xhtml:link rel="alternate" hreflang="{HREFLANG[x]}" href="{url(x,p)}"/>' for x in LANGS)+f'<xhtml:link rel="alternate" hreflang="x-default" href="{url("en",p)}"/></url>\n' for l,p in SM)+'</urlset>\n')
if not os.path.exists('sitemap.xml') or open('sitemap.xml').read()!=sm: open('sitemap.xml','w').write(sm)
print(len(pages),'pages,',len(SM),'sitemap URLs')

# ---------- llms.txt + Markdown twins for AI agents (en only; Sergey Barrow) ----------
# Same en strings as the HTML pages; links are canonical sitemap URLs only; the .md/.txt files are NOT in the sitemap
# (converter convention). Output goes through the same BANNED check; any hit fails the build.
def gen_llms():
    t=T['en']; S=SEO['en']; F=FAQ['en']
    INTRO='Files are processed in your browser and never leave your device. Free and open source: no uploads, no cookies, no ads.'  # Nathan-approved; BANNED-checked via w()
    md_url=lambda p:BASE+p[:-5]+'.md'
    def w(path,s):
        chk=s.replace('are not unlocked','')  # same Counsel exemption as check_page
        m=BANNED.search(chk); assert not m, f'banned word {m.group(0)!r} in {path}'
        assert NB not in s and '\u2011' not in s, f'non-plain space/hyphen in {path}'
        if not os.path.exists(path) or open(path,encoding='utf-8').read()!=s: open(path,'w',encoding='utf-8').write(s)
    def faq_md(key): return f'## {t["faq_h"]}\n\n'+''.join(f'### {plain(x["q"])}\n\n{plain(faq_plain(x["a"]))}\n\n' for x in F[key])
    def tools_md(skip=None): return ''.join(f'- [{t[MODE_KEY[m]]}]({url("en",p)}): {t[MODE_KEY[m]+"_desc"]}\n' for m,p in MODE_PAGE.items() if m!=skip)
    tail=f'{plain(t["foot"])}\n\n{plain(t["legal"])}\n'
    files={}
    for page,key,mode in TOOLS:
        s=S[key]; hub=page=='index.html'
        out=f'# {plain(t["h1_home"] if hub else s["h1"])}\n\nHTML version: {url("en",page)}\n\n{plain(t["lede"] if hub else s["meta"])}\n\n'
        if hub: out+=f'{plain(s["meta"])}\n\n'+tools_md()+'\n'
        if mode=='images': out+=f'{plain(t["meta_notice"])}\n\n'
        out+=faq_md(key)
        if not hub: out+=f'## {t["other_tools"]}\n\n'+tools_md(skip=mode)+'\n'
        files[page[:-5]+'.md']=out+tail
    # privacy: text of the generated en privacy page (already stripped of unverified claims there)
    ph=privacy_page('en'); body=ph.split('<main',1)[1].split('>',1)[1].split('</main>',1)[0]
    body=re.sub(r'<a href="([^"]+)">(.*?)</a>',r'[\2](\1)',body)
    body=re.sub(r'<h1[^>]*>(.*?)</h1>',r'# \1\n\nHTML version: '+url('en','privacy.html')+'\n',body)
    body=re.sub(r'<h2[^>]*>(.*?)</h2>',r'## \1\n',body); body=re.sub(r'<b>(.*?)</b>',r'**\1**',body)
    body=re.sub(r'<code>(.*?)</code>',r'`\1`',body); body=body.replace('</p>','\n\n').replace('<p>','')
    assert '<' not in body, 'unconverted tag in privacy.md'
    files['privacy.md']=re.sub(r'\n{3,}','\n\n',html.unescape(body).replace(NB,' ').strip()+'\n')
    lic=(f'# {re.split(r" [–—] ",t["licenses_title"])[0]}\n\nHTML version: {url("en","licenses.html")}\n\n{t["licenses_body"]}\n\n## {t["lic_h_libs"]}\n\n'
         f'| {t["lic_col_pkg"]} | {t["lic_col_ver"]} | {t["lic_col_lic"]} |\n|---|---|---|\n'+''.join(f'| {n} | {v} | {l.replace("see below","see the full notice on the [HTML version]("+url("en","licenses.html")+")")} |\n' for n,v,l,_ in LIBS['libs'])
         +f'\nFull licence texts: {url("en","licenses.html")}\n')
    files['licenses.md']=lic
    txt=(f'# Local PDF Tools\n\n> {plain(S["hub"]["meta"])}\n\n{INTRO}\n\n'
         f'## Tools\n\n'+tools_md()+
         f'\n## Docs\n\n- [{plain(t["h1_home"])}]({md_url("index.html")})\n'+''.join(f'- [{plain(S[k]["h1"])}]({md_url(p)})\n' for p,k,_ in TOOLS[1:])
         +f'- [{t["f_priv"]}]({md_url("privacy.html")})\n- [{t["f_lic"]}]({md_url("licenses.html")})\n'
         f'\n## Optional\n\n- [{t["f_src"]}]({REPO}): MIT\n- [Local PDF Tools (HTML)]({url("en","index.html")})\n\n{plain(t["legal"])}\n')
    files['llms.txt']=txt
    for p,s in files.items(): w(p,s)
    return sorted(files)
print('llms:',', '.join(gen_llms()))
