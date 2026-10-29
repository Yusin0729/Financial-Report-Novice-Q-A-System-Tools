"""依使用者指定接續詞分組相鄰HTML表格；只判斷區間，不改寫HTML。"""
import re
from bisect import bisect_right
from config.markdown_blocks import TABLE_CONTINUATION_MARKERS
from config.markdown_headings import APPENDIX_MARKDOWN_PATTERN


def group_continued_tables(text, ranges, offsets, code_lines):
    groups, joins = [], []
    for ordinal, span in enumerate(ranges):
        markers = []
        if ordinal:
            previous_end = ranges[ordinal - 1][1]
            gap = text[previous_end:span[0]]
            visible, position = [], previous_end
            for line in gap.splitlines(keepends=True):
                if bisect_right(offsets, position) - 1 not in code_lines:
                    visible.append(line)
                position += len(line)
            # 註解與程式碼裡的文字是資料，不觸發結構合併。
            between = re.sub(r'<!--.*?-->', '', ''.join(visible), flags=re.S)
            normalized = re.sub(r'\s+', '', between)
            markers = [marker for marker in TABLE_CONTINUATION_MARKERS if marker in normalized]
            if re.search(APPENDIX_MARKDOWN_PATTERN, between, re.M):
                markers = []  # 附表標題必須保留為範圍邊界，不被前一表接續吞掉。
        if markers:
            groups[-1].append(span)
            joins.append({'left_table': ordinal, 'right_table': ordinal + 1,
                          'markers': markers, 'policy': 'either_marker_ignore_whitespace'})
        else:
            groups.append([span])
    return groups, joins
