"""FAQ answer markup: [text](href) links; JSON-LD uses plain source text."""
import html
import re

FAQ_PATH_OK = re.compile(r'^/[a-z0-9\-/._#]*$')
FAQ_LINK = re.compile(r'\[([^\]]+)\]\(([^)\s]+)\)')


def faq_link_href_ok(h: str) -> bool:
    if h.startswith('https://noclaudkit.com'):
        h = h[len('https://noclaudkit.com') :]
    if not h.startswith('/') or h.startswith('//'):
        return False
    return FAQ_PATH_OK.fullmatch(h) is not None


def faq_plain(a: str) -> str:
    def sub(m):
        if not faq_link_href_ok(m.group(2)):
            raise ValueError(f'bad FAQ link href: {m.group(2)!r}')
        return m.group(1)

    return FAQ_LINK.sub(sub, a)


def faq_answer_html(a: str) -> str:
    out, pos = '', 0
    for m in FAQ_LINK.finditer(a):
        href = m.group(2)
        if not faq_link_href_ok(href):
            raise ValueError(f'bad FAQ link href: {href!r}')
        out += html.escape(a[pos : m.start()], quote=True)
        out += (
            f'<a class="link link-primary" href="{html.escape(href, quote=True)}">'
            f'{html.escape(m.group(1), quote=True)}</a>'
        )
        pos = m.end()
    return out + html.escape(a[pos:], quote=True)
