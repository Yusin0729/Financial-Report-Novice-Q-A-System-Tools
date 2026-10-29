"""Remove OCR-inserted horizontal whitespace between adjacent Han characters."""
import re


VERSION = 'cjk-intercharacter-space-cleanup/1.0'
_HAN = r'\u3400-\u4dbf\u4e00-\u9fff'
_SPACE = r'[\t\f\v \u00a0\u1680\u2000-\u200a\u202f\u205f\u3000]+'
_BETWEEN_HAN = re.compile(rf'(?<=[{_HAN}])({_SPACE})(?=[{_HAN}])')
_MARKUP_OR_CODE = re.compile(
    r'<!--.*?-->|</?[A-Za-z][A-Za-z0-9:_-]*(?:\s[^<>]*?)?/?>|(`+)[^`\r\n]*`+',
    re.S,
)
_FENCE = re.compile(r'^[ \t]{0,3}(`{3,}|~{3,})')


def _clean_text_segment(value):
    removed = 0

    def replace(match):
        nonlocal removed
        removed += len(match.group(1))
        return ''

    cleaned = _BETWEEN_HAN.sub(replace, value)
    return cleaned, removed


def clean_intercharacter_spaces(text):
    """Clean text nodes across the document while retaining lines and markup.

    HTML tags/comments, inline code spans, and fenced code blocks remain exact.
    Only horizontal whitespace between two Han characters is removed; spaces
    adjoining English, digits, punctuation, or line boundaries are untouched.
    """
    output = []
    removed = 0
    in_fence = None
    in_comment = False

    for line in text.splitlines(keepends=True):
        if in_fence:
            output.append(line)
            fence = _FENCE.match(line)
            if fence and fence.group(1)[0] == in_fence[0] and len(fence.group(1)) >= len(in_fence):
                in_fence = None
            continue

        fence = _FENCE.match(line)
        if fence:
            in_fence = fence.group(1)
            output.append(line)
            continue

        cursor = 0
        pieces = []
        while cursor < len(line):
            if in_comment:
                close = line.find('-->', cursor)
                if close < 0:
                    pieces.append(line[cursor:])
                    cursor = len(line)
                else:
                    end = close + 3
                    pieces.append(line[cursor:end])
                    cursor = end
                    in_comment = False
                continue

            comment = line.find('<!--', cursor)
            token = _MARKUP_OR_CODE.search(line, cursor)
            if comment >= 0 and (token is None or comment <= token.start()):
                segment, count = _clean_text_segment(line[cursor:comment])
                close = line.find('-->', comment + 4)
                end = close + 3 if close >= 0 else len(line)
                pieces.extend((segment, line[comment:end]))
                removed += count
                if close < 0:
                    in_comment = True
                cursor = end
                continue
            if token is None:
                segment, count = _clean_text_segment(line[cursor:])
                pieces.append(segment)
                removed += count
                cursor = len(line)
                continue

            segment, count = _clean_text_segment(line[cursor:token.start()])
            pieces.extend((segment, token.group(0)))
            removed += count
            cursor = token.end()

        output.append(''.join(pieces))

    return ''.join(output), {'version': VERSION, 'removed_whitespace_count': removed}
