"""以標準庫解析 HTML，展開合併儲存格，保留表外文字及數值。

不複製舊參考程式；不猜測同上、空白格或表格的欄位語意。
"""
import re
from html.parser import HTMLParser


def _cell_text(parts):
    return re.sub(r'[\t\r\f\v ]+', ' ', ''.join(parts)).strip()


def expand_rows(rows):
    """只複製明確 rowspan/colspan 原值；碰撞或超出列範圍即拒絕。"""
    grid = {}
    for r, cells in enumerate(rows):
        col = 0
        for text, rowspan, colspan in cells:
            while (r, col) in grid:
                col += 1
            if r + rowspan > len(rows):
                raise ValueError('rowspan超出實際表格列數')
            for rr in range(r, r + rowspan):
                for cc in range(col, col + colspan):
                    if (rr, cc) in grid:
                        raise ValueError('合併儲存格位置重疊')
                    grid[rr, cc] = text
            col += colspan
    if not rows or not grid:
        raise ValueError('空表格，不能當成功')
    width = max(c for _, c in grid) + 1
    return [[grid.get((r, c), '') for c in range(width)] for r in range(len(rows))]


def pipe_table(grid):
    def escape(value):
        return value.replace('\\', '\\\\').replace('|', '\\|').replace('\n', '<br>')
    lines = ['| ' + ' | '.join(escape(cell) for cell in row) + ' |' for row in grid]
    # Markdown 語法需要分隔列；沿用首列，不猜測或新增財務欄名。
    lines.insert(1, '| ' + ' | '.join('---' for _ in grid[0]) + ' |')
    return '\n'.join(lines)


class ContentParser(HTMLParser):
    """跨頁註解／自訂邊界只移除語法，不移除中間文字或重複表頭。"""
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts = []
        self.rows = None
        self.row = None
        self.cell = None
        self.cell_tag = None
        self.spans = None
        self.tables = []
        self.heading = None

    def append(self, text):
        if self.cell is not None:
            self.cell.append(text)
        elif self.rows is not None:
            if text.strip():
                raise ValueError('表格結構中出現儲存格外文字')
        else:
            self.parts.append(text)

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == 'table':
            if self.rows is not None:
                raise ValueError('暫不支援巢狀表格，請人工確認')
            self.parts.append('\n\n')
            self.rows = []
        elif tag == 'tr':
            if self.rows is None or self.row is not None or self.cell is not None:
                raise ValueError('tr邊界不完整')
            self.row = []
        elif tag in ('td', 'th'):
            if self.row is None or self.cell is not None:
                raise ValueError('儲存格邊界不完整')
            spans = []
            for key in ('rowspan', 'colspan'):
                raw = attrs.get(key, '1')
                if not raw or not re.fullmatch(r'[1-9]\d*', raw):
                    raise ValueError(f'{key}必須為正整數')
                spans.append(int(raw))
            self.spans = spans
            self.cell, self.cell_tag = [], tag
        elif tag == 'br':
            self.append('\n')
        elif re.fullmatch(r'hd[2-9]\d*', tag):
            if self.heading is not None or self.rows is not None:
                raise ValueError('標題邊界異常')
            self.heading = tag
            self.append('\n\n')
        elif tag in ('p', 'div', 'li'):
            self.append('\n')
        elif tag in ('tbody', 'thead', 'tfoot'):
            if self.rows is None or self.row is not None:
                raise ValueError('表格分區邊界異常')
        elif tag in ('page_start', 'page_end', 'content_start', 'content_end', 'table_start', 'table_end',
                     'fulltablestart', 'cannotfindtable', 'table_year', 'table_direction', 'content_direction'):
            pass
        elif tag not in ('b', 'strong', 'i', 'em', 'u', 's', 'sup', 'sub', 'span', 'a'):
            raise ValueError(f'不支援的HTML標記：{tag}，未默默刪除')

    def handle_endtag(self, tag):
        if tag in ('td', 'th'):
            if self.cell is None or tag != self.cell_tag:
                raise ValueError('儲存格結束標記不匹配')
            self.row.append((_cell_text(self.cell), *self.spans))
            self.cell = self.cell_tag = self.spans = None
        elif tag == 'tr':
            if self.row is None or self.cell is not None:
                raise ValueError('tr未完整結束')
            self.rows.append(self.row)
            self.row = None
        elif tag == 'table':
            if self.rows is None or self.row is not None or self.cell is not None:
                raise ValueError('table未完整結束')
            grid = expand_rows(self.rows)
            self.tables.append(grid)
            self.parts.append(pipe_table(grid) + '\n\n')
            self.rows = None
        elif re.fullmatch(r'hd[2-9]\d*', tag):
            if self.heading != tag:
                raise ValueError('標題結束標記不匹配')
            self.heading = None
            self.append('\n\n')
        elif tag in ('p', 'div', 'li'):
            self.append('\n')
        elif tag not in ('tbody', 'thead', 'tfoot', 'b', 'strong', 'i', 'em', 'u', 's',
                         'sup', 'sub', 'span', 'a', 'page_start', 'page_end', 'content_start',
                         'content_end', 'table_start', 'table_end', 'fulltablestart', 'cannotfindtable',
                         'table_year', 'table_direction', 'content_direction'):
            raise ValueError(f'不支援的結束標記：{tag}')

    def handle_data(self, data):
        self.append(data)

    def handle_comment(self, data):
        # Page 與控制註解不作 embedding 文字；原文仍完整保存。
        pass

    def finish(self):
        self.close()
        if self.rows is not None or self.row is not None or self.cell is not None or self.heading:
            raise ValueError('HTML表格／標題未閉合')
        return re.sub(r'\n{3,}', '\n\n', ''.join(self.parts)).strip()


def convert_content(content):
    parser = ContentParser()
    parser.feed(content)
    return parser.finish(), parser.tables
