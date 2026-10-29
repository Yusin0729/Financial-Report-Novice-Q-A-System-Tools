"""共用API設定：JSON只存模型與金鑰參照；秘密只存根目錄.env。

新增／刪除只影響本機設定，不探測服務、不呼叫模型，不自動修改任何索引。
"""
import json
import os
import re
import sqlite3
import tempfile
import uuid
from contextlib import contextmanager
from pathlib import Path
from Code.functions.embedding.keys import service_key

PURPOSES = {'embedding': ('voyage',), 'rerank': ('voyage',), 'answer': ('gemini', 'openai')}
MODEL_SUGGESTIONS = {'embedding': {'voyage': ['voyage-finance-2']},
                     'rerank': {'voyage': ['rerank-3-lite']},
                     'answer': {'gemini': ['gemini-3.1-flash-lite'], 'openai': []}}
LEGACY = {'legacy_voyage_embedding': ('embedding', 'voyage', 'voyage-finance-2', 'VOYAGE_API_KEY'),
          'legacy_voyage_rerank': ('rerank', 'voyage', 'rerank-3-lite', 'VOYAGE_API_KEY'),
          'legacy_gemini_answer': ('answer', 'gemini', 'gemini-3.1-flash-lite', 'GEMINI_API_KEY')}


def config_path(root): return Path(root) / 'Code/config/api_profiles.json'


@contextmanager
def locked(root):
    path = config_path(root).with_name('api_settings.lock.sqlite3')
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, timeout=10)
    try:
        conn.execute('BEGIN IMMEDIATE')  # Code與Code_2／不同程序共用寫入鎖。
        yield
    finally:
        conn.rollback()
        conn.close()


def read_config(root):
    path = config_path(root)
    if not path.exists(): return {'version': 1, 'credentials': [], 'profiles': []}
    if path.is_symlink() or path.stat().st_size > 1024*1024:
        raise ValueError('API設定檔路徑或大小異常')
    data = json.loads(path.read_text(encoding='utf-8'))
    if data.get('version') != 1 or not isinstance(data.get('credentials'), list) or not isinstance(data.get('profiles'), list):
        raise ValueError('API設定檔格式錯誤，未覆寫')
    if set(data) not in ({'version','credentials','profiles'}, {'version','credentials','profiles','slots'}):
        raise ValueError('API設定包含未知欄位')
    slots=data.get('slots',{})
    if (not isinstance(slots,dict) or not set(slots).issubset(PURPOSES)
            or any(v is not None and (not isinstance(v,str) or not re.fullmatch(r'[a-f0-9]{32}|legacy_[a-z_]+',v)) for v in slots.values())):
        raise ValueError('簡易API設定格式錯誤')
    ids=set()
    for credential in data['credentials']:
        if not isinstance(credential,dict) or set(credential)!={'id','name','provider','variable'}:
            raise ValueError('金鑰參照格式錯誤')
        if (credential['provider'] not in ('voyage','gemini','openai') or
                not isinstance(credential['id'],str) or credential['id'] in ids or
                not isinstance(credential['name'],str) or not 1<=len(credential['name'])<=100 or
                not isinstance(credential['variable'],str) or not re.fullmatch(r'FINRAG_KEY_[a-f0-9]{32}|VOYAGE_API_KEY|GEMINI_API_KEY|OPENAI_API_KEY',credential['variable'])):
            raise ValueError('金鑰參照內容無效')
        ids.add(credential['id'])
    profile_ids=set()
    for profile in data['profiles']:
        if not isinstance(profile,dict) or set(profile)!={'id','name','purpose','provider','model','credential_id'}:
            raise ValueError('模型設定格式錯誤')
        if (not isinstance(profile['id'],str) or not re.fullmatch(r'[a-f0-9]{32}',profile['id']) or
                profile['id'] in profile_ids or profile['credential_id'] not in ids or
                profile['purpose'] not in PURPOSES or profile['provider'] not in PURPOSES[profile['purpose']] or
                not isinstance(profile['name'],str) or not 1<=len(profile['name'])<=80 or
                not isinstance(profile['model'],str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.\-]{0,127}',profile['model'])):
            raise ValueError('模型設定內容無效')
        profile_ids.add(profile['id'])
    return data


def atomic_write(path, raw):
    path = Path(path)
    if path.is_symlink(): raise ValueError('設定檔不可為連結')
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix='.'+path.name+'.', dir=path.parent)
    try:
        with os.fdopen(fd, 'wb') as stream:
            stream.write(raw); stream.flush(); os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if Path(temporary).exists(): Path(temporary).unlink()


def save_config(root, data):
    atomic_write(config_path(root), (json.dumps(data, ensure_ascii=False, indent=2)+'\n').encode('utf-8'))


def change_env(root, variable, value=None):
    """只變更指定變數，其他.env行逐位元保留；不回傳任何檔案內容。"""
    if not re.fullmatch(r'FINRAG_KEY_[a-f0-9]{32}|VOYAGE_API_KEY|GEMINI_API_KEY|OPENAI_API_KEY', variable):
        raise ValueError('不允許修改此環境變數')
    path = Path(root) / '.env'
    if path.is_symlink(): raise ValueError('.env不可為連結')
    raw = path.read_bytes() if path.exists() else b''
    bom = raw.startswith(b'\xef\xbb\xbf')
    text = raw.decode('utf-8-sig')
    lines = text.splitlines(keepends=True)
    pattern = re.compile(r'^\s*(?:export\s+)?'+re.escape(variable)+r'\s*=')
    indexes = [i for i,line in enumerate(lines) if pattern.match(line)]
    if len(indexes)>1: raise ValueError('指定金鑰在.env重複，請先修正重複設定')
    if value is not None:
        if not isinstance(value,str) or not re.fullmatch(r'[A-Za-z0-9_.:/+=\-]{8,4096}',value):
            raise ValueError('API key格式無效；不得含空白、引號或換行')
        line = variable+'='+value
        if indexes:
            old = lines[indexes[0]]
            ending = '\r\n' if old.endswith('\r\n') else '\n' if old.endswith('\n') else ''
            lines[indexes[0]]=line+ending
        else:
            ending = '\r\n' if '\r\n' in text else '\n'
            if lines and not lines[-1].endswith(('\n','\r')): lines[-1]+=ending
            lines.append(line+ending)
    elif indexes:
        del lines[indexes[0]]
    atomic_write(path, (b'\xef\xbb\xbf' if bom else b'')+''.join(lines).encode('utf-8'))


def available_key(root, variable):
    try:
        service_key(root, variable)
        return True
    except ValueError:
        return False


def _public_settings(root, data):
    credentials = [{**c, 'configured': available_key(root,c['variable']),
                    'deletable': not bool(os.environ.get(c['variable']))} for c in data['credentials']]
    profiles = [dict(p) for p in data['profiles']]
    for provider,variable in (('voyage','VOYAGE_API_KEY'),('gemini','GEMINI_API_KEY'),('openai','OPENAI_API_KEY')):
        if available_key(root,variable) and not any(c['id']=='legacy_'+provider for c in credentials):
            credentials.append({'id':'legacy_'+provider,'name':provider+'（既有金鑰）','provider':provider,
                                'variable':variable,'configured':True,'deletable':not bool(os.environ.get(variable))})
    for identity,(purpose,provider,model,variable) in LEGACY.items():
        if available_key(root,variable):
            cid='legacy_'+provider
            if not any(c['id']==cid for c in credentials):
                credentials.append({'id':cid,'name':provider+'（既有金鑰）','provider':provider,
                    'variable':variable,'configured':True,'deletable':not bool(os.environ.get(variable))})
            profiles.append({'id':identity,'name':model+'（既有設定）','purpose':purpose,
                             'provider':provider,'model':model,'credential_id':cid})
    valid = {c['id'] for c in credentials if c['configured']}
    for p in profiles: p['configured']=p['credential_id'] in valid
    slots=data.get('slots',{})
    profiles=[p for p in profiles if p['purpose'] not in slots or p['id']==slots[p['purpose']]]
    selected={purpose:next((p for p in profiles if p['purpose']==purpose and p['configured']),None)
              for purpose in PURPOSES}
    return {'credentials':credentials,'profiles':profiles,'slots':selected,'model_suggestions':MODEL_SUGGESTIONS}


def public_settings(root):
    with locked(root):
        return _public_settings(root, read_config(root))


def change_slot(root, data, request):
    """三個用途各一設定；保留其他舊設定，共用金鑰不連帶刪除。"""
    purpose=request.get('purpose')
    if purpose not in PURPOSES:raise ValueError('未知API用途')
    public=_public_settings(root,data)
    current=public['slots'][purpose]
    old_credential=next((c for c in public['credentials'] if current and c['id']==current['credential_id']),None)
    deleting=request['action']=='delete-slot'
    if deleting and not current:raise ValueError('此用途尚未保存金鑰')
    if deleting and not old_credential['deletable']:raise ValueError('金鑰由外部環境提供，請在啟動環境移除')
    provider=request.get('provider')
    model=request.get('model')
    if not deleting:
        if provider not in PURPOSES[purpose]:raise ValueError('用途與服務商不相容')
        if (not isinstance(model,str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.\-]{0,127}',model)
                or (purpose=='embedding' and model!='voyage-finance-2')
                or (purpose=='rerank' and not model.startswith('rerank-'))
                or (provider=='openai' and not model.startswith('gpt-'))
                or (provider=='gemini' and not model.startswith('gemini-'))):
            raise ValueError('請填入符合服務商與用途的模型ID')
        key=request.get('api_key')
        if key is not None and not isinstance(key,str):raise ValueError('API key格式無效')
        if not key and (not current or current['provider']!=provider):raise ValueError('請輸入此服務商的API key')
    env_path=Path(root)/'.env'
    if env_path.is_symlink():raise ValueError('.env不可為連結')
    before=env_path.read_bytes() if env_path.exists() else None
    try:
        slots=data.setdefault('slots',{})
        if current:
            data['profiles']=[p for p in data['profiles'] if p['id']!=current['id']]
        if deleting:
            slots[purpose]=None
        else:
            if key:
                cid=uuid.uuid4().hex
                credential={'id':cid,'name':purpose,'provider':provider,'variable':'FINRAG_KEY_'+cid}
                change_env(root,credential['variable'],key)
                data['credentials'].append(credential)
            else:
                credential=dict(old_credential)
                credential={k:credential[k] for k in ('id','name','provider','variable')}
                if not any(c['id']==credential['id'] for c in data['credentials']):data['credentials'].append(credential)
            pid=current['id'] if current and not current['id'].startswith('legacy_') else uuid.uuid4().hex
            data['profiles'].append({'id':pid,'name':{'embedding':'Voyage Embedding','rerank':'Voyage Rerank','answer':'LLM'}[purpose],
                'purpose':purpose,'provider':provider,'model':model,'credential_id':credential['id']})
            slots[purpose]=pid
        if old_credential:
            used=any(p['credential_id']==old_credential['id'] for p in data['profiles'])
            used=used or any(p['credential_id']==old_credential['id'] for p in _public_settings(root,data)['profiles'])
            if not used and old_credential['deletable']:
                change_env(root,old_credential['variable'])
                data['credentials']=[c for c in data['credentials'] if c['id']!=old_credential['id']]
        save_config(root,data)
    except Exception:
        if before is not None:atomic_write(env_path,before)
        elif env_path.exists():env_path.unlink()
        raise


def resolve_profile(root, identity, purpose):
    public = public_settings(root)
    profile = next((p for p in public['profiles'] if p['id']==identity and p['purpose']==purpose),None)
    if not profile or not profile['configured']: raise ValueError('API設定已刪除或金鑰缺少，請重新選擇')
    credential = next(c for c in public['credentials'] if c['id']==profile['credential_id'])
    return profile, service_key(root,credential['variable'])


def manage(root, request):
    if not isinstance(request,dict): raise ValueError('API設定請求須為物件')
    action=request.get('action')
    if action=='list': return public_settings(root)
    with locked(root):
        data=read_config(root)
        if action in ('save-slot','delete-slot'):
            change_slot(root,data,request)
        elif action=='add':
            purpose,provider,model=request.get('purpose'),request.get('provider'),request.get('model')
            name=request.get('name')
            if purpose not in PURPOSES or provider not in PURPOSES[purpose]: raise ValueError('用途與服務商不相容')
            if not isinstance(name,str) or not name.strip() or len(name)>80: raise ValueError('請輸入80字以內的名稱')
            if not isinstance(model,str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.\-]{0,127}',model): raise ValueError('請指定有效模型ID')
            if (provider=='openai' and not model.startswith('gpt-')) or (provider=='gemini' and not model.startswith('gemini-')) or (purpose=='rerank' and not model.startswith('rerank-')):
                raise ValueError('模型ID與服務商／用途不符；回答只支援Gemini及GPT，重排序只支援Voyage')
            if purpose=='embedding' and model!='voyage-finance-2': raise ValueError('目前API embedding僅支援voyage-finance-2，避免未知維度混入索引')
            credential_id=request.get('credential_id')
            new_credential=None
            if credential_id:
                credential=next((c for c in data['credentials'] if c['id']==credential_id and c['provider']==provider),None)
                # 既有.env金鑰可共用，但不複製秘密。
                if credential is None and credential_id=='legacy_'+provider:
                    variable={'voyage':'VOYAGE_API_KEY','gemini':'GEMINI_API_KEY','openai':'OPENAI_API_KEY'}[provider]
                    if available_key(root,variable):
                        credential={'id':credential_id,'name':provider+'（既有金鑰）','provider':provider,'variable':variable}
                        data['credentials'].append(credential)
                if credential is None or not available_key(root,credential['variable']): raise ValueError('共用金鑰不存在或服務商不符')
                if request.get('api_key'): raise ValueError('共用金鑰時請勿同時輸入新key')
            else:
                cid=uuid.uuid4().hex
                new_credential={'id':cid,'name':name.strip(),'provider':provider,'variable':'FINRAG_KEY_'+cid}
                if not isinstance(request.get('api_key'), str) or not request['api_key']:
                    raise ValueError('請輸入API key或選擇已保存金鑰')
                change_env(root,new_credential['variable'],request.get('api_key'))
                credential_id=cid;data['credentials'].append(new_credential)
            data['profiles'].append({'id':uuid.uuid4().hex,'name':name.strip(),'purpose':purpose,
                                     'provider':provider,'model':model,'credential_id':credential_id})
            try: save_config(root,data)
            except Exception:
                if new_credential: change_env(root,new_credential['variable'])
                raise RuntimeError('API設定未完整保存，未宣稱新增成功') from None
        elif action=='delete-profile':
            identity=request.get('id')
            if identity in LEGACY: raise ValueError('既有預設選項請從下方金鑰清單刪除其金鑰')
            found=[p for p in data['profiles'] if p['id']==identity]
            if not found: raise ValueError('設定已不存在')
            data['profiles']=[p for p in data['profiles'] if p['id']!=identity]
            save_config(root,data)  # 金鑰可能共用，保留供其他設定使用；可另行刪除。
        elif action=='delete-key':
            identity=request.get('id')
            credential=next((c for c in data['credentials'] if c['id']==identity),None)
            if credential is None and identity in ('legacy_voyage','legacy_gemini','legacy_openai'):
                provider=identity[7:]
                credential={'id':identity,'variable':{'voyage':'VOYAGE_API_KEY','gemini':'GEMINI_API_KEY','openai':'OPENAI_API_KEY'}[provider]}
            if credential is None: raise ValueError('金鑰不存在')
            if os.environ.get(credential['variable']): raise ValueError('此金鑰由外部環境變數提供，請在啟動環境移除後重新啟動服務；介面不能撤銷外部環境')
            change_env(root,credential['variable'])
            data['credentials']=[c for c in data['credentials'] if c['id']!=identity]
            data['profiles']=[p for p in data['profiles'] if p['credential_id']!=identity]
            save_config(root,data)
        else: raise ValueError('未知API設定操作')
    return public_settings(root)
