"""EXPERIMENT_ONLY：輸出用標籤與全文；不改送給重排序的text，不查向量庫。"""
import copy
import hashlib
import json
import re
from Code.functions.content_context import context_prefix


class EvidenceReportContext:
    def __init__(self, settings):
        self.root = settings.input_dir.resolve()
        self.paths = None
        self.cache = {}

    def node(self, evidence):
        identity = re.fullmatch(r'(\d{4})Q[1-4]_(\d+)_Financial_Report', evidence['doc_id'])
        digest = evidence.get('input_sha256')
        if identity is None or not isinstance(digest, str) or not re.fullmatch(r'[a-f0-9]{64}', digest):
            return None
        key = (evidence['doc_id'], digest)
        if key not in self.cache:
            if self.paths is None:
                self.paths = list(self.root.rglob('*.json')) if self.root.is_dir() else []
            self.cache[key] = {}
            stem = f'{identity[1]}_{identity[2]}_chunk'
            for path in self.paths:
                if (not re.fullmatch(re.escape(stem)+r'(?:_\d+)?(?:_text-(?:body|description|full)_table-(?:body|description|full))?\.json', path.name)
                        or path.is_symlink() or not path.resolve().is_relative_to(self.root)):
                    continue
                raw = path.read_bytes()
                if hashlib.sha256(raw).hexdigest() != digest:
                    continue
                doc = json.loads(raw.decode('utf-8'))
                if doc.get('doc_id') != evidence['doc_id']:
                    continue
                self.cache[key] = {c['chunk_id']: c for c in doc['chunks'] + doc.get('parents', [])}
                break
        return self.cache[key].get(evidence['chunk_id'])

    def enrich(self, evidence, fallback=None):
        result = copy.deepcopy(evidence)
        node = self.node(evidence)
        identity = re.fullmatch(r'\d{4}Q[1-4]_(\d+)_Financial_Report', evidence['doc_id'])
        stock = identity[1] if identity else None
        if node is not None:
            # 僅採已通過檔案SHA256匹配的既有chunk欄位；不重判年度或說明。
            header = context_prefix(node, include_identity=True)
            prefix = node.get('content_prefix', '')
            text = evidence['text']
            body = text[len(prefix):].lstrip('\n') if prefix and text.startswith(prefix) else text
            description = header.partition('說明：')[2].strip() if '說明：' in header else ''
            metadata = {'years': node['years'], 'stock_code': stock,
                'main_section': node['main_section'], 'sub_section': node['sub_section'],
                'note_title': node['note_title'], 'description': description,
                'content_type': node['content_type'], 'node_type': node.get('node_type'),
                'parent_relation': evidence.get('parent_relation'),
                'table_context': node.get('table_context', ''), 'directions': node.get('directions', []),
                'source_chunk_json_sha256': evidence['input_sha256'], 'status': 'verified_source_chunk'}
            report_text = header.rstrip() + '\n\n' + body
        else:
            # 原始chunk已移除時仍可重排報告，但輸出缺欄位需明示，不能猜補大標。
            meta = fallback or {}
            metadata = {'years': meta.get('years', []), 'stock_code': stock,
                'main_section': None, 'sub_section': meta.get('sub_section'),
                'note_title': meta.get('note_title'), 'description': None,
                'status': 'source_chunk_unavailable',
                'warning': '無法找到SHA256相符的來源chunk；缺少欄位未猜補，原候選全文保留'}
            header = '年度：' + ('、'.join(map(str, metadata['years'])) or '未取得')
            header += '｜股票代號：' + (stock or '未取得') + '｜Main_Section：未取得'
            report_text = header + '\n\n' + evidence['text']
        result['report_metadata'] = metadata
        result['report_text'] = report_text
        return result
