"""本機目錄選頁：核對目錄續頁與查核／附註的原 PDF 頁序。"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from functions.ingestion.page_selection import select_from_toc, find_notes_in_body


def table(rows):
    return '<table>' + ''.join('<tr>' + ''.join(f'<td>{cell}</td>' for cell in row) + '</tr>'
                            for row in rows) + '</table>'


class LocalPageSelectionTests(unittest.TestCase):
    def test_nfkc_normalizes_toc_keywords_and_fullwidth_page_numbers(self):
        second = '⽬ 錄' + table([('會計師查核報告', '４－７'),
                                   ('合併資產負債表', '８'), ('公司沿⾰', '１４')])
        self.assertEqual(select_from_toc(second, None, 103)['notes_start'], 14)
        self.assertIn('公司沿⾰', second)

    def test_body_company_history_normalized_and_stops_early(self):
        calls = []
        def read(page):
            calls.append(page)
            return '一、公司沿⾰與業務範圍' if page == 14 else '一般內容'
        self.assertEqual(find_notes_in_body(read, 4, 103, audit_end=7),
                         (14, 'company_history_fallback'))
        self.assertEqual(calls, list(range(8, 15)))

    def test_independent_notes_header_accepts_company_prefix_and_rejects_references(self):
        cases = ('## 合併財務報告附註',
                 '聯華電子股份有限公司及子公司合併財務報告附註(續) (金額除另予註明外，均以新臺幣千元為單位)',
                 '**合併財務報表附註**')
        for header in cases:
            pages = {4: '請參閱合併財務報告附註', 5: '(請參閱合併財務報表附註)',
                     6: '合併財務報告附註，包括重大會計政策，業經查核。', 14: header}
            self.assertEqual(find_notes_in_body(lambda p: pages.get(p, ''), 4, 103),
                             (14, 'notes_heading_fallback'))

    def test_missing_title_keeps_unknown_and_skips_known_audit_pages(self):
        pages = {4: '合併財務報告附註', 8: '詳見合併財務報告附註'}
        self.assertEqual(find_notes_in_body(lambda p: pages.get(p, ''), 4, 10, audit_end=7),
                         (None, None))

    def test_headers_in_toc_audit_and_tables_do_not_trigger_notes_fallback(self):
        pages = {4: '## 會計師查核報告\n合併財務報告附註',
                 5: '## 目 錄\n合併財務報告附註',
                 6: '<table>\n合併財務報告附註\n</table>',
                 7: '```\n合併財務報告附註\n```'}
        self.assertEqual(find_notes_in_body(lambda p: pages[p], 4, 7), (None, None))

    def test_one_page_toc_uses_company_history_when_notes_heading_has_no_page(self):
        second = '目 錄' + table([
            ('項目', '頁次'), ('聲明書', '3'), ('會計師查核報告', '4〜7'),
            ('合併資產負債表', '8'), ('合併財務報告附註', ''), ('公司沿革', '15'),
        ])
        third = '關係企業合併財務報告聲明書'
        self.assertEqual(select_from_toc(second, third, 85),
                         {'toc_pages': [2], 'audit_pages': (4, 7), 'notes_start': 15})

    def test_third_page_continuation_without_toc_title(self):
        second = '目錄' + table([
            ('項目', '頁次'), ('聲明書', '4'), ('會計師查核報告書', '5 ~ 8'),
            ('合併資產負債表', '9'), ('合併財務報表附註', '15 ~ 64'),
        ])
        third = table([('項目', '頁次'), ('(九) 重大事項', '53'), ('(十) 其他', '54')])
        self.assertEqual(select_from_toc(second, third, 79)['toc_pages'], [2, 3])

    def test_unreadable_toc_stops_instead_of_inventing_pages(self):
        with self.assertRaisesRegex(ValueError, '第2頁'):
            select_from_toc('聲明書', None, 85)


if __name__ == '__main__':
    unittest.main()
