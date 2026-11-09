#!/usr/bin/env python3
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from editorial_html import validate_editorial_html, EditorialHtmlError, editorial_section

GOOD = '<ul><li>One</li><li><a href="/pdf/merge-pdf.html">Merge</a></li></ul>'
POSITIVE_P = '<p>Hello <strong>bold</strong> and <a href="/x.html">link</a>.</p>'


class TestEditorialHtml(unittest.TestCase):
    def test_positive_ul_li(self):
        validate_editorial_html(GOOD)

    def test_positive_paragraph(self):
        validate_editorial_html(POSITIVE_P)

    def test_renders_section(self):
        self.assertIn('class="link link-primary"', editorial_section(POSITIVE_P))

    def test_p_hidden(self):
        with self.assertRaises(EditorialHtmlError):
            validate_editorial_html('<p hidden>x</p>')

    def test_onclick(self):
        with self.assertRaises(EditorialHtmlError):
            validate_editorial_html('<p onclick="alert(1)">x</p>')

    def test_href_protocol_relative(self):
        with self.assertRaises(EditorialHtmlError):
            validate_editorial_html('<p><a href="//evil.example/x">x</a></p>')

    def test_href_backslash(self):
        with self.assertRaises(EditorialHtmlError):
            validate_editorial_html('<p><a href="/\\evil">x</a></p>')

    def test_href_entity_tab(self):
        with self.assertRaises(EditorialHtmlError):
            validate_editorial_html('<p><a href="/&#9;/evil">x</a></p>')

    def test_javascript_href(self):
        with self.assertRaises(EditorialHtmlError):
            validate_editorial_html('<p><a href="javascript:alert(1)">x</a></p>')

    def test_cdata(self):
        with self.assertRaises(EditorialHtmlError):
            validate_editorial_html('<![CDATA[x]]>')

    def test_html_comment(self):
        with self.assertRaises(EditorialHtmlError):
            validate_editorial_html('<!-- x --!>')

    def test_trailing_unclosed_a(self):
        with self.assertRaises(EditorialHtmlError):
            validate_editorial_html('<p><a href="//e"')

    def test_incomplete_open_p(self):
        with self.assertRaises(EditorialHtmlError):
            validate_editorial_html('<p')

    def test_incomplete_close_p(self):
        with self.assertRaises(EditorialHtmlError):
            validate_editorial_html('<p>x</p')

    def test_stray_lt(self):
        with self.assertRaises(EditorialHtmlError):
            validate_editorial_html('<p>x < y</p>')

    def test_unbalanced(self):
        with self.assertRaises(EditorialHtmlError):
            validate_editorial_html('<p><strong>x</p>')

    def test_placeholder(self):
        with self.assertRaises(EditorialHtmlError):
            validate_editorial_html('<p>TODO fix</p>')

    def test_empty(self):
        with self.assertRaises(EditorialHtmlError):
            validate_editorial_html('')


if __name__ == '__main__':
    unittest.main()
