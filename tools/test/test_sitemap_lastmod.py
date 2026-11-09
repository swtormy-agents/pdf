#!/usr/bin/env python3
"""Unit tests for content-aware seo/faq subtree lastmod (throwaway git repos)."""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
sys.path.insert(0, os.path.join(ROOT, 'tools'))
import sitemap_lastmod as sl

def git(args, cwd, env=None):
    e = {**os.environ, **(env or {})}
    subprocess.run(['git', *args], cwd=cwd, check=True, capture_output=True, env=e)


class SubtreeLastmodTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix='lastmod-')
        git(['init'], self.tmp)
        git(['config', 'user.email', 't@t.com'], self.tmp)
        git(['config', 'user.name', 't'], self.tmp)
        os.makedirs(os.path.join(self.tmp, 'tools', 'i18n'), exist_ok=True)
        self.faq_path = os.path.join(self.tmp, 'tools', 'i18n', 'faq.json')
        self.seo_path = os.path.join(self.tmp, 'tools', 'i18n', 'seo.json')

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)
        sl.clear_json_cache()

    def _write_faq(self, data):
        with open(self.faq_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=1)

    def _write_seo(self, data):
        with open(self.seo_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=1)

    def test_faq_answer_edit_moves_one_page_only(self):
        faq = {
            'en': {
                'hub': [{'q': 'Hub Q', 'a': 'hub a'}],
                'merge': [{'q': 'Merge Q', 'a': 'merge a'}],
                'split': [{'q': 'Split Q', 'a': 'split v1'}],
                'organize': [{'q': 'Org Q', 'a': 'org a'}],
                'jpg': [{'q': 'Jpg Q', 'a': 'jpg a'}],
            }
        }
        for lang in ('ru', 'zh'):
            faq[lang] = json.loads(json.dumps(faq['en']))
        self._write_faq(faq)
        git(['add', 'tools/i18n/faq.json'], self.tmp)
        git(['commit', '-m', 'init faq'], self.tmp, env={
            'GIT_AUTHOR_DATE': '2026-01-10T12:00:00',
            'GIT_COMMITTER_DATE': '2026-01-10T12:00:00',
        })
        faq['en']['split'][0]['a'] = 'split v2'
        self._write_faq(faq)
        git(['add', 'tools/i18n/faq.json'], self.tmp)
        git(['commit', '-m', 'split answer only'], self.tmp, env={
            'GIT_AUTHOR_DATE': '2026-02-15T12:00:00',
            'GIT_COMMITTER_DATE': '2026-02-15T12:00:00',
        })
        cache = {}
        dates = sl.subtree_lastmods('tools/i18n/faq.json', cwd=self.tmp, cache=cache)
        self.assertEqual(dates[('en', 'split')], '2026-02-15')
        self.assertEqual(dates[('en', 'merge')], '2026-01-10')
        self.assertEqual(dates[('en', 'hub')], '2026-01-10')
        page_seo = {
            'index.html': 'hub',
            'merge-pdf.html': 'merge',
            'split-pdf.html': 'split',
        }
        merge = sl.page_lastmod('en', 'merge-pdf.html', page_seo, cwd=self.tmp, faq_dates=dates, cache=cache)
        split = sl.page_lastmod('en', 'split-pdf.html', page_seo, cwd=self.tmp, faq_dates=dates, cache=cache)
        self.assertEqual(merge, '2026-01-10')
        self.assertEqual(split, '2026-02-15')


if __name__ == '__main__':
    unittest.main()
