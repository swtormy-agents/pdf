#!/usr/bin/env python3
"""Draws the Open Graph images assets/og/og-{en,ru,zh}.png (1200x630), same layout as the image converter's: accent bar,
the hub H1 (h1_home), the promise line (lede) and the brand. Text comes from tools/i18n/{lang}.json; fonts are the
locally installed Noto Sans CJK (covers Latin, Cyrillic and Han). No network, no third-party assets.
Run: python3 tools/scripts/og.py   (needs Pillow). The PNGs are committed; gen.py only reads them (og:image ?v= hash)."""
import json, os, sys
from PIL import Image, ImageDraw, ImageFont
os.chdir(os.path.join(os.path.dirname(__file__), '..', '..'))
FONT_DIR = os.environ.get('OG_FONT_DIR', '/usr/share/fonts/opentype/noto')
BOLD, REG = f'{FONT_DIR}/NotoSansCJK-Bold.ttc', f'{FONT_DIR}/NotoSansCJK-Regular.ttc'
FACE = {'en': 2, 'ru': 2, 'zh': 2}  # .ttc index 2 = SC (Simplified Chinese glyph forms; Latin/Cyrillic identical)
W, H = 1200, 630
BG, CARD, EDGE, INK, MUTED, ACCENT = (243, 244, 247), (255, 255, 255), (170, 176, 196), (17, 24, 39), (85, 92, 110), (30, 64, 175)
NB = '\u00a0'

def wrap(draw, text, font, width):
    """Greedy wrap on spaces (Han text: per character); U+00A0 never breaks."""
    words = list(text) if ' ' not in text else text.split(' ')
    joiner = '' if ' ' not in text else ' '
    lines, cur = [], ''
    for w in words:
        nxt = cur + (joiner if cur else '') + w
        if cur and draw.textlength(nxt.replace(NB, ' '), font=font) > width: lines.append(cur); cur = w
        else: cur = nxt
    if cur: lines.append(cur)
    return [l.replace(NB, ' ') for l in lines]

def draw(lang):
    t = json.load(open(f'tools/i18n/{lang}.json', encoding='utf-8'))
    img = Image.new('RGB', (W, H), BG)
    d = ImageDraw.Draw(img)
    d.rounded_rectangle((40, 40, W - 40, H - 40), radius=28, fill=CARD, outline=EDGE, width=2)
    x, maxw = 112, W - 2 * 112
    d.rectangle((x, 140, x + 72, 147), fill=ACCENT)
    h1 = ImageFont.truetype(BOLD, 66, index=FACE[lang]); sub = ImageFont.truetype(REG, 34, index=FACE[lang]); brand = ImageFont.truetype(BOLD, 30, index=FACE[lang])
    y = 186
    for line in wrap(d, t['h1_home'], h1, maxw)[:2]:
        d.text((x, y), line, font=h1, fill=INK); y += 84
    y += 16
    for line in wrap(d, t['lede'], sub, maxw)[:2]:
        d.text((x, y), line, font=sub, fill=MUTED); y += 48
    d.text((x, H - 40 - 78), 'Local PDF Tools', font=brand, fill=ACCENT)
    out = f'assets/og/og-{lang}.png'
    img.save(out, optimize=True)
    return out

if __name__ == '__main__':
    os.makedirs('assets/og', exist_ok=True)
    for l in ('en', 'ru', 'zh'): print(draw(l))
