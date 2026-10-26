#!/usr/bin/env python3
"""Unit tests for tools/indexnow.py. Run: python3 tools/test/test_indexnow.py"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

TOOLS = Path(__file__).resolve().parent.parent
ROOT = TOOLS.parent
sys.path.insert(0, str(TOOLS))

import indexnow  # noqa: E402

HOST = "noclaudkit.com"
BASE = f"https://{HOST}/pdf"
HOME = f"{BASE}/"
MERGE = f"{BASE}/merge-pdf.html"
MERGE_RU = f"{BASE}/ru/merge-pdf.html"
SAMPLE_LOCS = [HOME, MERGE, MERGE_RU]

URLSET = f"""<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9" xmlns:xhtml="http://www.w3.org/1999/xhtml">
<url><loc>{HOME}</loc><lastmod>2026-10-25</lastmod></url>
<url><loc>{MERGE}</loc><lastmod>2026-10-25</lastmod></url>
<url><loc>{MERGE_RU}</loc><lastmod>2026-10-25</lastmod></url>
</urlset>
"""


def write_min_repo(tmp: Path, urlset: str = URLSET) -> Path:
    tmp.joinpath("sitemap.xml").write_text(urlset, encoding="utf-8")
    return tmp


def mapped(tmp: Path, files: list[str]) -> list[str]:
    locs, alts = indexnow.parse_local_urlsets(tmp)
    return indexnow.map_changed_files(files, locs, alts)


class CanonicalUrlTests(unittest.TestCase):
    def test_accepts_pdf_prefix_only(self):
        self.assertTrue(indexnow.is_canonical_url(HOME))
        self.assertTrue(indexnow.is_canonical_url(MERGE_RU))
        self.assertFalse(indexnow.is_canonical_url("https://noclaudkit.com/"))
        self.assertFalse(indexnow.is_canonical_url("https://noclaudkit.com/image-converter/"))
        self.assertFalse(indexnow.is_canonical_url(f"{MERGE}?x=1"))


class MappingTests(unittest.TestCase):
    def test_html_maps_to_sitemap_locs(self):
        with tempfile.TemporaryDirectory() as raw:
            tmp = write_min_repo(Path(raw))
            self.assertEqual(mapped(tmp, ["merge-pdf.html"]), [MERGE])
            self.assertEqual(mapped(tmp, ["ru/merge-pdf.html"]), [MERGE_RU])

    def test_theme_js_maps_all_locs(self):
        with tempfile.TemporaryDirectory() as raw:
            tmp = write_min_repo(Path(raw))
            self.assertEqual(mapped(tmp, ["theme.js"]), sorted(SAMPLE_LOCS))


class CollectUrlsTests(unittest.TestCase):
    def test_all_locs(self):
        with tempfile.TemporaryDirectory() as raw:
            tmp = write_min_repo(Path(raw))
            urls = indexnow.collect_urls(tmp, None, None, None, all_locs=True)
            self.assertEqual(urls, sorted(SAMPLE_LOCS))

    def test_files_mode(self):
        with tempfile.TemporaryDirectory() as raw:
            tmp = write_min_repo(Path(raw))
            urls = indexnow.collect_urls(tmp, ["merge-pdf.html"], None, None, all_locs=False)
            self.assertEqual(urls, [MERGE])


class ShaValidationTests(unittest.TestCase):
    def test_rejects_bad_sha_lengths_and_metacharacters(self):
        self.assertFalse(indexnow.is_full_sha("a" * 39))
        self.assertFalse(indexnow.is_full_sha("a" * 41))
        self.assertFalse(indexnow.is_full_sha("g" * 40))
        self.assertFalse(indexnow.is_full_sha("deadbeef;rm -rf"))
        self.assertTrue(indexnow.is_full_sha("a" * 40))

    def test_validate_explicit_before_message(self):
        with tempfile.TemporaryDirectory() as raw:
            tmp = Path(raw)
            subprocess.run(["git", "init", "-q"], cwd=tmp, check=True)
            subprocess.run(["git", "checkout", "-b", "main"], cwd=tmp, check=True)
            tmp.joinpath("f").write_text("x\n", encoding="utf-8")
            subprocess.run(["git", "add", "f"], cwd=tmp, check=True)
            subprocess.run(
                ["git", "-c", "user.email=a@b.c", "-c", "user.name=t", "commit", "-qm", "c1"],
                cwd=tmp,
                check=True,
            )
            good = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=tmp, text=True).strip()
            with self.assertRaises(indexnow.IndexNowError) as ctx:
                indexnow.validate_explicit_before(tmp, "b" * 39)
            self.assertIn("40-character", str(ctx.exception))
            with self.assertRaises(indexnow.IndexNowError) as ctx:
                indexnow.validate_explicit_before(tmp, "g" * 40)
            self.assertIn("40-character", str(ctx.exception))
            self.assertEqual(indexnow.validate_explicit_before(tmp, good), good)


class RootKeyTests(unittest.TestCase):
    def test_uses_root_key_location(self):
        key, location = indexnow.root_key()
        self.assertEqual(key, indexnow.INDEXNOW_KEY)
        self.assertEqual(location, indexnow.KEY_LOCATION)
        self.assertTrue(location.startswith("https://noclaudkit.com/"))
        self.assertNotIn("/pdf/", location)


class WorkflowContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.path = ROOT / ".github/workflows/indexnow.yml"
        cls.text = cls.path.read_text(encoding="utf-8")

    def test_security_and_pins(self):
        self.assertIn("contents: read", self.text)
        self.assertIn("actions: read", self.text)
        self.assertIn("persist-credentials: false", self.text)
        self.assertIn(
            "actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1",
            self.text,
        )
        self.assertEqual(self.text.count("python3 tools/indexnow.py --submit"), 1)
        self.assertIn("INDEXNOW_ALL:", self.text)
        self.assertNotIn("secrets.INDEXNOW", self.text)

    def test_inputs_not_interpolated_into_run(self):
        run_lines = [line for line in self.text.splitlines() if line.lstrip().startswith("run:")]
        self.assertEqual(run_lines, ["        run: python3 tools/indexnow.py --submit"])
        for line in run_lines:
            self.assertNotIn("${{", line)


class LiveRepoTests(unittest.TestCase):
    def test_real_sitemap_urls_are_pdf_canonical(self):
        locs, _ = indexnow.parse_local_urlsets(ROOT)
        self.assertGreater(len(locs), 10)
        self.assertTrue(all(indexnow.is_canonical_url(url) for url in locs))

    def test_dry_run_payload_shape(self):
        code = indexnow.main(["--dry-run", "--all", "--repo-root", str(ROOT)])
        self.assertEqual(code, 0)


class MainAllEnvTests(unittest.TestCase):
    def test_indexnow_all_env_enables_all_mode(self):
        with tempfile.TemporaryDirectory() as raw:
            tmp = write_min_repo(Path(raw))
            env = {**os.environ, "INDEXNOW_ALL": "1"}
            with mock.patch.dict(os.environ, env, clear=True):
                out = subprocess.check_output(
                    [sys.executable, str(TOOLS / "indexnow.py"), "--dry-run", "--repo-root", str(tmp)],
                    text=True,
                )
            payload = json.loads(out)
            self.assertEqual(len(payload["urlList"]), 3)
            self.assertEqual(payload["keyLocation"], indexnow.KEY_LOCATION)


if __name__ == "__main__":
    unittest.main()
