#!/usr/bin/env python3
"""Print policy rejections for current SEO copy (no page rewrites)."""
import json
import os
import re
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
os.chdir(ROOT)
sys.path.insert(0, os.path.join(ROOT, 'tools'))
import gen  # noqa: E402

BANNED = gen.BANNED
SEO = json.load(open('tools/i18n/seo.json', encoding='utf-8'))
PAGE = {'jpg': 'jpg-to-pdf.html', 'split': 'split-pdf.html'}


def emit(kind, locale, page, field, word, detail=''):
    w = f'{word!r}'
    tail = f' ({detail})' if detail else ''
    print(f'{kind}\t{locale}\t{page}\t{field}\t{w}{tail}')


for key, page in PAGE.items():
    for lang in gen.LANGS:
        for field in ('title', 'h1', 'meta', 'editorial_html'):
            text = SEO[lang][key].get(field, '')
            m = BANNED.search(text)
            if m:
                emit('BANNED', lang, page, field, m.group(0))

for k, ent in SEO['ru'].items():
    if 'онлайн' in ent.get('title', '').lower():
        emit('RU_TITLE', 'ru', k, 'title', 'онлайн', ent['title'])

for lang in gen.LANGS:
    p = PAGE['jpg']
    try:
        html_doc = gen.tool_page(lang, p, 'jpg', 'images')
    except Exception as e:
        emit('BUILD', lang, p, 'tool_page', type(e).__name__, str(e))
        continue
    vis = re.sub(r'<script type="application/json" id="i18n">.*?</script>', '', html_doc, flags=re.S)
    vis = vis.replace('are not unlocked', '')
    m = BANNED.search(vis)
    if m:
        emit('BANNED_PAGE', lang, p, 'rendered_html', m.group(0))
