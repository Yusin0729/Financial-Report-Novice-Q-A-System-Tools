"""年度優先序、前置標籤邊界與說明來源；不使用模型或既有Output。"""
import unittest
import re
from test_chunks import convert, tagged, page
from test_table_parents import table
from functions.chunking.table_metadata import explicit_years,table_years


def tagged_with_descriptions(raw):
    # tag_comments只接收processed；先保留測試指定的新標籤，待第三階段結束後插回。
    labels = []
    def reserve(match):
        labels.append(match[0])
        return f'DESCRIPTIONFIXTURE{len(labels)-1}'
    raw = re.sub(r'<(table_year|table_direction|content_direction)>.*?</\1>', reserve, raw)
    source = tagged(raw)
    for index, label in enumerate(labels):
        source = source.replace(f'DESCRIPTIONFIXTURE{index}', label)
    return source


class TablePeriodTests(unittest.TestCase):
    def parent(self, prefix, header='金額'):
        raw = page(15) + '## 一、公司沿革\n' + prefix + table(header)
        return convert(tagged_with_descriptions(raw)).document['parents'][-1]

    def test_extract_years_anywhere_and_convert_to_gregorian(self):
        examples = {
            '所得稅於民國一一四年度及一一三年度之組成如下：': [2024, 2025],
            '一百一十四年度': [2025],
            '１１２ 年 １２ 月 ３１ 日': [2023],
            '114.12.31及113.12.31': [2024, 2025],
            '西元2024及2025年度之金額': [2024, 2025],
            '金額4.375%、$2,025、123': [],
        }
        for value, years in examples.items():
            with self.subTest(value=value):
                self.assertEqual(explicit_years(value), years)

    def test_minimum_roc_year_100_and_allowed_year_formats(self):
        for value,want in [('113年度',[2024]),('113年12月31日',[2024]),('112年',[2023]),
                           ('100年度',[2011]),('一百年',[2011]),('90年',[]),('99年度',[]),
                           ('民國九十年',[]),('短於1年',[]),('1至3年',[]),('3至5年',[]),
                           ('5年以上合計',[]),('2024年',[2024]),('2024',[2024])]:
            with self.subTest(value=value):self.assertEqual(explicit_years(value),want)
    def test_maturity_headers_fall_back_to_explicit_table_year(self):
        html='<table><tr><th>短於1年</th><th>1至3年</th><th>3至5年</th><th>5年以上</th></tr><tr><td>負債</td><td>90年取得</td></tr></table>'
        years,sources=table_years(html,[('113年12月31日','preceding_table_year')],2025)
        self.assertEqual(years,[2024])
        self.assertEqual(sources[0]['source'],'preceding_table_year')
        self.assertEqual(table_years('<table><tr><th>90年</th></tr></table>',[],2025)[0],[2025])
        self.assertEqual(table_years('<table><tr><th>112年</th><th>113年度</th></tr></table>',
            [('110年度','preceding_table_year')],2025)[0],[2023,2024])
    def test_table_years_win_over_preceding_years(self):
        item = self.parent('## 民國一一二年度\n', '114及113年度')
        self.assertEqual(item['years'], [2024, 2025])
        self.assertTrue(all(s['source'].startswith('table_') for s in item['year_sources']))

    def test_three_description_tags_supply_years_inside_explanations(self):
        for tag in ('table_year', 'table_direction', 'content_direction'):
            with self.subTest(tag=tag):
                prefix = f'<{tag}>說明：民國一一二年度及一一一年度資料如下：</{tag}>\n'
                item = self.parent(prefix)
                self.assertEqual(item['years'], [2022, 2023])
                self.assertEqual(item['year_sources'][0]['source'], 'preceding_' + tag)

    def test_context_prefers_nearest_allowed_tag_and_skips_table_year(self):
        item = self.parent('## (一) 金融工具\n'
                           '<content_direction>所得稅組成：</content_direction>\n'
                           '<table_year>112年度</table_year>\n')
        self.assertEqual(item['table_context'], '所得稅組成：')
        self.assertEqual(item['years'], [2023])

    def test_year_search_stops_at_prose_heading_and_previous_table(self):
        for barrier in ('說明正文\n', '## (一) 金融工具\n', table('金額')):
            with self.subTest(barrier=barrier):
                item = self.parent('<table_year>112年度</table_year>\n' + barrier)
                self.assertEqual(item['years'], [2025])
                self.assertEqual(item['year_sources'][0]['source'], 'document_year_fallback')

    def test_page_and_blank_lines_do_not_stop_year_search(self):
        item = self.parent('<table_year>112年度</table_year>\n\n' + page(16))
        self.assertEqual(item['years'], [2023])

    def test_code_literal_tag_does_not_supply_year_or_context(self):
        item = self.parent('```html\n<table_year>112年度</table_year>\n```\n')
        self.assertEqual(item['years'], [2025])
        self.assertEqual(item['table_context'], '一、公司沿革')

    def test_no_borrowing_years_or_context_from_previous_section(self):
        raw = (page(15) + '<會計師查核報告>\n'
               '<content_direction>112年度報告：</content_direction>\n'
               '<note>\n' + table('金額'))
        item = convert(tagged_with_descriptions(raw)).document['parents'][0]
        self.assertEqual(item['years'], [2025])
        self.assertEqual(item['table_context'], '')


if __name__ == '__main__':
    unittest.main()
