"""僅分類 ## 標題；表格／程式碼等保護區域由文件掃描端先排除。"""
import re

from config.markdown_headings import LIST_PREFIX_PATTERN, MARKER_PATTERNS
from config.markdown_tagging import MAIN_TITLE, SECTION_PATTERN, DYNAMIC_MARKER_TYPES
from schemas import TagHeading

_HEADING = re.compile(r'^ {0,3}##[ \t]+(.+?)[ \t]*$')
_SECTION = re.compile(SECTION_PATTERN)
_LIST = re.compile(LIST_PREFIX_PATTERN)
_DYNAMIC = tuple((kind, re.compile('^'+pattern)) for kind, pattern in MARKER_PATTERNS
                 if kind in DYNAMIC_MARKER_TYPES)


def classify_tag_heading(line: str) -> TagHeading | None:
    """不重新做20字元候選篩選；既有 ## 即為標題來源，井號不決定層級。"""
    match = _HEADING.fullmatch(line)
    if not match:
        return None
    title = match[1]
    comparison = _LIST.sub('', title, count=1)
    section = _SECTION.match(comparison)
    main_candidate = comparison[section.end():] if section else comparison
    if re.sub(r'\s+', '', main_candidate) == MAIN_TITLE:
        return TagHeading('main', title)
    if section and comparison[section.end():].strip():
        return TagHeading('section', title, 'chinese_comma')
    for kind, pattern in _DYNAMIC:
        prefix = pattern.match(comparison)
        if prefix and comparison[prefix.end():].strip():
            return TagHeading('dynamic', title, kind)
    return TagHeading('untracked', title)
