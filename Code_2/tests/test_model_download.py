"""分段下載的恢復與SHA保護；全部網路回覆為模擬，不下載模型。"""
import hashlib
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch
from Code_2.config.embedding import Settings
from Code_2.functions.embedding.model_download import download


class Response:
    def __init__(self, data, start, end, size, status=206):
        self.data, self.status = data, status
        self.headers = {'Content-Range': f'bytes {start}-{end}/{size}'}

    def read(self, count):
        return self.data[:count]

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass


class DownloadTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.settings = replace(Settings(project_root=Path(self.tmp.name)), bge_revision='fake-revision',
                                hf_http_chunk_bytes=2, hf_http_workers=2)
        self.root = self.settings.model_cache / 'models--BAAI--bge-m3/snapshots/fake-revision'
        self.root.mkdir(parents=True)
        self.data = b'abcdef'
        self.sha = hashlib.sha256(self.data).hexdigest()
        self.starts = []

    def metadata(self, *args):
        if 'api/models/' in args[0]:
            return {'siblings': [{'rfilename': 'pytorch_model.bin', 'size': len(self.data), 'lfs': {'sha256': self.sha}}]}
        return {'pooling_mode_cls_token': True}

    def network(self, request, **kwargs):
        span = request.headers['Range'].removeprefix('bytes=')
        start, end = map(int, span.split('-'))
        self.starts.append(start)
        return Response(self.data[start:end + 1], start, end, len(self.data))

    def run_download(self, side_effect=None):
        with patch('Code_2.functions.embedding.model_download.get_json', side_effect=self.metadata), \
                patch('Code_2.functions.embedding.model_download.urllib.request.urlopen', side_effect=side_effect or self.network):
            download(self.settings)

    def test_resume_verified_then_rename(self):
        (self.root / 'pytorch_model.bin.http.part').write_bytes(b'ab')
        self.run_download()
        self.assertEqual((self.root / 'pytorch_model.bin').read_bytes(), self.data)
        self.assertEqual(sorted(self.starts), [2, 4])
        self.assertFalse((self.root / 'pytorch_model.bin.http.part').exists())

    def test_wrong_sha_never_becomes_model(self):
        self.sha = '0' * 64
        with self.assertRaisesRegex(ValueError, 'SHA不符'):
            self.run_download()
        self.assertFalse((self.root / 'pytorch_model.bin').exists())
        self.assertEqual((self.root / 'pytorch_model.bin.http.part').read_bytes(), self.data)

    def test_wrong_range_never_appended(self):
        with self.assertRaisesRegex(ValueError, '分段範圍'):
            self.run_download(lambda *args, **kwargs: Response(b'ab', 0, 1, 6, status=200))
        self.assertFalse((self.root / 'pytorch_model.bin').exists())
        self.assertEqual((self.root / 'pytorch_model.bin.http.part').stat().st_size, 0)

    def test_bad_existing_model_not_overwritten(self):
        (self.root / 'pytorch_model.bin').write_bytes(b'wrong')
        with self.assertRaisesRegex(ValueError, '既有權重SHA不符'):
            self.run_download()
        self.assertEqual((self.root / 'pytorch_model.bin').read_bytes(), b'wrong')


if __name__ == '__main__':
    unittest.main()
