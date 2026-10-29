"""已確認的階層核心合成測試；不代表Markdown解析或標籤功能已完成。"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from functions.markdown_processing.heading_hierarchy import HeadingHierarchy
from functions.markdown_processing.classify_tag_heading import classify_tag_heading


class HierarchyTests(unittest.TestCase):
    def test_only_two_hashes_and_unnumbered_title_does_not_invent_type(self):
        for text in ['# (1) 待處理：', '### 一、公司沿革', '一、公司沿革', '    ## 一、程式碼']:
            self.assertIsNone(classify_tag_heading(text))
        self.assertEqual(classify_tag_heading('## 重大會計判斷').role, 'untracked')

    def test_main_section_spacing_and_dynamic_markers(self):
        for text in ['## 合併財務報告附註', '## 九、合併財務報告附註']:
            self.assertEqual(classify_tag_heading(text).role, 'main')
        for text in ['## 一、公司沿革', '## 四 、重大會計政策', '## 三 十 、現金流量資訊']:
            self.assertEqual(classify_tag_heading(text).role, 'section')
        for text, kind in [('## (一) 基礎', 'parenthesized_chinese'),
                           ('## 1. 事項', 'number_dot'),
                           ('## - （1）衡量', 'parenthesized_number')]:
            self.assertEqual(classify_tag_heading(text).marker_type, kind)

    def tracker(self):
        tracker = HeadingHierarchy()
        tracker.start_section('四、重大會計政策')
        return tracker

    def test_first_seen_types_and_return_to_known_level(self):
        tracker = self.tracker()
        tracker.add_dynamic('(一) 金融工具', 'parenthesized_chinese')
        first = tracker.add_dynamic('1. 金融資產', 'number_dot')
        self.assertEqual([x.level for x in first], [1, 2, 3])
        tracker.add_dynamic('2. 金融負債', 'number_dot')
        self.assertEqual(tracker.path[-1].title, '2. 金融負債')
        tracker.add_dynamic('(二) 存貨', 'parenthesized_chinese')
        self.assertEqual([x.level for x in tracker.path], [1, 2])
        tracker.add_dynamic('1. 成本', 'number_dot')
        self.assertEqual(tracker.path[-1].level, 3)
        self.assertEqual(first[-1].title, '1. 金融資產')

    def test_section_reset_changes_first_seen_order(self):
        tracker = self.tracker()
        tracker.add_dynamic('(一) 金融工具', 'parenthesized_chinese')
        tracker.add_dynamic('1. 金融資產', 'number_dot')
        tracker.start_section('五、重大會計判斷')
        tracker.add_dynamic('1. 判斷事項', 'number_dot')
        tracker.add_dynamic('(1) 衡量方式', 'parenthesized_number')
        self.assertEqual([x.level for x in tracker.path], [1, 2, 3])
        self.assertEqual(tracker.path[1].marker_type, 'number_dot')
        self.assertNotIn('金融工具', ' '.join(x.title for x in tracker.path))

    def test_section_reset_and_no_fabricated_parent(self):
        tracker = self.tracker()
        tracker.add_dynamic('(一) 金融工具', 'parenthesized_chinese')
        tracker.start_section('二、其他章節')
        self.assertEqual(len(tracker.path), 1)
        fresh = HeadingHierarchy()
        self.assertEqual(fresh.path, ())
        with self.assertRaises(ValueError):
            fresh.add_dynamic('1. 事項', 'number_dot')

    def test_reject_unknown_type_and_empty_title_without_mutation(self):
        tracker = self.tracker()
        before = tracker.path
        for title, kind in [('A. 事項', 'uppercase'), (' ', 'number_dot')]:
            with self.assertRaises(ValueError):
                tracker.add_dynamic(title, kind)
        self.assertEqual(tracker.path, before)

    def test_new_type_after_return_does_not_invent_missing_parent(self):
        tracker = self.tracker()
        tracker.add_dynamic('(一) 方法', 'parenthesized_chinese')
        tracker.add_dynamic('1. 事項', 'number_dot')
        tracker.add_dynamic('(二) 方法', 'parenthesized_chinese')
        tracker.add_dynamic('(1) 內容', 'parenthesized_number')
        # 類型對應保留，第三種仍為4；不補造已清除的第3層標題。
        self.assertEqual([x.level for x in tracker.path], [1, 2, 4])


if __name__ == '__main__':
    unittest.main()
