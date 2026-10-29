"""以已確認的選頁範圍輸出原PDF頁序與章節邊界。"""
from functions.markdown_processing.page_markers import format_page_marker


def assemble_selected_pages(pages, identity, audit_start, notes_start):
    marked = []
    for page in pages:
        marker = format_page_marker(page.pdf_page, identity) + '\n'
        if page.pdf_page == audit_start:
            marker = '<會計師查核報告>\n' + marker
        if page.pdf_page == notes_start:
            marker = '<note>\n<合併財務報告附註>\n' + marker
        if page.cross_page_item_refs:
            marker += '<!-- CROSS_PAGE_ITEMS: ' + ', '.join(page.cross_page_item_refs) + ' -->\n'
        if page.status == 'no_text_extracted':
            marker += '<!-- NO_TEXT_EXTRACTED: 請核對原 PDF，本頁不視為文字辨識成功 -->\n'
        marked.append(marker + '\n' + page.markdown + '\n')
    return '\n'.join(marked)
