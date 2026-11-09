#!/usr/bin/env python3
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from faq_markup import faq_link_href_ok, faq_plain, FAQ_LINK


class TestFaqMarkup(unittest.TestCase):
    def test_href_root_path(self):
        self.assertTrue(faq_link_href_ok('/pdf/merge-pdf.html'))
        self.assertTrue(faq_link_href_ok('https://noclaudkit.com/image-converter/heic-to-jpg.html'))

    def test_rejects_protocol_relative(self):
        self.assertFalse(faq_link_href_ok('//evil.com'))
        with self.assertRaises(ValueError):
            faq_plain('[x](//evil.com)')

    def test_rejects_non_slash(self):
        self.assertFalse(faq_link_href_ok('javascript:alert(1)'))
        with self.assertRaises(ValueError):
            faq_plain('[x](https://example.com)')

    def test_plain_keeps_link_text(self):
        self.assertEqual(faq_plain('[конвертер HEIC в JPG](/x.html)'), 'конвертер HEIC в JPG')


if __name__ == '__main__':
    unittest.main()
