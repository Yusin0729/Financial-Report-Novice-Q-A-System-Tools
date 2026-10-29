"""重用Code工作面板與腳本；由統一網站提供同來源資產，不複製處理邏輯。"""
import re
from pathlib import Path

SOURCE=Path(__file__).resolve().parents[3]/'Code/functions/web_ui'


def asset(name, values, token):
    original=(SOURCE/'index.html').read_text(encoding='utf-8')
    for key,value in {**values,'token':token}.items():
        if key=='ocr_checked':
            value='checked' if value else ''
        original=original.replace('__'+key.upper()+'__',str(value))
    if name=='legacy.css':
        return re.search(r'<style>(.*?)</style>',original,re.S).group(1)
    if name=='legacy.js':
        script=re.search(r'<script>\s*(const token=.*?)</script>',original,re.S).group(1)
        return script.replace("fetch('/api/'+path", "fetch('/api/workspace/'+path").replace("'X-UI-Token':token", "'X-App-Token':token")
    if name=='index.html':
        original=re.sub(r'<style>.*?</style>', '<link rel="stylesheet" href="/workspace/legacy.css"><link rel="stylesheet" href="/style.css"><link rel="stylesheet" href="/workspace.css">',original,flags=re.S)
        original=original.replace('</head>',f'<meta name="app-token" content="{token}"></head>')
        original=re.sub(r'<script>\s*const token=.*?</script>', '<script src="/workspace/legacy.js"></script>',original,flags=re.S)
        original=original.replace('<script>refreshApiSettings().catch(fail);</script>','<script src="/workspace.js"></script>')
        original=original.replace(' onclick="openApiSettings()"','')
        original=original.replace('src="/selection.js"','src="/workspace/selection.js"').replace('src="/database.js"','src="/workspace/database.js"')
        return original
    if name in ('selection.js','database.js'):
        return (SOURCE/name).read_text(encoding='utf-8')
    raise ValueError('未知工作區資產')
