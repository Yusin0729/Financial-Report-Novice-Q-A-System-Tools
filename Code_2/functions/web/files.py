"""Scoped project folder browsing and recoverable, confirmed folder removal."""
import hashlib
import json
import os
import shutil
import uuid
from datetime import datetime, timezone
from pathlib import Path

ROOTS = {'output': ('階段輸出與測報', 'Output'), 'sources': ('財報來源', 'Financial Statements')}
EXTENSIONS = {'.md','.txt','.json','.csv','.log','.pdf','.xlsx','.png','.jpg','.jpeg'}
TEXT = {'.md','.txt','.json','.csv','.log'}
PREVIEW_BYTES = 256 * 1024


def is_link(p):
    try:
        return p.is_symlink() or bool(getattr(p.lstat(), 'st_file_attributes', 0) & 0x400)
    except FileNotFoundError:
        return False


def resolve(settings, area, relative=''):
    if area not in ROOTS or not isinstance(relative, str) or len(relative)>2000:
        raise ValueError('資料夾位置無效')
    parts = relative.replace('\\','/').split('/') if relative else []
    if any(not p or p in ('.','..') or p.startswith('.') or ':' in p for p in parts):
        raise ValueError('不允許這個資料夾位置')
    project = settings.project_root.resolve()
    base = project / ROOTS[area][1]
    if is_link(base) or not base.resolve().is_relative_to(project):
        raise ValueError('來源位置不在專案內')
    path = base
    for part in parts:
        path = path / part
        if is_link(path):
            raise ValueError('不瀏覽連結或重新導向的資料夾')
    path = path.resolve()
    if not path.is_relative_to(base.resolve()):
        raise ValueError('來源位置超出資料範圍')
    return path, base.resolve()


def listing(settings, area, relative='', offset=0):
    path, base = resolve(settings, area, relative)
    if not path.exists() and not relative:
        return {'area':area,'path':'','entries':[],'total':0,'next_offset':None}
    if not path.is_dir():raise ValueError('請選擇資料夾')
    if type(offset) is not int or offset<0:raise ValueError('分頁無效')
    entries=[]
    for p in path.iterdir():
        if p.name.startswith('.') or is_link(p):continue
        if not p.is_dir() and p.suffix.lower() not in EXTENSIONS:continue
        try:
            st=p.stat()
            entries.append({'name':p.name,'path':p.relative_to(base).as_posix(),'directory':p.is_dir(),
                            'size':None if p.is_dir() else st.st_size,'modified':datetime.fromtimestamp(st.st_mtime,timezone.utc).isoformat()})
        except FileNotFoundError:continue
    entries.sort(key=lambda e:(not e['directory'],e['name'].casefold()))
    return {'area':area,'path':relative,'entries':entries[offset:offset+200],'total':len(entries),
            'next_offset':offset+200 if offset+200<len(entries) else None}


def file_path(settings, area, relative):
    p,_=resolve(settings,area,relative)
    if not p.is_file() or p.suffix.lower() not in EXTENSIONS:raise ValueError('此檔案類型不提供瀏覽或下載')
    return p


def preview(settings, area, relative):
    p=file_path(settings,area,relative)
    if p.suffix.lower() not in TEXT:
        return {'name':p.name,'text':None,'size':p.stat().st_size,'truncated':False}
    with p.open('rb') as f:raw=f.read(PREVIEW_BYTES+1)
    return {'name':p.name,'size':p.stat().st_size,'text':raw[:PREVIEW_BYTES].decode('utf-8-sig',errors='replace'),
            'truncated':len(raw)>PREVIEW_BYTES}


def folder_snapshot(settings, area, relative):
    p,_=resolve(settings,area,relative)
    if not relative or not p.is_dir():raise ValueError('不可移除來源或輸出根目錄；請選下層資料夾')
    files=folders=total=0;digest=hashlib.sha256()
    for directory, dirs, names in os.walk(p,followlinks=False):
        dirs.sort()
        for name in sorted(dirs+names):
            child=Path(directory)/name
            if is_link(child):raise ValueError('資料夾含連結，請先由檔案總管處理')
            st=child.stat();digest.update(f'{child.relative_to(p)}:{st.st_size}:{st.st_mtime_ns}'.encode('utf-8'))
            if child.is_dir():folders+=1
            else:files+=1;total+=st.st_size
            if files+folders>100000:raise ValueError('資料夾項目過多，請選較小的資料夾')
    digest.update(f'{area}:{relative}:{p.stat().st_mtime_ns}'.encode('utf-8'))
    return {'area':area,'path':relative,'name':p.name,'files':files,'folders':folders,'bytes':total,'confirmation':digest.hexdigest()}


def trash_root(settings):
    project=settings.project_root.resolve();p=project/'Data'/'folder_trash'
    if not p.resolve().is_relative_to(project) or is_link(p):raise ValueError('垃圾桶位置無效')
    return p


def trash(settings, data):
    snap=folder_snapshot(settings,data.get('area'),data.get('path'))
    if data.get('confirmation')!=snap['confirmation'] or data.get('confirm_name')!=snap['name']:
        raise ValueError('資料夾已變動或確認不符，請重新預覽並確認')
    source,_=resolve(settings,snap['area'],snap['path'])
    target=trash_root(settings)/uuid.uuid4().hex
    target.mkdir(parents=True,exist_ok=False)
    destination=(target/'folder').resolve()
    if not destination.is_relative_to(trash_root(settings).resolve()):raise ValueError('垃圾桶位置無效')
    record={**snap,'id':target.name,'deleted_at':datetime.now(timezone.utc).isoformat()}
    (target/'record.json').write_text(json.dumps(record,ensure_ascii=False),encoding='utf-8')
    # Both absolute source and destination have been checked within their allowed roots.
    shutil.move(str(source),str(destination))
    return {'ok':True,'message':'已移至專案垃圾桶，可還原；磁碟空間尚未釋放。'}


def trash_list(settings):
    p=trash_root(settings);rows=[]
    if p.exists():
        for child in p.iterdir():
            if len(child.name)!=32 or any(c not in '0123456789abcdef' for c in child.name) or is_link(child):continue
            if (child/'folder').is_dir() and (child/'record.json').is_file():
                rows.append(json.loads((child/'record.json').read_text(encoding='utf-8')))
    return {'entries':sorted(rows,key=lambda r:r['deleted_at'],reverse=True)}


def restore(settings, identity):
    if not isinstance(identity,str) or len(identity)!=32 or any(c not in '0123456789abcdef' for c in identity):raise ValueError('垃圾桶項目無效')
    base=trash_root(settings);item=base/identity
    if is_link(item):raise ValueError('垃圾桶項目無效')
    record=json.loads((item/'record.json').read_text(encoding='utf-8'))
    target,_=resolve(settings,record['area'],record['path'])
    source=(item/'folder').resolve()
    if not source.is_relative_to(base.resolve()) or not source.is_dir():raise ValueError('垃圾桶項目不存在')
    if target.exists():raise ValueError('原位置已有同名資料夾，請先處理，避免覆寫')
    target.parent.mkdir(parents=True,exist_ok=True)
    shutil.move(str(source),str(target))
    (item/'record.json').unlink();item.rmdir()
    return {'ok':True,'message':'資料夾已還原至原位置。'}
