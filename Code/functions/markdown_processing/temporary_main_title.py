"""TEMPORARY_FALLBACK：無有效目錄時，以公司沿革所在整頁至EOF作大標範圍。

只定位正文恰好##的公司沿革標題；不改寫目錄JSON、不讀寫Output。
日後替換時調整comment_tagging的呼叫及config/markdown_tagging的設定。
"""
import re
from config.markdown_tagging import TEMPORARY_MAIN_FALLBACK_VERSION


def locate_company_history(lines, protected, pages):
    pattern = re.compile(r'公司沿革')
    current_page = None
    page_starts = dict(pages)
    for index, line in enumerate(lines):
        if index in page_starts:
            current_page = page_starts[index]
        if index in protected or not re.match(r'^\s*##(?!#)\s+', line):
            continue
        title = re.sub(r'^\s*##\s+', '', line).strip()
        title = re.sub(r'^-\s+', '', title)
        if current_page is not None and pattern.search(re.sub(r'\s+', '', title)):
            return {'status': 'temporary_main_title_fallback',
                    'version': TEMPORARY_MAIN_FALLBACK_VERSION,
                    'start_page': current_page, 'end_page': pages[-1][1],
                    'source_line': index + 1, 'title': title}
    raise ValueError('暫時備援找不到有可靠頁序的正文##公司沿革標題，待確認；未猜測起點')
