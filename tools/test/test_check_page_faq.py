#!/usr/bin/env python3
"""check_page FAQ JSON-LD vs visible text must be scoped to the FAQ section."""
import os
import re
import sys
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
os.chdir(ROOT)
sys.path.insert(0, os.path.join(ROOT, 'tools'))
import gen  # noqa: E402


class TestCheckPageFaq(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.good = gen.tool_page('en', 'merge-pdf.html', 'merge', 'merge')

    def test_passes_on_built_page(self):
        gen.check_page('en', 'merge-pdf.html', self.good)

    def test_fails_on_faq_answer_mismatch_in_section(self):
        # Break only the visible FAQ answer; JSON-LD stays correct — must fail, not mask via whole-page scan.
        bad = re.sub(
            r'(<summary class="collapse-title[^"]*">How do I merge PDF files\?</summary><div class="collapse-content"><p>)',
            r'\1BROKEN ',
            self.good,
            count=1,
        )
        self.assertNotEqual(bad, self.good, 'test HTML was not mutated')
        with self.assertRaises(AssertionError, msg='FAQ mismatch inside section should fail check_page'):
            gen.check_page('en', 'merge-pdf.html', bad)

    def test_fails_when_faq_section_missing(self):
        stripped = re.sub(r'<section class="faq[^"]*"[^>]*>.*?</section>\n?', '', self.good, count=1, flags=re.S)
        self.assertIsNone(re.search(r'<section class="faq[^"]*"[^>]*>', stripped))
        with self.assertRaises(AssertionError, msg='FAQPage without FAQ section should fail'):
            gen.check_page('en', 'merge-pdf.html', stripped)


if __name__ == '__main__':
    unittest.main()
