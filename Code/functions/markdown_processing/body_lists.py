"""以內文為起點，回查誤標的條列；不改文字、不跨表格或控制邊界。"""
import re

from config.body_lists import RULE_VERSION, MARKER_PATTERN
from config.markdown_headings import COLON_ENDINGS, LIST_PREFIX_PATTERN
from functions.markdown_processing.mark_headings import _protected_lines, _TAG
from functions.markdown_processing.numeric_lines import is_numeric_line
from schemas import HeadingChange

_MARKER = re.compile(r'^(?:' + MARKER_PATTERN + r')')
_HEADING = re.compile(r'^(#{1,6})[ \t]*(.*)$')
_BULLET = re.compile(LIST_PREFIX_PATTERN)


def _item(line):
    value = line.strip()
    heading = _HEADING.fullmatch(value)
    hashes = heading[1] if heading else ''
    if hashes and hashes not in ('##', '###'):
        return None
    title = heading[2] if heading else value
    compact = re.sub(r'\s+', '', _BULLET.sub('', title, count=1))
    if is_numeric_line(compact):
        return None
    match = _MARKER.match(compact)
    if not match or not compact[match.end():]:
        return None
    # 例如1. A.說明：外層自動列表號不遮蔽內層英文字母編號。
    inner = _MARKER.match(compact[match.end():])
    if inner and match['dot'] and match['dot'].isdigit():
        token = next(v for v in inner.groups() if v is not None)
        if token.isalpha() and compact[match.end()+inner.end():]:
            match = inner
    token = next(v for v in match.groups() if v is not None)
    family = ('number' if token.isdigit() else 'upper' if token.isupper() else 'lower',
              'dot' if match['dot'] else 'paren' if match['paren'] else 'wide')
    ordinal = int(token) if token.isdigit() else ord(token.lower())-ord('a')+1
    return family, ordinal, hashes


def mark_body_lists(text):
    """輸入為已補標題的note後內容；回傳文字、變更及待核對跳號。

    只有普通內文是新辨識起點；已產生的###只支援重跑，不把整組##當起點。
    """
    lines = text.splitlines(keepends=True)
    protected = _protected_lines(text, lines)
    items = {i: item for i, line in enumerate(lines)
             if i not in protected and (item := _item(line)) is not None}
    nonempty = [i for i, line in enumerate(lines) if line.strip()]
    previous = {b: a for a, b in zip(nonempty, nonempty[1:])}

    def neighbour(index, direction, family):
        for j in range(index+direction, len(lines) if direction > 0 else -1, direction):
            value = lines[j].strip()
            if j in protected or _TAG.fullmatch(value):
                return None
            if j in items:
                return j if items[j][0] == family else None
            if value.startswith('#'):
                return None
        return None

    selected, handled, gaps = set(), set(), []
    for seed, (family, _, hashes) in items.items():
        if hashes == '##' or seed in handled:
            continue
        group = [seed]
        # 回查同型前項；##只有正確的前一號才可被特殊回查納入。
        while (j := neighbour(group[0], -1, family)) is not None:
            if items[j][1] >= items[group[0]][1]:
                break
            if items[j][2] == '##' and items[j][1]+1 != items[group[0]][1]:
                break
            group.insert(0, j)
        while (j := neighbour(group[-1], 1, family)) is not None:
            if items[j][1] <= items[group[-1]][1]:
                break
            if items[j][2] == '##' and items[j][1] != items[group[-1]][1]+1:
                break
            group.append(j)
        first = group[0]
        before = previous.get(first)
        prior = _HEADING.fullmatch(lines[before].strip()) if before is not None else None
        colon = bool(items[first][1] == 1 and prior and prior[1] == '##'
                     and prior[2].rstrip().endswith(COLON_ENDINGS))
        adjacent = any(previous.get(b) == a for a, b in zip(group, group[1:]))
        # 首項被誤標##且為1/a時，依確認規則必須再核對前面的冒號標題。
        if items[first][2] == '##' and items[first][1] == 1 and not colon:
            continue
        if not (colon or adjacent):
            continue
        selected.update(group)
        handled.update(group)
        for a, b in zip(group, group[1:]):
            if items[b][1] > items[a][1]+1:
                gaps.append({'line_number': b+1, 'marker_type': list(family),
                             'missing_ordinals': list(range(items[a][1]+1, items[b][1])),
                             'status': '未找到原文編號，不補造內容'})
    changes = []
    for i in sorted(selected):
        original = lines[i].rstrip('\r\n')
        value = original.lstrip(' \t\u3000')
        indent = original[:len(original)-len(value)]
        heading = _HEADING.fullmatch(value)
        title = heading[2] if heading else value
        modified = indent+'### '+title
        if modified != original:
            changes.append(HeadingChange(i+1, original, modified, 'body_list:triple_hash'))
            lines[i] = modified+lines[i][len(original):]
    return ''.join(lines), tuple(changes), {'version': RULE_VERSION,
            'changed_count': len(changes), 'gaps': gaps}


def heading_line_origins(text, changes):
    """將補標題後行號映回其輸入；合併／拆行都指向該變更原始起行。"""
    origins, cursor = [], 0
    for change in changes:
        start = change.line_number-1
        origins.extend(range(cursor, start))
        origins.extend([start]*max(1, len(change.modified.splitlines())))
        cursor = start+max(1, len(change.original.splitlines()))
    origins.extend(range(cursor, len(text.splitlines())))
    return origins
