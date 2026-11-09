#!/usr/bin/env python3
"""FAQPage JSON-LD and visible answers must match tools/i18n/faq.json source text."""
import html
import json
import os
import re
import sys
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
os.chdir(ROOT)
sys.path.insert(0, os.path.join(ROOT, 'tools'))
import gen  # noqa: E402


class TestFaqSource(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.faq = json.load(open('tools/i18n/faq.json', encoding='utf-8'))
        cls.pages = {lang: gen.tool_page(lang, 'jpg-to-pdf.html', 'jpg', 'images') for lang in gen.LANGS}

    def test_jpg_faq_matches_source_all_locales(self):
        for lang in gen.LANGS:
            src = {x['q']: x['a'] for x in self.faq[lang]['jpg']}
            html_doc = self.pages[lang]
            for j in re.findall(r'<script type="application/ld\+json">(.*?)</script>', html_doc, re.S):
                d = json.loads(j)
                if d.get('@type') != 'FAQPage':
                    continue
                for ent in d['mainEntity']:
                    q, plain = ent['name'], ent['acceptedAnswer']['text']
                    self.assertIn(q, src, msg=f'{lang}: unknown question in JSON-LD')
                    self.assertEqual(plain, src[q], msg=f'{lang} JSON-LD answer != faq.json for {q!r}')
            fb = re.search(r'<section class="faq[^"]*"[^>]*>(.*?)</section>', html_doc, re.S)
            self.assertTrue(fb, f'{lang}: missing FAQ section')
            for summary, content in zip(
                re.findall(r'<summary class="collapse-title[^"]*">(.*?)</summary>', fb.group(1)),
                re.findall(r'<div class="collapse-content"><p>(.*?)</p>', fb.group(1)),
            ):
                q = html.unescape(summary)
                visible = html.unescape(re.sub(r'<[^>]+>', '', content))
                self.assertIn(q, src)
                self.assertEqual(visible, src[q], msg=f'{lang} visible answer != faq.json for {q!r}')


if __name__ == '__main__':
    unittest.main()
