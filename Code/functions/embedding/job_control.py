"""建庫在文件邊界安全停止；只含本批來源ID，不包含密鑰或正文。"""
import json
import re
import uuid
from pathlib import Path


def control_path(settings,job_id):
    if not isinstance(job_id,str) or not re.fullmatch(r'[a-f0-9]{32}',job_id):
        raise ValueError('建庫工作識別無效')
    path=settings.vector_job_dir/f'{job_id}.json'
    if not path.resolve().is_relative_to(settings.project_root.resolve()) or path.is_symlink():
        raise ValueError('建庫控制檔超出專案')
    return path


def create_control(settings,job_id,files):
    if not isinstance(files,list) or not files or any(not isinstance(f,str) for f in files) or len(set(files))!=len(files):
        raise ValueError('建庫工作來源清單無效')
    path=control_path(settings,job_id)
    path.parent.mkdir(parents=True,exist_ok=True)
    with path.open('x',encoding='utf-8') as stream:
        json.dump({'schema_version':'vector-job-control/1.0','job_id':job_id,'files':files,
                   'stop_requested':False,'stop_after':None},stream,ensure_ascii=False)


def read_control(settings,job_id):
    value=json.loads(control_path(settings,job_id).read_text(encoding='utf-8'))
    if (not isinstance(value,dict) or value.get('schema_version')!='vector-job-control/1.0' or value.get('job_id')!=job_id
            or type(value.get('stop_requested')) is not bool or not isinstance(value.get('files'),list)
            or (value.get('stop_after') is not None and value['stop_after'] not in value['files'])):
        raise ValueError('建庫控制內容無效，未繼續下一份')
    return value


def request_stop(settings,job_id,after_file=None):
    value=read_control(settings,job_id)
    if after_file is not None and after_file not in value['files']:
        raise ValueError('停止位置不在本次建庫清單')
    value.update(stop_requested=True,stop_after=after_file)
    path=control_path(settings,job_id)
    temporary=path.with_name(path.name+'.'+uuid.uuid4().hex+'.tmp')
    try:
        with temporary.open('x',encoding='utf-8') as stream:json.dump(value,stream,ensure_ascii=False)
        temporary.replace(path)
    finally:temporary.unlink(missing_ok=True)
    return value


def remove_control(settings,job_id):
    control_path(settings,job_id).unlink(missing_ok=True)
