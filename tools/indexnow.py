#!/usr/bin/env python3
"""Map this repo's changed files to sitemap URLs and optionally ping IndexNow.

Uses the public IndexNow key file on the root site (noclaudkit.com), not in this repo.
Only <loc> entries under https://noclaudkit.com/pdf/ in the local sitemap are eligible.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path

HOST = "noclaudkit.com"
SITE_PATH = "pdf"
ORIGIN = f"https://{HOST}/{SITE_PATH}"
ROOT_ORIGIN = f"https://{HOST}"
INDEXNOW_KEY = "3c9d9ec99b2863d4ed3f1eed6b0780fc"
KEY_LOCATION = f"{ROOT_ORIGIN}/{INDEXNOW_KEY}.txt"
INDEXNOW_ENDPOINT = "https://api.indexnow.org/indexnow"
GITHUB_API = "https://api.github.com"
WORKFLOW_FILE = "indexnow.yml"
WORKFLOW_BRANCH = "main"
URL_LIST_CAP = 10_000
FULL_SHA_RE = re.compile(r"^[0-9a-f]{40}$")

SHARED_SITE_FILES = frozenset(
    {
        "theme.js",
        "favicon.svg",
        "build/app.css",
        "tools/gen.py",
    }
)


class IndexNowError(Exception):
    """User-facing script failure."""


def normalize_repo_path(path: str) -> str:
    return path.replace("\\", "/").lstrip("./")


def is_canonical_url(url: str, host: str = HOST, site_path: str = SITE_PATH) -> bool:
    if not url:
        return False
    prefix = f"https://{host}/{site_path}/"
    if url != prefix and not url.startswith(prefix):
        return False
    if any(ch in url for ch in "#?"):
        return False
    return True


def parse_urlset_text(text: str) -> tuple[set[str], dict[str, set[str]], dict[str, str]]:
    """Return (locs, alternates, loc_fingerprints) from one urlset document."""
    locs: set[str] = set()
    alternates: dict[str, set[str]] = {}
    fingerprints: dict[str, str] = {}
    try:
        root = ET.fromstring(text)
    except ET.ParseError:
        return locs, alternates, fingerprints
    tag = root.tag.rsplit("}", 1)[-1]
    if tag != "urlset":
        return locs, alternates, fingerprints
    for url_el in root.findall(".//{*}url"):
        loc_el = url_el.find("{*}loc")
        if loc_el is None or not loc_el.text:
            continue
        loc = loc_el.text.strip()
        if not is_canonical_url(loc):
            continue
        locs.add(loc)
        lastmod_el = url_el.find("{*}lastmod")
        lastmod = (lastmod_el.text or "").strip() if lastmod_el is not None else ""
        fingerprints[loc] = f"{loc}\n{lastmod}"
        alts = alternates.setdefault(loc, set())
        for link in url_el.findall("{*}link"):
            if link.get("rel") != "alternate":
                continue
            href = (link.get("href") or "").strip()
            if is_canonical_url(href):
                alts.add(href)
    return locs, alternates, fingerprints


def parse_local_urlsets(repo_root: Path) -> tuple[set[str], dict[str, set[str]]]:
    locs: set[str] = set()
    alternates: dict[str, set[str]] = {}
    for path in sorted(repo_root.glob("sitemap*.xml")):
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            continue
        part_locs, part_alts, _ = parse_urlset_text(text)
        locs |= part_locs
        for loc, alts in part_alts.items():
            alternates.setdefault(loc, set()).update(alts)
    return locs, alternates


def candidate_urls_for_file(relpath: str) -> set[str] | None:
    relpath = normalize_repo_path(relpath)
    if not relpath or relpath.startswith(".git/"):
        return set()
    if relpath in SHARED_SITE_FILES:
        return None
    if relpath == "sitemap.xml":
        return None
    if not relpath.endswith(".html"):
        return set()
    if relpath.endswith("index.html"):
        directory = relpath[: -len("index.html")]
        if directory:
            return {f"{ORIGIN}/{directory}"}
        return {f"{ORIGIN}/"}
    stem = relpath[: -len(".html")]
    return {
        f"{ORIGIN}/{relpath}",
        f"{ORIGIN}/{stem}",
        f"{ORIGIN}/{stem}/",
    }


def map_changed_files(
    changed_files: list[str],
    sitemap_locs: set[str],
    alternates: dict[str, set[str]],
) -> list[str]:
    urls: set[str] = set()
    for raw in changed_files:
        candidates = candidate_urls_for_file(raw)
        if candidates is None:
            matched = set(sitemap_locs)
        else:
            matched = {url for url in candidates if url in sitemap_locs}
        for url in matched:
            urls.add(url)
            for alt in alternates.get(url, ()):
                if alt in sitemap_locs:
                    urls.add(alt)
    return sorted(urls)[:URL_LIST_CAP]


def changed_files_between(repo_root: Path, before: str, after: str) -> list[str]:
    result = subprocess.run(
        ["git", "diff", "--name-only", "--diff-filter=ACDMR", before, after],
        cwd=repo_root,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        detail = (result.stderr or result.stdout).strip() or f"exit {result.returncode}"
        raise IndexNowError(f"git diff failed: {detail}")
    return [normalize_repo_path(line) for line in result.stdout.splitlines() if line.strip()]


def git_show_file(repo_root: Path, rev: str, relpath: str) -> str | None:
    result = subprocess.run(
        ["git", "show", f"{rev}:{relpath}"],
        cwd=repo_root,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        return None
    return result.stdout


def changed_sitemap_locs(repo_root: Path, before: str, after: str) -> set[str]:
    before_text = git_show_file(repo_root, before, "sitemap.xml")
    after_text = git_show_file(repo_root, after, "sitemap.xml")
    if not after_text:
        return set()
    _, _, after_fp = parse_urlset_text(after_text)
    if not before_text:
        return set(after_fp)
    _, _, before_fp = parse_urlset_text(before_text)
    changed: set[str] = set()
    for loc, fp in after_fp.items():
        if before_fp.get(loc) != fp:
            changed.add(loc)
    return changed


def first_parent(repo_root: Path, sha: str) -> str:
    result = subprocess.run(
        ["git", "rev-parse", f"{sha}^1"],
        cwd=repo_root,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        detail = (result.stderr or result.stdout).strip() or f"exit {result.returncode}"
        raise IndexNowError(f"cannot resolve first parent of {sha}: {detail}")
    return result.stdout.strip()


def is_ancestor(repo_root: Path, ancestor: str, sha: str) -> bool:
    result = subprocess.run(
        ["git", "merge-base", "--is-ancestor", ancestor, sha],
        cwd=repo_root,
        capture_output=True,
        text=True,
        check=False,
    )
    return result.returncode == 0


def is_full_sha(value: str | None) -> bool:
    return bool(value) and bool(FULL_SHA_RE.fullmatch(value))


def rev_parse(repo_root: Path, ref: str) -> str:
    result = subprocess.run(
        ["git", "rev-parse", "--verify", ref],
        cwd=repo_root,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        detail = (result.stderr or result.stdout).strip() or f"exit {result.returncode}"
        raise IndexNowError(f"cannot resolve {ref}: {detail}")
    return result.stdout.strip()


def resolve_main_tip(repo_root: Path) -> str:
    for ref in ("refs/heads/main", "main", "origin/main"):
        result = subprocess.run(
            ["git", "rev-parse", "--verify", ref],
            cwd=repo_root,
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout.strip()
    return rev_parse(repo_root, "HEAD")


def validate_explicit_before(repo_root: Path, sha: str) -> str:
    if not is_full_sha(sha):
        raise IndexNowError("after must be a 40-character hex commit SHA")
    tip = resolve_main_tip(repo_root)
    if not is_ancestor(repo_root, sha, tip):
        raise IndexNowError("after is not an ancestor of main")
    return sha


def resolve_before(repo_root: Path, after: str, previous_head: str | None) -> str:
    if previous_head and is_ancestor(repo_root, previous_head, after):
        return previous_head
    return first_parent(repo_root, after)


def github_request_json(url: str, token: str):
    request = urllib.request.Request(
        url,
        headers={
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {token}",
            "X-GitHub-Api-Version": "2022-11-28",
        },
        method="GET",
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.loads(response.read().decode("utf-8"))


def github_get_json(url: str, token: str) -> dict:
    data = github_request_json(url, token)
    if not isinstance(data, dict):
        raise TypeError(f"expected JSON object from {url}")
    return data


def push_before_for_head_sha(repo: str, token: str, head_sha: str) -> str | None:
    url = f"{GITHUB_API}/repos/{repo}/events?per_page=30"
    try:
        data = github_request_json(url, token)
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, json.JSONDecodeError, OSError):
        return None
    if not isinstance(data, list):
        return None
    for event in data:
        if event.get("type") != "PushEvent":
            continue
        payload = event.get("payload") or {}
        if str(payload.get("head")) != head_sha:
            continue
        before = payload.get("before")
        if before and is_full_sha(str(before)):
            return str(before)
    return None


def lookup_push_before_sha() -> str | None:
    explicit = (os.environ.get("INDEXNOW_PUSH_BEFORE") or "").strip()
    if explicit and is_full_sha(explicit):
        return explicit
    token = os.environ.get("GITHUB_TOKEN") or ""
    repo = os.environ.get("GITHUB_REPOSITORY") or ""
    if not token or not repo:
        return None
    head_sha = (os.environ.get("INDEXNOW_AFTER") or "").strip()
    event_path = os.environ.get("GITHUB_EVENT_PATH") or ""
    if event_path:
        try:
            event = json.loads(Path(event_path).read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            event = {}
        workflow_run = event.get("workflow_run") or {}
        if workflow_run.get("event") == "push":
            wr_head = workflow_run.get("head_sha")
            if wr_head and is_full_sha(str(wr_head)):
                head_sha = str(wr_head)
    if not head_sha or not is_full_sha(head_sha):
        return None
    return push_before_for_head_sha(repo, token, head_sha)


def previous_successful_workflow_head(
    repo: str,
    token: str,
    workflow_file: str = WORKFLOW_FILE,
    branch: str = WORKFLOW_BRANCH,
    exclude_run_id: str | None = None,
) -> str | None:
    url = (
        f"{GITHUB_API}/repos/{repo}/actions/workflows/{workflow_file}/runs"
        f"?branch={branch}&status=success&event=workflow_run&per_page=20"
    )
    try:
        data = github_get_json(url, token)
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, json.JSONDecodeError, OSError):
        return None
    exclude = str(exclude_run_id) if exclude_run_id else None
    for run in data.get("workflow_runs") or []:
        if exclude and str(run.get("id")) == exclude:
            continue
        if run.get("event") != "workflow_run":
            continue
        if run.get("conclusion") != "success":
            continue
        head = run.get("head_sha")
        if head:
            return str(head)
    return None


def lookup_previous_successful_head() -> str | None:
    token = os.environ.get("GITHUB_TOKEN") or ""
    repo = os.environ.get("GITHUB_REPOSITORY") or ""
    if not token or not repo:
        return None
    return previous_successful_workflow_head(
        repo,
        token,
        exclude_run_id=os.environ.get("GITHUB_RUN_ID") or None,
    )


def resolve_before_sha(repo_root: Path, after: str, before_override: str | None) -> str:
    if before_override:
        return validate_explicit_before(repo_root, before_override)
    push_before = lookup_push_before_sha()
    if push_before and is_ancestor(repo_root, push_before, after):
        return push_before
    previous = lookup_previous_successful_head()
    if previous and is_ancestor(repo_root, previous, after):
        return previous
    return first_parent(repo_root, after)


def root_key() -> tuple[str, str]:
    return INDEXNOW_KEY, KEY_LOCATION


def build_payload(host: str, key: str, key_location: str, url_list: list[str]) -> dict:
    return {
        "host": host,
        "key": key,
        "keyLocation": key_location,
        "urlList": url_list,
    }


def submit(payload: dict) -> int | str:
    request = urllib.request.Request(
        INDEXNOW_ENDPOINT,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json; charset=utf-8"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return int(response.status)
    except urllib.error.HTTPError as exc:
        return int(exc.code)
    except (urllib.error.URLError, TimeoutError):
        return "error"


def log_status(status: int | str | None, url_count: int) -> None:
    if status is None:
        print(f"status=skipped url_count={url_count}", file=sys.stderr)
    else:
        print(f"status={status} url_count={url_count}", file=sys.stderr)


def env_truthy(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in {"1", "true", "yes", "on"}


def collect_urls(
    repo_root: Path,
    files: list[str] | None,
    before: str | None,
    after: str | None,
    all_locs: bool = False,
) -> list[str]:
    sitemap_locs, alternates = parse_local_urlsets(repo_root)
    if all_locs:
        return sorted(sitemap_locs)[:URL_LIST_CAP]
    urls: set[str] = set()
    if files is not None:
        urls.update(map_changed_files(files, sitemap_locs, alternates))
        return sorted(urls)[:URL_LIST_CAP]

    if not after:
        raise IndexNowError("either --files or --after is required")
    resolved_before = resolve_before_sha(repo_root, after, before)
    changed = changed_files_between(repo_root, resolved_before, after)
    urls.update(map_changed_files(changed, sitemap_locs, alternates))
    urls.update(changed_sitemap_locs(repo_root, resolved_before, after))
    return sorted(url for url in urls if url in sitemap_locs)[:URL_LIST_CAP]


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--dry-run",
        action="store_true",
        default=False,
        help="print the JSON payload and do not send (default if --submit is omitted)",
    )
    mode.add_argument(
        "--submit",
        action="store_true",
        help="POST once to IndexNow; logs HTTP status and URL count only",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        default=env_truthy("INDEXNOW_ALL"),
        help="ping every <loc> in this repo's sitemap (or INDEXNOW_ALL=1)",
    )
    parser.add_argument(
        "--before",
        default=os.environ.get("INDEXNOW_BEFORE") or None,
        help="git SHA for the start of the range (or INDEXNOW_BEFORE)",
    )
    parser.add_argument(
        "--after",
        default=os.environ.get("INDEXNOW_AFTER") or None,
        help="git SHA for the end of the pushed range (or INDEXNOW_AFTER)",
    )
    parser.add_argument(
        "--files",
        nargs="*",
        help="explicit changed paths (skips git); useful for tests",
    )
    parser.add_argument("--repo-root", default=".", help="repository root")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    dry_run = not args.submit
    repo_root = Path(args.repo_root).resolve()
    after = args.after
    if not args.all and args.files is None and not after:
        after = rev_parse(repo_root, "HEAD")
    try:
        url_list = collect_urls(
            repo_root,
            args.files,
            args.before,
            after,
            all_locs=args.all,
        )
        key, key_location = root_key()
    except IndexNowError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    payload = build_payload(HOST, key, key_location, url_list)
    if dry_run:
        json.dump(payload, sys.stdout, indent=2, ensure_ascii=False)
        sys.stdout.write("\n")
        return 0
    if not url_list:
        log_status(None, 0)
        return 0
    status = submit(payload)
    log_status(status, len(url_list))
    return 0 if isinstance(status, int) and 200 <= status < 300 else 1


if __name__ == "__main__":
    sys.exit(main())
