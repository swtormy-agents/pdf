"""Strict whitelist validation for tools/i18n/seo.json editorial_html (build-time guard)."""
import html
import re

PLACEHOLDER = re.compile(r'\b(?:TODO|lorem|placeholder|TBD)\b', re.I)
HREF_OK = re.compile(r'^/[a-z0-9\-/._#]*$')
OPEN_TAG = re.compile(r'^<([a-z]+)>$')
CLOSE_TAG = re.compile(r'^</([a-z]+)>')
ALLOWED = frozenset(('p', 'ul', 'ol', 'li', 'strong', 'em', 'a'))
CHILDREN = {
    'root': frozenset(('p', 'ul', 'ol')),
    'p': frozenset(('strong', 'em', 'a')),
    'ul': frozenset(('li',)),
    'ol': frozenset(('li',)),
    'li': frozenset(('strong', 'em', 'a', 'p')),
    'strong': frozenset(('em', 'a')),
    'em': frozenset(('strong', 'a')),
    'a': frozenset(('strong', 'em')),
}
TEXT_PARENTS = frozenset(('p', 'li', 'strong', 'em', 'a'))


class EditorialHtmlError(ValueError):
    pass


def _parse_open(s, pos):
    if s.startswith('<a href="', pos):
        q = pos + len('<a href="')
        end = s.find('"', q)
        if end < 0:
            raise EditorialHtmlError('unclosed a href')
        href = html.unescape(s[q:end])
        if not HREF_OK.match(href) or href.startswith('//'):
            raise EditorialHtmlError(f'bad href: {href!r}')
        if s[end:end + 2] != '">':
            raise EditorialHtmlError('bad a tag')
        return 'a', end + 2
    chunk = s[pos:]
    if not chunk.startswith('<'):
        raise EditorialHtmlError('expected tag')
    gt = chunk.find('>')
    if gt < 0:
        raise EditorialHtmlError('unclosed tag')
    inner = chunk[1:gt]
    if not OPEN_TAG.match('<' + inner + '>'):
        raise EditorialHtmlError(f'bad open tag: {inner!r}')
    tag = OPEN_TAG.match('<' + inner + '>').group(1)
    if tag not in ALLOWED or tag == 'a':
        raise EditorialHtmlError(f'bad open tag: {inner!r}')
    return tag, pos + gt + 1


def validate_editorial_html(s):
    """Tokenize s; must consume the entire string or raise EditorialHtmlError."""
    if not isinstance(s, str) or not s.strip():
        raise EditorialHtmlError('missing editorial_html')
    if PLACEHOLDER.search(s):
        raise EditorialHtmlError('placeholder marker')
    stack = ['root']
    pos = 0
    n = len(s)
    while pos < n:
        if s[pos] == '<':
            if s.startswith('<!', pos) or s.startswith('<?', pos):
                raise EditorialHtmlError('forbidden markup')
            if s.startswith('</', pos):
                m = CLOSE_TAG.match(s[pos:])
                if not m:
                    raise EditorialHtmlError('bad close tag')
                tag = m.group(1)
                if tag not in ALLOWED:
                    raise EditorialHtmlError('bad close tag')
                if len(stack) == 1:
                    raise EditorialHtmlError('unbalanced')
                if stack[-1] != tag:
                    raise EditorialHtmlError('tag mismatch')
                stack.pop()
                pos += m.end()
                continue
            tag, pos = _parse_open(s, pos)
            parent = stack[-1]
            if tag not in CHILDREN.get(parent, frozenset()):
                raise EditorialHtmlError(f'{tag} not allowed in {parent}')
            stack.append(tag)
        else:
            end = s.find('<', pos)
            if end < 0:
                end = n
            text = s[pos:end]
            if '<' in text or '>' in text:
                raise EditorialHtmlError('stray angle bracket')
            if text and stack[-1] not in TEXT_PARENTS:
                raise EditorialHtmlError('text outside inline context')
            pos = end
    if len(stack) != 1:
        raise EditorialHtmlError('unclosed tags')
    if pos != n:
        raise EditorialHtmlError('trailing content')


def editorial_section(validated_html):
    """Validated HTML only: add link classes for site styling."""
    body = validated_html.replace('<a href=', '<a class="link link-primary" href=')
    return (
        '<section class="editorial mt-12 max-w-3xl text-base text-base-content/90" aria-label="About this tool">\n'
        f'<div class="editorial-body space-y-3 leading-relaxed">{body}</div></section>\n'
    )
