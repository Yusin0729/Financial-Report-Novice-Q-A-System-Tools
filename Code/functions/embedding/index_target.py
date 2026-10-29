"""使用者命名的實驗索引：名稱供顯示，隨機身分隔離集合；不改既有集合。"""
import json
import re
import uuid


def validate_choice(mode=None, name=None, collection=None):
    if mode is None:
        if name is not None or collection is not None:
            raise ValueError('請明確選新建索引或加入既有索引')
        return
    if mode in ('new', 'batch'):
        if not isinstance(name, str) or not name.strip() or len(name.strip()) > 80 or any(ord(c) < 32 for c in name):
            raise ValueError('索引名稱須為1～80字，且不可含控制字元')
        if collection is not None:
            raise ValueError('新建索引不可同時指定既有集合')
    elif mode == 'existing':
        if name is not None or not isinstance(collection, str) or not re.fullmatch(r'financial_[a-f0-9]{24}', collection):
            raise ValueError('請選擇有效的既有索引')
    else:
        raise ValueError('索引操作須為new／batch／existing')


def resolve_target(settings, backend, *, mode=None, name=None, collection=None):
    validate_choice(mode, name, collection)
    if mode is None:
        return None  # 相容舊CLI與既有自動分組，不重命名或遷移。
    if mode == 'new':
        return {'experiment': {'id': uuid.uuid4().hex, 'name': name.strip()}}
    if mode == 'batch':
        raise ValueError('批次索引須由建庫分組入口建立')
    from Code.functions.embedding.catalog import list_indexes, select_index
    item = select_index(list_indexes(settings, backend), backend, collection)
    if item.get('status') == 'collection_deletion_pending':
        raise ValueError('索引正在移除，不能加入資料')
    return {'signature': item['signature']}


def bind_signature(signature, target):
    if target is None:
        return signature
    expected = target.get('signature')
    if expected is not None:
        actual = dict(signature)
        if 'experiment' in expected:
            actual['experiment'] = expected['experiment']
        if json.dumps(actual, sort_keys=True, ensure_ascii=False) != json.dumps(expected, sort_keys=True, ensure_ascii=False):
            raise ValueError('所選索引的模型、欄位、切法或處理版本不同；請新建索引')
        return actual
    experiment = target.get('experiment')
    if (not isinstance(experiment, dict) or set(experiment) != {'id','name'}
            or not isinstance(experiment['id'], str) or not re.fullmatch(r'[a-f0-9]{32}', experiment['id'])):
        raise ValueError('新索引身分無效')
    validate_choice('new', experiment['name'])
    return {**signature, 'experiment': dict(experiment)}


def plan_key(doc):
    """一個自訂索引不能跨切法／字數／規則；在模型建立前檢查。"""
    return json.dumps({'preparation_rule':doc['rule_version'],
                      'embedding_context_modes':doc.get('embedding_context_modes'),
                      'chunking':doc.get('chunking'),
                      'source_chunk_rule':doc.get('source_rule_version')},sort_keys=True)
