"""模擬模型介面，確認超限時不讓encode默默截斷；不下載模型。"""
import unittest
from unittest.mock import Mock
from Code_2.functions.embedding.providers import BgeProvider, validate_vectors


class ProviderTests(unittest.TestCase):
    def provider(self):
        model = Mock()
        model.max_seq_length = 4
        model.get_embedding_dimension.return_value = 2
        model.tokenizer.return_value = {'input_ids': [[0, 1, 2]]}
        model.encode.return_value.tolist.return_value = [[0.6, 0.8]]
        return BgeProvider(model_name='fake-test-only', cache_dir='unused', revision=None, model=model)

    def test_cpu_adapter_contract(self):
        provider = self.provider()
        self.assertEqual(provider.embed(['財報'], batch_size=1), [[0.6, 0.8]])
        self.assertFalse(provider.model.tokenizer.call_args.kwargs['truncation'])
        self.assertTrue(provider.model.tokenizer.call_args.kwargs['add_special_tokens'])
        self.assertTrue(provider.model.encode.call_args.kwargs['normalize_embeddings'])

    def test_over_limit_does_not_encode(self):
        provider = self.provider()
        provider.model.tokenizer.return_value = {'input_ids': [[0, 1, 2, 3, 4]]}
        with self.assertRaises(ValueError):
            provider.embed(['長表格'], batch_size=1)
        provider.model.encode.assert_not_called()

    def test_bad_vectors_rejected(self):
        for vectors in ([], [[1]], [[True, 1]], [[0, 0]], [[float('nan'), 1]], [[float('inf'), 1]]):
            with self.subTest(vectors=vectors), self.assertRaises(ValueError):
                validate_vectors(vectors, expected_count=1, dimension=2)

    def test_invalid_input_or_batch_rejected(self):
        provider = self.provider()
        for texts, size in (([], 1), ([''], 1), (['財報'], 0), (['財報'], True)):
            with self.subTest(texts=texts, size=size), self.assertRaises(ValueError):
                provider.embed(texts, batch_size=size)


if __name__ == '__main__':
    unittest.main()
