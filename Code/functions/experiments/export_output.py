"""
程式主要目的與功能：
本程式為 EXPERIMENT_ONLY 實驗輸出模組，負責：
1. 同批轉換保存至 Output/markdown_raw/Financial_raw_YYYYMMDD_HH-MM-SS/，紀錄位於該批次內 Record/。
2. 輸出年度_股票代號_raw.md（含頁序標記）及 Financial_Table/ 兩頁PDF；不再保存無頁序版。
3. 與核心轉換解耦，可透過 Settings.export_enabled 集中停用；移除此模組不影響核心流程回傳之 MarkdownDocument。

使用之外部套件與用途：
- 本模組僅使用 Python 內建標準庫（json 序列化執行清冊、datetime 產生台北時區時間戳記、pathlib 處理路徑），未依賴第三方外部套件。
"""

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from schemas import MarkdownDocument
from functions.markdown_processing.file_identity import markdown_filename
from functions.experiments.output_ownership import exclusive_output


def create_markdown_batch(output_root: Path, *, now=None) -> Path:
    """EXPERIMENT_ONLY：以台灣時間命名批次；同秒碰撞停止，不另加流水號。"""
    from config.output_layout import BATCH_NAME_FORMAT
    local = now or datetime.now(timezone(timedelta(hours=8)))
    if local.tzinfo is None:
        raise ValueError('批次時間必須包含時區，未猜測本機時區')
    name = local.astimezone(timezone(timedelta(hours=8))).strftime(BATCH_NAME_FORMAT)
    output_root.mkdir(parents=True, exist_ok=True)
    target = output_root / name
    try:
        target.mkdir()
    except FileExistsError:
        raise FileExistsError(f'同一秒的批次資料夾已存在，未覆寫、未另加流水號：{target}') from None
    return target


def stage_output_batch(settings, stage, output_batch=None):
    """EXPERIMENT_ONLY：一個執行共用新批次；呼叫端可傳入本次已建立的批次。"""
    import re
    import time
    from config.output_layout import BATCH_NAME_PATTERN, STAGE_BATCH_FORMAT
    roots = {'processed': settings.markdown_processed_output_dir,
             'tagged': settings.markdown_tagged_output_dir, 'chunk': settings.markdown_chunk_output_dir}
    if stage not in roots:
        raise ValueError('未知的輸出階段')
    root = roots[stage].resolve()
    if output_batch is not None:
        path = Path(output_batch).resolve()
        if (path.parent != root or not re.fullmatch(BATCH_NAME_PATTERN, path.name)
                or Path(output_batch).is_symlink()):
            raise ValueError('本次輸出批次不在指定階段目錄')
        return path
    for attempt in range(2):
        local = datetime.now(timezone(timedelta(hours=8)))
        path = root / local.strftime(STAGE_BATCH_FORMAT.format(stage=stage))
        if not settings.export_enabled:
            return path  # 不建立Output，核心仍可獨立運作。
        root.mkdir(parents=True, exist_ok=True)
        try:
            path.mkdir()
            return path
        except FileExistsError:
            if attempt == 0:
                # 不加流水號、不覆寫；同秒重跑等待下一秒再保留真正執行時間。
                time.sleep(1 - local.microsecond / 1_000_000 + .01)
    raise FileExistsError('下一秒批次亦已存在；未覆寫，請稍後重試')


def markdown_run_paths(output_root: Path, batch: Path, pdf_stem: str) -> dict:
    """EXPERIMENT_ONLY：集中命名及碰撞檢查；reocrd 為使用者指定拼字。"""
    from functions.markdown_processing.file_identity import source_identity
    identity = source_identity(Path(pdf_stem))
    if identity is None:
        raise ValueError('無法從財報檔名取得年度與股票代號，未輸出；請確認來源命名')
    prefix = '_'.join(identity)
    return {'raw': batch / f'{prefix}_raw.md',
            'table': batch / 'Financial_Table' / f'{prefix}_table.pdf',
            'record': batch / 'Record' / f'{prefix}_reocrd',
            'ocr': batch / 'Record' / f'{prefix}_reocrd.ocr'}


def check_markdown_paths(paths: dict):
    for path in paths.values():
        if path.exists():
            raise FileExistsError(f'輸出已存在，未覆寫：{path}')


def export_markdown_run(output_root: Path, pdf_stem: str, record: dict,
                        document: MarkdownDocument | None, *, batch_dir=None, toc_pdf=None) -> Path:
    """EXPERIMENT_ONLY：只寫頁序 raw、兩頁 PDF 及集中紀錄，不呼叫 Gemini。"""
    target = batch_dir if batch_dir is not None else create_markdown_batch(output_root)
    paths = markdown_run_paths(output_root, target, pdf_stem)
    check_markdown_paths(paths)
    manifest = {key: value for key, value in record.items() if key != 'document'}
    manifest['output_layout'] = 'financial-batch/1.1'
    manifest['batch_dir'] = str(target)
    manifest['markdown_files'] = {'raw': paths['raw'].name} if document else {}
    if document is not None:
        with exclusive_output(paths['raw'], 'xb') as stream:
            stream.write(document.markdown.encode('utf-8'))
    if toc_pdf is not None:
        paths['table'].parent.mkdir(parents=True, exist_ok=True)
        with exclusive_output(paths['table'], 'xb') as stream:
            stream.write(toc_pdf.data)
        manifest['table_pdf'] = str(paths['table'])
        manifest['table_source_pages'] = list(toc_pdf.source_pages)
        manifest['table_source_sha256'] = toc_pdf.source_sha256
        manifest['table_pdf_sha256'] = toc_pdf.extracted_sha256
    paths['record'].parent.mkdir(parents=True, exist_ok=True)
    if 'ocr_diagnostics' in manifest:
        with exclusive_output(paths['ocr'], 'x', encoding='utf-8') as stream:
            json.dump({'schema': 'ocr-diagnostics/1.0', 'pages': manifest.pop('ocr_diagnostics')},
                      stream, ensure_ascii=False, indent=2)
        manifest['ocr_diagnostics_file'] = str(paths['ocr'])
    with exclusive_output(paths['record'], 'x', encoding='utf-8') as stream:
        json.dump(manifest, stream, ensure_ascii=False, indent=2)
    return target


def _write_json(path: Path, value: dict):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def export_toc_run(settings, source: Path, record: dict, pdf, response, result) -> Path | None:
    """EXPERIMENT_ONLY：兩頁PDF、目錄JSON、回答與紀錄；移除時調整main.run_toc。

    核心傳遞TocPdf／TocResult，不從Output讀回；失敗也保留可用診斷但不產生成功JSON。
    """
    if not settings.export_enabled:
        return None
    import re
    from config.markdown_files import PDF_STEM_PATTERN
    timestamp = datetime.now(timezone(timedelta(hours=8))).strftime('%Y%m%d_%H%M%S_%f')
    target = settings.toc_output_dir / source.stem / f'toc_{timestamp}'
    target.mkdir(parents=True, exist_ok=False)
    files = {}
    if pdf is not None:
        (target / 'pages_2_3.pdf').write_bytes(pdf.data)
        files['pdf'] = 'pages_2_3.pdf'
    if response is not None:
        _write_json(target / 'raw_response.json', response)
        files['raw_response'] = 'raw_response.json'
    if result is not None:
        match = re.fullmatch(PDF_STEM_PATTERN, source.stem)
        name = f"{match['year']}_{match['stock']}_toc.json" if match else 'toc.json'
        _write_json(target / name, result.toc)
        (target / 'response.txt').write_bytes(result.response_text.encode('utf-8'))
        files.update(toc=name, response_text='response.txt')
    _write_json(target / 'manifest.json', {**record, 'files': files})
    return target


def export_heading_run(settings, source: Path, record: dict, result) -> Path | None:
    """EXPERIMENT_ONLY：補標記 Markdown 與逐行紀錄；移除時調整 main.run_mark_headings。

    markdown_raw 來源相對於該目錄；其他專案檔相對專案根，外部檔採檔名。
    原始絕對來源另記在 manifest，永不覆寫來源或既有結果。
    """
    if not settings.export_enabled:
        return None
    if source.is_relative_to(settings.markdown_output_dir.resolve()):
        relative = source.relative_to(settings.markdown_output_dir.resolve())
    elif source.is_relative_to(settings.project_root.resolve()):
        relative = source.relative_to(settings.project_root.resolve())
    else:
        relative = Path(source.name)
    timestamp = datetime.now(timezone(timedelta(hours=8))).strftime('%Y%m%d_%H%M%S_%f')
    target = settings.markdown_processed_output_dir / relative.with_suffix('') / f'headings_{timestamp}'
    target.mkdir(parents=True, exist_ok=False)
    # bytes 防止 Windows 自動把來源 LF 正規化成 CRLF。
    output_name=markdown_filename(source,'processed')
    (target / output_name).write_bytes(result.markdown.encode('utf-8'))
    _write_json(target / 'manifest.json', {**record,'markdown_files':{'processed':output_name}})
    return target


def processed_run_paths(settings, batch_name: str, prefix: str) -> dict:
    """EXPERIMENT_ONLY：第二階段固定批次及集中紀錄路徑。"""
    target = settings.markdown_processed_output_dir / batch_name
    return {'markdown': target / f'{prefix}_processed.md',
            'toc': target / f'{prefix}_tablerefer.json',
            'record': target / 'Record' / f'{prefix}_reocrd'}


def export_processed_run(settings, paths: dict, record: dict, heading_result, toc_result):
    """EXPERIMENT_ONLY：目錄失敗仍保存補標題，只有有效目錄才寫 JSON。"""
    if not settings.export_enabled:
        return None
    check_markdown_paths(paths)
    paths['markdown'].parent.mkdir(parents=True, exist_ok=True)
    paths['record'].parent.mkdir(parents=True, exist_ok=True)
    if heading_result is not None:
        with exclusive_output(paths['markdown'], 'xb') as stream:
            stream.write(heading_result.markdown.encode('utf-8'))
    if toc_result is not None and toc_result.status == 'extracted_needs_review':
        with exclusive_output(paths['toc'], 'x', encoding='utf-8') as stream:
            json.dump(toc_result.toc, stream, ensure_ascii=False, indent=2)
    with exclusive_output(paths['record'], 'x', encoding='utf-8') as stream:
        json.dump(record, stream, ensure_ascii=False, indent=2)
    return paths['markdown'].parent


def export_tagging_run(settings, source: Path, record: dict, result) -> Path | None:
    """EXPERIMENT_ONLY：自訂標籤Markdown及紀錄；移除時調整main.run_tag_markdown。

    不輸出正文JSON／chunk，停用寫檔仍可取得核心記憶體結果。
    """
    if not settings.export_enabled:
        return None
    root=settings.markdown_processed_output_dir.resolve()
    relative=source.relative_to(root) if source.is_relative_to(root) else Path(source.name)
    timestamp=datetime.now(timezone(timedelta(hours=8))).strftime('%Y%m%d_%H%M%S_%f')
    target=settings.markdown_tagged_output_dir / relative.with_suffix('') / f'tagging_{timestamp}'
    target.mkdir(parents=True,exist_ok=False)
    output_name=markdown_filename(source,'tagged')
    (target/output_name).write_bytes(result.markdown.encode('utf-8'))
    _write_json(target/'manifest.json',{**record,'markdown_files':{'tagged':output_name}})
    return target


def comment_tag_paths(settings, batch_name, prefix):
    """EXPERIMENT_ONLY：單行註解標籤批次，不沿用舊巢狀路徑。"""
    target = settings.markdown_tagged_output_dir / batch_name
    return {'markdown': target / f'{prefix}_tagged.md',
            'record': target / 'Record' / f'{prefix}_reocrd'}


def chunk_run_paths(settings, batch_name, prefix):
    """EXPERIMENT_ONLY：移除時調整chunking/batch.py呼叫與Settings路徑。"""
    target = settings.markdown_chunk_output_dir / batch_name / settings.chunking.mode
    suffix = f'_{settings.chunking.recursive_threshold}' if settings.chunking.mode == 'parent_child' else ''
    suffix += f'_text-{settings.chunking.text_embedding_mode}_table-{settings.chunking.table_embedding_mode}'
    return {'markdown': target / f'{prefix}_chunk{suffix}.md', 'json': target / f'{prefix}_chunk{suffix}.json',
            'record': target / 'Record' / f'{prefix}{suffix}_reocrd'}


def export_chunks(settings, paths, record, result):
    """EXPERIMENT_ONLY：MD與JSON採同一核心結果，失敗只留Record。"""
    if not settings.export_enabled:
        return None
    check_markdown_paths(paths)
    paths['record'].parent.mkdir(parents=True, exist_ok=True)
    if result is not None:
        payloads = {'markdown': result.markdown.encode('utf-8'),
                    'json': json.dumps(result.document, ensure_ascii=False, indent=2).encode('utf-8')}
        created = []
        try:
            for role, data in payloads.items():
                with exclusive_output(paths[role], 'xb') as stream:
                    created.append(paths[role])
                    stream.write(data)
        except (OSError, KeyboardInterrupt) as error:
            # 僅移除本次以xb建立的檔案；不動來源或既有產物，不留下單邊假成功。
            for path in created:
                path.unlink(missing_ok=True)
            record.update(status='interrupted' if isinstance(error, KeyboardInterrupt) else 'failed',
                          error=f'chunk輸出未完成：{type(error).__name__}: {error}')
            payloads = {}
        import hashlib
        if payloads:
            record['outputs'] = {role: {'filename': paths[role].name, 'sha256': hashlib.sha256(data).hexdigest()}
                                 for role, data in payloads.items()}
    with exclusive_output(paths['record'], 'x', encoding='utf-8') as stream:
        json.dump(record, stream, ensure_ascii=False, indent=2)
    return paths['markdown'].parent


def export_comment_tags(settings, paths, record, result):
    """EXPERIMENT_ONLY：失敗只留紀錄，不輸出猜配的標籤文件。"""
    if not settings.export_enabled:
        return None
    check_markdown_paths(paths)
    paths['record'].parent.mkdir(parents=True, exist_ok=True)
    if result is not None:
        with exclusive_output(paths['markdown'], 'xb') as stream:
            stream.write(result.markdown.encode('utf-8'))
    with exclusive_output(paths['record'], 'x', encoding='utf-8') as stream:
        json.dump(record, stream, ensure_ascii=False, indent=2)
    return paths['markdown'].parent


def migrate_markdown_filenames(settings, *, apply=False):
    """EXPERIMENT_ONLY：已獲授權的既有財報Markdown改名；保留內容雜湊及舊名。

    不動PDF、目錄、模型、合成測試檔或程式說明；同步manifest來源引用。
    預先確認所有碰撞及紀錄可讀性，例外時回復本次已改動項目。
    """
    import hashlib
    from functions.markdown_processing.file_identity import filename_identity,source_identity
    roots=[settings.markdown_output_dir,settings.markdown_processed_output_dir,settings.markdown_tagged_output_dir]
    plan=[]
    for root in roots:
        root=root.resolve()
        for source in sorted(root.rglob('*.md')):
            source=source.resolve()
            if not source.is_relative_to(root):
                raise ValueError('改名來源超出指定Output目錄')
            if filename_identity(source.name) or not source_identity(source):
                continue
            role=source.stem
            if source.name=='document.md':
                role='processed' if root==settings.markdown_processed_output_dir.resolve() else 'tagged' if root==settings.markdown_tagged_output_dir.resolve() else 'document'
            target=source.with_name(markdown_filename(source,role))
            if target.exists() or not target.resolve().is_relative_to(root):
                raise FileExistsError(f'改名目標衝突或超出Output：{target}')
            if not (source.parent/'manifest.json').is_file():
                raise ValueError(f'缺少manifest，無法保留改名紀錄：{source}')
            plan.append({'old':str(source),'new':str(target),'sha256':hashlib.sha256(source.read_bytes()).hexdigest()})
    if len({x['new'] for x in plan})!=len(plan):
        raise ValueError('多個來源將改成同一檔名；未改名')
    if not apply or not plan:
        return plan
    if not settings.export_enabled:
        raise ValueError('實驗輸出已停用，未改名')
    mapping={x['old']:x['new'] for x in plan}
    mapping.update({Path(x['old']).as_posix():Path(x['new']).as_posix() for x in plan})
    manifests={p:(p.read_bytes(),json.loads(p.read_text(encoding='utf-8'))) for root in roots for p in root.rglob('manifest.json')}

    def replace_references(value,changes):
        if isinstance(value,dict):return {k:replace_references(v,changes) for k,v in value.items()}
        if isinstance(value,list):return [replace_references(v,changes) for v in value]
        if isinstance(value,str) and value in mapping:
            changes.append({'old':value,'new':mapping[value]})
            return mapping[value]
        return value

    moved=[];written=[]
    try:
        for item in plan:
            source,target=Path(item['old']),Path(item['new'])
            if hashlib.sha256(source.read_bytes()).hexdigest()!=item['sha256']:
                raise ValueError('Markdown在改名前發生變更')
            source.rename(target);moved.append((source,target))
        for manifest,(old_bytes,data) in manifests.items():
            changes=[];updated=replace_references(data,changes)
            own=[{'old_name':Path(x['old']).name,'new_name':Path(x['new']).name,'sha256':x['sha256']} for x in plan if Path(x['old']).parent==manifest.parent]
            if changes or own:
                updated['filename_migration']={'version':'markdown-filenames/1.0','renamed_files':own,'updated_references':changes}
                updated['markdown_files']={p.stem:p.name for p in sorted(manifest.parent.glob('*.md'))}
                written.append(manifest)
                _write_json(manifest,updated)
    except Exception:
        for manifest in reversed(written):manifest.write_bytes(manifests[manifest][0])
        for source,target in reversed(moved):target.rename(source)
        raise
    return plan


def export_ocr_validation(settings, source: Path, record: dict, documents: dict) -> Path | None:
    """EXPERIMENT_ONLY：局部 OCR 實測；停用寫檔仍回傳記憶體結果。"""
    if not settings.export_enabled:
        return None
    timestamp = datetime.now(timezone(timedelta(hours=8))).strftime("%Y%m%d_%H%M%S_%f")
    target = settings.markdown_output_dir / source.stem / f"ocr_validation_{timestamp}"
    target.mkdir(parents=True, exist_ok=False)
    _write_json(target / 'manifest.json', record)
    from PIL import ImageDraw
    import pypdfium2 as pdfium
    with pdfium.PdfDocument(source) as pdf:
        for page_no, document in documents.items():
            output_name=markdown_filename(source,f'page_{page_no}',f'page_{page_no}.md')
            (target / output_name).write_bytes(document.markdown.encode('utf-8'))
            # 座標覆圖只用於實驗人工核對，不改動 PDF。
            image = pdf[page_no-1].render(scale=1.5).to_pil().convert('RGB')
            draw = ImageDraw.Draw(image)
            diag = next((d for d in record['ocr_diagnostics'] if d['pdf_page']==page_no), {})
            for region in diag.get('regions', []):
                for line in region.get('lines', []):
                    points = [(x*1.5,y*1.5) for x,y in line['pdf_quad']]
                    draw.line(points+[points[0]], fill='magenta' if line['accepted'] else 'red', width=2)
            image.save(target / f'page_{page_no}_ocr.png')
    return target


def export_synthetic_mixed_fixture(output_root: Path, font_path: Path) -> Path:
    """EXPERIMENT_ONLY：已確認的合成混合頁；不是財報或實際辨識結果。"""
    from io import BytesIO
    from PIL import Image, ImageDraw, ImageFont
    from reportlab.pdfgen import canvas
    from reportlab.lib.utils import ImageReader
    target = output_root / 'synthetic_mixed_fixture'
    target.mkdir(parents=True, exist_ok=True)
    path = target / 'synthetic_mixed.pdf'
    if path.exists():
        raise FileExistsError('不覆寫已存在的合成測試頁')
    bitmap=Image.new('RGB',(1380,330),'white')
    draw=ImageDraw.Draw(bitmap)
    font=ImageFont.truetype(str(font_path),52)
    draw.text((30,45),'掃描區域 新臺幣仟元',font=font,fill='black')
    draw.text((30,150),'114年度 (9,876.50) -12.5%',font=font,fill='black')
    image=BytesIO();bitmap.save(image,format='PNG');image.seek(0)
    pdf=canvas.Canvas(str(path),pagesize=(612,792))
    pdf.setFont('Helvetica',15)
    pdf.drawString(72,730,'SYNTHETIC MIXED PAGE - ENGINEERING TEST ONLY')
    pdf.setFont('Helvetica',13)
    pdf.drawString(72,660,'NATIVE: USD (1,234.50) -6.00 100% FY2025')
    pdf.drawImage(ImageReader(image),72,430,width=460,height=110)
    pdf.setFont('Helvetica',11)
    pdf.drawString(72,360,'Native text above must remain once; bitmap text needs OCR.')
    pdf.save()
    _write_json(target / 'expected.json',{'synthetic':True,'physical_page':1,
                'native':'NATIVE: USD (1,234.50) -6.00 100% FY2025',
                'bitmap':['掃描區域 新臺幣仟元','114年度 (9,876.50) -12.5%'],
                'purpose':'人工建立的預期文字；不是模型輸出，不能代表真實混合頁品質'})
    return path
