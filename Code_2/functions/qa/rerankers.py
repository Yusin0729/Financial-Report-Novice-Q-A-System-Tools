"""Reranker selection is independent of embedding/index and API key management."""
from dataclasses import replace
from Code_2.config.qa import QASettings

LOCAL_BGE_PROFILE = 'local_bge_reranker_v2_m3'


def local_profiles():
    return [{'id': LOCAL_BGE_PROFILE, 'purpose': 'rerank', 'provider': 'bge',
             'name': 'BGE本機重排序（不需金鑰）', 'model': QASettings().bge_rerank_model,
             'configured': True}]


def resolve_rerank_profile(root, identity):
    if identity == LOCAL_BGE_PROFILE:
        return local_profiles()[0], None
    from Code.functions.embedding.api_settings import resolve_profile
    return resolve_profile(root, identity, 'rerank')


def create_reranker(settings, qa):
    profile, key = resolve_rerank_profile(settings.project_root, qa.rerank_profile)
    current = replace(qa, rerank_model=profile['model'], rerank_provider=profile['provider'])
    if profile['provider'] == 'bge':
        from Code_2.functions.qa.bge_reranker import BgeReranker
        return BgeReranker(settings, current), current
    if profile['provider'] != 'voyage':
        raise ValueError('重排序只支援BGE本機與Voyage')
    import voyageai
    from Code_2.functions.qa.services import VoyageReranker
    client = voyageai.Client(api_key=key, timeout=current.timeout, max_retries=0)
    return VoyageReranker(client, current), current
