"""第二階段分類及第三階段責任界線；不載入模型。"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from functions.markdown_processing.mark_headings import mark_missing_headings
from functions.markdown_processing.comment_tagging import tag_comments
from schemas import TaggingMetadata


class ProcessedHeadingCleanupTests(unittest.TestCase):
    def test_spaced_appendix_and_hash_without_separator(self):
        for title in ('附 表 一：'+'長'*30, '附表 一 說明', '附\t表\u3000二十 說明'):
            for prefix in ('', '##', '### '):
                source = prefix+title+'\r\n'
                result = mark_missing_headings(source).markdown
                self.assertEqual(result, '#### '+title+'\r\n')
                self.assertEqual(mark_missing_headings(result).markdown, result)
        for source, expected in [('##一、公司沿革', '##一、公司沿革'),
                                 ('##普通正文', '普通正文'),
                                 ('##4.375%', '4.375%'),
                                 ('####民國一一四年度', '## 民國一一四年度'),
                                 ('##\u3000普通正文', '普通正文')]:
            self.assertEqual(mark_missing_headings(source).markdown, expected)
        protected = ('<table>\n##普通正文\n附 表 一\n</table>\n'
                     '    附 表 一\n\t##普通正文\n<note>\n'
                     '<!-- Page: 2330_2025_P15 -->\n')
        self.assertEqual(mark_missing_headings(protected).markdown, protected)
        self.assertEqual(mark_missing_headings('詳附 表 一').markdown, '詳附 表 一')
        self.assertEqual(mark_missing_headings('附 表 一\n說明：\n').markdown,
                         '#### 附 表 一\n## 說明：\n')

    def test_note_prefix_ignores_spaces_preserves_long_content_and_protection(self):
        for title in ('註一、說明', '註 二：'+'長'*30, '註\t二\u3000十 方法。'):
            for prefix in ('', '# ', '##', '#### '):
                result = mark_missing_headings(prefix+title+'\n').markdown
                self.assertEqual(result, '### '+title+'\n')
                self.assertEqual(mark_missing_headings(result).markdown, result)
        for text in ('詳註一、內容', '註1：內容', '    註 一：內容',
                     '<table>\n註 一：內容\n</table>',
                     '<cannotfindtable>\n註 二\n</cannotfindtable>'):
            self.assertEqual(mark_missing_headings(text).markdown, text)
        self.assertEqual(mark_missing_headings('前文\n註 一：\n').markdown, '前文\n### 註 一：\n')

    def test_standalone_chinese_calendar_date_is_year_heading(self):
        for date in ('112 年 12 月 31 日', '民國112年12月31日', '2023年12月31日',
                     '民國一一二年12月31日'):
            for prefix in ('', '## ', '#### '):
                text = prefix + date + '\r\n'
                result = mark_missing_headings(text).markdown
                self.assertEqual(result, '## ' + date + '\r\n')
                self.assertEqual(mark_missing_headings(result).markdown, result)
        for text in ('截至112年12月31日', '112 年 12 月 31 日之餘額', '112.12.31'):
            self.assertEqual(mark_missing_headings(text).markdown, text)
        for protected in ('<table>\n112 年 12 月 31 日\n</table>\n',
                          '<cannotfindtable>\n112 年 12 月 31 日\n</cannotfindtable>\n'):
            self.assertEqual(mark_missing_headings(protected).markdown, protected)
        self.assertEqual(mark_missing_headings('112 年 12 月 31 日\n說明如下：\n').markdown,
                         '## 112 年 12 月 31 日\n## 說明如下：\n')

    def test_classification_preserves_content_and_numbered_rules(self):
        source = ('## 普通正文\r\n## 民國一一四年度\r\n2025年度\n'
                  '## 一 、 公司沿革\n## A. 尚未啟用\n'
                  '附表一：' + '長'*30 + '\n## 附表二：其他\n'
                  'A. 不補英文\n1. 方法\n(1) 說明。\n')
        result = mark_missing_headings(source)
        self.assertEqual(result.markdown,
                         '普通正文\r\n## 民國一一四年度\r\n## 2025年度\n'
                         '## 一 、 公司沿革\n## A. 尚未啟用\n#### 附表一：' + '長'*30 +
                         '\n#### 附表二：其他\n## A. 不補英文\n## 1. 方法\n(1) 說明。\n')
        self.assertEqual(mark_missing_headings(result.markdown).markdown, result.markdown)

    def test_protected_and_year_sentences_unchanged(self):
        text = ('<table>\n## 普通\n附表一\n民國一一四年度\n</table>\n'
                '```\n## 普通\n```\n<!--\n## 普通\n-->\n'
                '民國一一四年度及一一三年度，所得稅主要組成如下：\n')
        self.assertEqual(mark_missing_headings(text).markdown,
                         text.replace('民國一一四年度及一一三年度，所得稅主要組成如下：',
                                      '## 民國一一四年度及一一三年度，所得稅主要組成如下：'))

    def test_tagging_preserves_prepared_appendix_and_year_without_hd(self):
        raw = '<!-- Page: 2330_2025_P15 -->\n## 一、公司沿革\n附表一：說明\n## 民國一一四年度\n'
        processed = mark_missing_headings(raw).markdown
        tagged = tag_comments(processed, None, TaggingMetadata(report_year='2025', stock_code='2330')).markdown
        self.assertIn('#### 附表一：說明', tagged)
        self.assertIn('<table_year>民國一一四年度</table_year>', tagged)
        self.assertNotIn('<hd4>民國', tagged)
        legacy = tag_comments(raw, None, TaggingMetadata(report_year='2025', stock_code='2330')).markdown
        self.assertNotIn('# 附表一：說明', legacy)


if __name__ == '__main__':
    unittest.main()
