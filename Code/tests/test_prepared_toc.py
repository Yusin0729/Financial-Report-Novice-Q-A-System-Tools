"""既有目錄PDF的本機驗證，不呼叫Gemini。"""
import hashlib
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from functions.ingestion.toc_pdf import load_prepared_toc_pdf
from test_toc import make_pdf


class PreparedTocTests(unittest.TestCase):
    def test_prepared_pdf_requires_matching_hash_two_pages_and_source_mapping(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / '2025_2330_table.pdf'
            data = make_pdf(2)
            path.write_bytes(data)
            info = dict(source_sha256='a' * 64, extracted_sha256=hashlib.sha256(data).hexdigest(),
                        source_page_count=85, source_pages=(2, 3))
            result = load_prepared_toc_pdf(path, **info)
            self.assertEqual(result.data, data)
            self.assertEqual(result.source_pages, (2, 3))
            for changes in ({'source_pages': (1, 2)}, {'source_sha256': ''},
                            {'source_page_count': 2}, {'extracted_sha256': 'b' * 64}):
                with self.subTest(changes=changes), self.assertRaises(ValueError):
                    load_prepared_toc_pdf(path, **{**info, **changes})
            path.write_bytes(make_pdf(3))
            info['extracted_sha256'] = hashlib.sha256(path.read_bytes()).hexdigest()
            with self.assertRaisesRegex(ValueError, '恰有兩頁'):
                load_prepared_toc_pdf(path, **info)


if __name__ == '__main__':
    unittest.main()
