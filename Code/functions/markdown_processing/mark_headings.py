"""標題分類及冒號段落合併；純本機規則，不讀寫檔、不載入模型。

參考 markdown_title.py 的編號與標點概念，依新規格重新實作；不匯入、
複製或修改舊程式，不使用其拆行、底線、自訂標籤與清除標題流程。
"""
import re
from bisect import bisect_right

from config.markdown_headings import (
    EXCLUDED_ENDINGS, MARKER_PATTERNS,
    MAX_CANDIDATE_LENGTH, RULE_VERSION, LIST_PREFIX_PATTERN, PAGE_NUMBER_PATTERN,
    APPENDIX_PREFIX_PATTERN, PURE_YEAR_PATTERN, COLON_ENDINGS, UNLIMITED_LENGTH_MARKERS,
    MULTI_YEAR_DESCRIPTION_PATTERN, NOTE_PREFIX_PATTERN,
)
from functions.markdown_processing.numeric_lines import is_numeric_line
from schemas import HeadingChange, HeadingMarkResult

_MARKERS = tuple((kind, re.compile(r'^[ \t\u3000]*(' + pattern + r')(.*)$'))
                 for kind, pattern in MARKER_PATTERNS)
_TAG = re.compile(r'''<(?:"[^"]*"|'[^']*'|[^'"<>])*>''')
_TABLE_LIKE = re.compile(r'<\s*/?\s*table\b', re.IGNORECASE)
_FENCE = re.compile(r'^ {0,3}(`{3,}|~{3,})(.*)$')
_NEXT = re.compile(r'[<\r\n]')
_LIST_PREFIX = re.compile(LIST_PREFIX_PATTERN)
_PAGE_NUMBER = re.compile(PAGE_NUMBER_PATTERN)
_APPENDIX = re.compile(APPENDIX_PREFIX_PATTERN)
_NOTE = re.compile(NOTE_PREFIX_PATTERN)
_PURE_YEAR = re.compile(PURE_YEAR_PATTERN)
_MULTI_YEAR_DESCRIPTION = re.compile(MULTI_YEAR_DESCRIPTION_PATTERN)
_MD_HEADING = re.compile(r'^([ \t\u3000]*)(#{1,6})[ \t\u3000]*(.*)$')


class TableBoundaryError(ValueError):
    """表格邊界不能可靠確認；呼叫端不得保存部分修改結果。"""


def _colon_paragraphs(lines, protected):
    """定位冒號段落；保護區及獨立控制標籤不可被併入標題。"""
    spans, start, last_colon = {}, None, None

    def flush():
        if start is not None and last_colon is not None:
            parts = []
            prefix = ''
            for ordinal, line in enumerate(lines[start:last_colon + 1]):
                if ordinal == 0 and '。' in line:
                    cut = line.rfind('。') + 1
                    prefix = mark_missing_headings(line[:cut]).markdown
                    newline = line[len(line.rstrip('\r\n')):] or '\n'
                    prefix += newline
                    line = line[cut:]
                value = line.rstrip('\r\n').lstrip('\ufeff').strip()
                match = _MD_HEADING.fullmatch(value)
                if value:
                    parts.append((match[3] if match else value).strip())
            bom = '\ufeff' if not prefix and start == 0 and lines[start].startswith('\ufeff') else ''
            spans[start] = (last_colon, prefix + bom + '## ' + ' '.join(parts))

    for index, line in enumerate(lines):
        value = line.strip().lstrip('\ufeff')
        heading = _MD_HEADING.fullmatch(value)
        title = heading[3] if heading else value
        barrier = (index in protected or not value or _TAG.fullmatch(value)
                   or _PAGE_NUMBER.fullmatch(value) or _APPENDIX.match(re.sub(r'\s+', '', title))
                   or _NOTE.match(re.sub(r'\s+', '', title))
                   or _PURE_YEAR.fullmatch(re.sub(r'\s+', '', title))
                   or (heading and heading[2] != '##'))
        if barrier:
            flush()
            start, last_colon = None, None
            continue
        # 新編號開啟另一項；冒號最多回收到本項編號，不跨入上一項。
        candidate_line = _LIST_PREFIX.sub('', title, count=1)
        normalized = re.sub(r'\s+', '', candidate_line)
        if any(pattern.match(normalized) for _, pattern in _MARKERS):
            flush()
            start, last_colon = index, None
        if '。' in value:
            # 句號也分隔收集範圍；保留前句，只把最後句號之後納入冒號標題。
            flush()
            start, last_colon = index, None
        if start is None:
            start = index
        if value.endswith(COLON_ENDINGS):
            last_colon = index
    flush()
    return spans


def _protected_lines(text, lines, *, table_ranges=None, code_lines=None, full_table_ranges=None):
    """只定位原文區間，不解析／重新序列化 HTML，保留字元與換行。

    線性掃描字元及標籤；註解與程式碼中的 table 字串不視為 HTML。
    table 可跨行、含屬性、大小寫不同或巢狀；未閉合／多餘閉合即失敗。
    """
    starts, offset = [], 0
    for line in lines:
        starts.append(offset)
        offset += len(line)
    protected = set()

    def line_at(pos):
        return bisect_right(starts, pos)-1

    def protect(start, end):
        protected.update(range(line_at(start), line_at(max(start, end-1))+1))

    pos, table_stack, fence = 0, [], None
    while pos < len(text):
        index = line_at(pos)
        if pos == starts[index] and not table_stack:
            line = lines[index].rstrip('\r\n')
            if fence:
                protected.add(index)
                if code_lines is not None:
                    code_lines.add(index)
                if re.fullmatch(r' {0,3}' + re.escape(fence[0]) + '{' + str(fence[1]) + r',}[ \t]*', line):
                    fence = None
                pos += len(lines[index])
                continue
            match = _FENCE.match(line)
            if match and (match[1][0] != '`' or '`' not in match[2]):
                fence = (match[1][0], len(match[1]))
                protected.add(index)
                if code_lines is not None:
                    code_lines.add(index)
                pos += len(lines[index])
                continue
            # Markdown 縮排程式碼原樣保護，避免把程式碼中的編號當標題。
            if line.startswith(('    ', '\t')):
                protected.add(index)
                if code_lines is not None:
                    code_lines.add(index)
                pos += len(lines[index])
                continue
        if text.startswith('<!--', pos):
            close = text.find('-->', pos+4)
            end = len(text) if close < 0 else close+3
            protect(pos, end)
            pos = end
            continue
        if text[pos] == '<':
            tag = _TAG.match(text, pos)
            if tag:
                raw = tag[0]
                if _TABLE_LIKE.match(raw):
                    if re.match(r'<table(?=[\s/>])', raw, re.IGNORECASE):
                        if raw.rstrip().endswith('/>'):
                            raise TableBoundaryError(f'Markdown 第 {index+1} 行：table 不可自閉合')
                        table_stack.append(pos)
                    elif re.fullmatch(r'</table\s*>', raw, re.IGNORECASE):
                        if not table_stack:
                            raise TableBoundaryError(f'Markdown 第 {index+1} 行：多餘 </table>')
                        start = table_stack.pop()
                        if not table_stack:
                            protect(start, tag.end())
                            if table_ranges is not None:
                                table_ranges.append((start, tag.end()))
                    else:
                        raise TableBoundaryError(f'Markdown 第 {index+1} 行：table 標籤格式異常')
                pos = tag.end()
                continue
            if _TABLE_LIKE.match(text, pos):
                raise TableBoundaryError(f'Markdown 第 {index+1} 行：table 標籤不完整')
        # 非標籤文字跳到下一個標籤或換行，避免逐字做二分搜尋。
        if text[pos] in '\r\n':
            pos += 2 if text.startswith('\r\n', pos) else 1
            continue
        match = _NEXT.search(text, pos+1)
        pos = len(text) if not match else match.start()
    if table_stack:
        raise TableBoundaryError(f'Markdown 第 {line_at(table_stack[0])+1} 行：<table> 未閉合')
    from functions.markdown_processing.pipe_tables import pipe_tables
    for start, end, first_line, last_line in pipe_tables(text, protected):
        protected.update(range(first_line, last_line))
        if table_ranges is not None:
            table_ranges.append((start, end))
    if table_ranges is not None:
        table_ranges.sort()
    from config.suspected_tables import START_TAG, END_TAG
    suspect_start = None
    for index, line in enumerate(lines):
        if index in protected:
            continue
        value = line.strip()
        if value == START_TAG:
            if suspect_start is not None:
                raise TableBoundaryError('cannotfindtable 標記不可巢狀')
            suspect_start = index
        elif value == END_TAG:
            if suspect_start is None:
                raise TableBoundaryError('多餘的 cannotfindtable 結束標記')
            protected.update(range(suspect_start, index + 1))
            if full_table_ranges is not None:
                full_table_ranges.append((starts[suspect_start], starts[index]+len(line)))
            suspect_start = None
    if suspect_start is not None:
        raise TableBoundaryError('cannotfindtable 標記未閉合')
    return protected


def mark_missing_headings(text: str) -> HeadingMarkResult:
    """完整驗證邊界後再產生結果；20字元不計編號後內容的空白。"""
    lines = text.splitlines(keepends=True)
    if not lines:
        return HeadingMarkResult(text, (), RULE_VERSION)
    protected = _protected_lines(text, lines)
    colon_spans = _colon_paragraphs(lines, protected)
    consumed_through = -1
    output, changes = [], []
    for index, line in enumerate(lines):
        if index <= consumed_through:
            continue
        if index in colon_spans:
            end, modified = colon_spans[index]
            original = ''.join(lines[index:end + 1]).rstrip('\r\n')
            if original != modified:
                changes.append(HeadingChange(index + 1, original, modified, 'colon:merged_paragraph'))
            tail = lines[end][len(lines[end].rstrip('\r\n')):]
            output.append(modified + tail)
            consumed_through = end
            continue
        content = line.rstrip('\r\n')
        bom = '\ufeff' if index == 0 and content.startswith('\ufeff') else ''
        body = content[len(bom):]
        prefix = ''
        reason = ''
        if index not in protected:
            heading = _MD_HEADING.fullmatch(body)
            title = heading[3] if heading else body.lstrip(' \t\u3000')
            replacement = None
            if (heading is None or heading[2] == '##') and is_numeric_line(title):
                replacement = heading[1] + title if heading else body
                reason = 'numeric:remove_double_hash'
            elif _APPENDIX.match(re.sub(r'\s+', '', title)):
                replacement, reason = '#### ' + title, 'appendix:four_hashes'
            elif _NOTE.match(re.sub(r'\s+', '', title)):
                replacement, reason = '### ' + title, 'note:triple_hash'
            elif _PURE_YEAR.fullmatch(re.sub(r'\s+', '', title)):
                replacement, reason = '## ' + title, 'year:double_hash'
            elif _MULTI_YEAR_DESCRIPTION.fullmatch(re.sub(r'\s+', '', title)):
                replacement, reason = '## ' + title, 'year_description:double_hash'
            elif heading and heading[2] == '##':
                candidate_line = _LIST_PREFIX.sub('', title, count=1)
                normalized = re.sub(r'\s+', '', candidate_line)
                if not any(pattern.match(normalized) for _, pattern in _MARKERS):
                    replacement, reason = heading[1] + title, 'unnumbered:remove_double_hash'
                else:
                    for kind, pattern in _MARKERS:
                        match = pattern.match(normalized)
                        if kind in UNLIMITED_LENGTH_MARKERS and match:
                            candidate = match[2].strip()
                            if not candidate or candidate[-1] in EXCLUDED_ENDINGS:
                                replacement, reason = heading[1] + title, 'english:excluded_ending_or_empty'
                            break
            if replacement is not None:
                modified = bom + replacement
                if modified != content:
                    changes.append(HeadingChange(index+1, content, modified, reason))
                output.append(modified + line[len(content):])
                continue
        if index not in protected and not body.lstrip().startswith('#') and not _PAGE_NUMBER.fullmatch(body):
            # 僅判斷時忽略一個列表前綴；輸出使用原 body，不刪除 - 或空白。
            candidate_line = _LIST_PREFIX.sub('', body, count=1)
            # 與既有 ## 的辨識一致：忽略排版空白比對編號，
            # 再映回原文取得內容；字數不計空白，標點及輸出空白保留。
            positions = list(re.finditer(r'\S', candidate_line))
            normalized = ''.join(part[0] for part in positions)
            for kind, pattern in _MARKERS:
                match = pattern.match(normalized)
                if not match:
                    continue
                marker_end = positions[match.end(1) - 1].end()
                candidate = candidate_line[marker_end:].strip()
                if candidate and (kind in UNLIMITED_LENGTH_MARKERS or len(re.sub(r'\s+', '', candidate)) <= MAX_CANDIDATE_LENGTH):
                    if candidate[-1] not in EXCLUDED_ENDINGS:
                        prefix, reason = '## ', f'{kind}:missing_heading'
                break
        if prefix:
            modified = bom + prefix + body
            changes.append(HeadingChange(index+1, content, modified, reason))
            output.append(modified + line[len(content):])
        else:
            output.append(line)
    return HeadingMarkResult(''.join(output), tuple(changes), RULE_VERSION)


def recheck_dash_number_headings(text: str) -> HeadingMarkResult:
    """末段重查- 1.，並移除##數字標題的列表前綴；保留###條列。"""
    lines = text.splitlines(keepends=True)
    protected = _protected_lines(text, lines)
    number_dot = next(pattern for kind, pattern in _MARKERS if kind == 'number_dot')
    output, changes = [], []
    for index, line in enumerate(lines):
        original = line.rstrip('\r\n')
        if index not in protected and _LIST_PREFIX.match(original):
            numbered = _LIST_PREFIX.sub('', original, count=1)
            if number_dot.match(re.sub(r'\s+', '', numbered)):
                result = mark_missing_headings(line)
                if result.changes:
                    modified = result.markdown.rstrip('\r\n')
                    changes.append(HeadingChange(index+1, original, modified,
                                                 'dash_number:final_heading_recheck'))
                    output.append(result.markdown)
                    continue
        output.append(line)
    # 首輪補標題及本輪重查產生的##都要清理，但###條列不能變成標題。
    cleaned = []
    for index, line in enumerate(output):
        for part in line.splitlines(keepends=True):
            original = part.rstrip('\r\n')
            heading = _MD_HEADING.fullmatch(original)
            if heading and heading[2] == '##' and _LIST_PREFIX.match(heading[3]):
                title = _LIST_PREFIX.sub('', heading[3], count=1)
                normalized = re.sub(r'\s+', '', title)
                if any(pattern.match(normalized) for kind, pattern in _MARKERS
                       if kind in ('number_dot', 'parenthesized_number')):
                    # 每個output項目對應一個原始輸入行，拆行也沿用來源起行。
                    if index not in protected:
                        modified = original[:len(original)-len(heading[3])]+title
                        changes.append(HeadingChange(index+1, original, modified,
                                                     'number_heading:remove_list_prefix'))
                        part = modified+part[len(original):]
            cleaned.append(part)
    return HeadingMarkResult(''.join(cleaned), tuple(changes), RULE_VERSION)
