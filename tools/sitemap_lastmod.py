"""Per-page lastmod from git history of i18n JSON slices (seo.json / faq.json).

Walks every commit that touched each file (merges included, newest first). At each commit,
compares json[lang][page_key] to the first parent's blob; the first diff seen for a slice is
the most recent content change for that page (keyed by lang + seo/faq page key).
"""
import json
import re
import subprocess

LANGS = ('en', 'ru', 'zh')
PAGE_KEYS = ('hub', 'merge', 'split', 'organize', 'jpg')
_I18N_JSON_CACHE: dict[tuple[str, str], object] = {}


def _git(cmd, *, cwd=None):
    return subprocess.run(cmd, capture_output=True, text=True, cwd=cwd)


def git_json_at(sha: str, path: str, *, cwd=None, cache: dict | None = None) -> dict | None:
    c = _I18N_JSON_CACHE if cache is None else cache
    k = (sha, path)
    if k in c:
        return c[k]
    r = _git(['git', 'show', f'{sha}:{path}'], cwd=cwd)
    if r.returncode != 0 or not r.stdout.strip():
        c[k] = None
        return None
    try:
        c[k] = json.loads(r.stdout)
    except json.JSONDecodeError:
        c[k] = None
    return c[k]


def _first_parent(sha: str, *, cwd=None) -> str | None:
    r = _git(['git', 'rev-parse', f'{sha}^'], cwd=cwd)
    if r.returncode != 0:
        return None
    p = r.stdout.strip()
    return p or None


def subtree_lastmods(path: str, *, cwd=None, cache: dict | None = None) -> dict[tuple[str, str], str]:
    """Return {(lang, page_key): commit-date} for the newest change of each subtree in path."""
    cache = {} if cache is None else cache
    out: dict[tuple[str, str], str] = {}
    r = _git(['git', 'log', '--format=%H %cs', '--', path], cwd=cwd)
    if r.returncode != 0:
        return out
    for line in r.stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        sha, cs = line.split(None, 1)
        cur = git_json_at(sha, path, cwd=cwd, cache=cache)
        if not isinstance(cur, dict):
            continue
        par_sha = _first_parent(sha, cwd=cwd)
        par = git_json_at(par_sha, path, cwd=cwd, cache=cache) if par_sha else None
        for lang in LANGS:
            bloc = cur.get(lang)
            if not isinstance(bloc, dict):
                continue
            for key in PAGE_KEYS:
                if key not in bloc:
                    continue
                sub = bloc.get(key)
                old = (par.get(lang) or {}).get(key) if isinstance(par, dict) else None
                if sub != old and (lang, key) not in out:
                    out[(lang, key)] = cs
    return out


def file_lastmod(path: str, *, cwd=None) -> str:
    """Most recent commit touching a single path (any commit, including merges)."""
    r = _git(['git', 'log', '-1', '--format=%cs', '--', path], cwd=cwd)
    return r.stdout.strip() if r.returncode == 0 else ''


def clear_json_cache():
    _I18N_JSON_CACHE.clear()


def page_lastmod(
    lang: str,
    page: str,
    page_seo: dict[str, str],
    *,
    cwd=None,
    seo_dates: dict[tuple[str, str], str] | None = None,
    faq_dates: dict[tuple[str, str], str] | None = None,
    cache: dict | None = None,
) -> str:
    """Max commit date across UI json and page-specific seo/faq slices (+ extras per page kind)."""
    dates: list[str] = []
    d = file_lastmod(f'tools/i18n/{lang}.json', cwd=cwd)
    if d:
        dates.append(d)
    if page == 'privacy.html':
        d = file_lastmod('tools/i18n/privacy.json', cwd=cwd)
        if d:
            dates.append(d)
    elif page == 'licenses.html':
        for fp in ('tools/i18n/licenses-page.json', 'licenses'):
            d = file_lastmod(fp, cwd=cwd)
            if d:
                dates.append(d)
    elif page in page_seo:
        key = page_seo[page]
        if seo_dates is None:
            seo_dates = subtree_lastmods('tools/i18n/seo.json', cwd=cwd, cache=cache)
        if faq_dates is None:
            faq_dates = subtree_lastmods('tools/i18n/faq.json', cwd=cwd, cache=cache)
        if (lang, key) in seo_dates:
            dates.append(seo_dates[(lang, key)])
        if (lang, key) in faq_dates:
            dates.append(faq_dates[(lang, key)])
        if page == 'index.html':
            for fp in ('tools/i18n/header.json', 'tools/i18n/interlink.json'):
                d = file_lastmod(fp, cwd=cwd)
                if d:
                    dates.append(d)
    dates = [x for x in dates if x and re.fullmatch(r'\d{4}-\d{2}-\d{2}', x)]
    if not dates:
        return ''
    return max(dates)
