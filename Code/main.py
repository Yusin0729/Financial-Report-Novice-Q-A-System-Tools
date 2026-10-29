"""
程式主要目的與功能：
本程式為完整財報分析系統的命令列互動入口與流程串接模組，提供：
1. 互動式選單瀏覽 Financial Statements/ 下所有 PDF（支援單選、多選與全選）。
2. 調用 Docling 轉換 PDF，提供預設關閉的 MinerU ch_lite OCR 開關。
3. 系統執行環境與可用記憶體檢查（--check-env）。
4. 實驗產物集中導出至 Output/markdown_raw/。
5. 獨立處理既有 Markdown 的漏抓標題，實驗輸出至 markdown_processed/。

使用之外部套件與用途：
- pypdfium2: 高效讀取 PDF 檔案資訊（如頁數）與後端渲染驗證。
- psutil: 顯示可用記憶體，供使用者判斷執行環境；目前不自動阻擋低記憶體執行。
"""

import argparse
import json
import os
import platform
import re
import subprocess
import sys
import time
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))


def ensure_project_python(script_path=None):
    """直接執行入口時，在匯入第三方套件前切換到專案 Python 3.11。"""
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    from config.runtime import PDF_ENVIRONMENT_NAME, use_current_python
    if use_current_python():
        if sys.version_info < (3, 11):
            raise SystemExit('Colab／共用環境須使用 Python 3.11 以上')
        return
    environment = Path(__file__).resolve().parent / PDF_ENVIRONMENT_NAME
    interpreter = environment / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    if Path(sys.prefix).resolve() == environment.resolve():
        if sys.version_info[:2] != (3, 11):
            raise SystemExit("Code/.venv_pdf 必須使用 Python 3.11；請依 Code/README.md 重建環境。")
        return
    if not interpreter.is_file():
        raise SystemExit("找不到 Code/.venv_pdf 的 Python；請依 Code/README.md 安裝 PDF 專用環境。")
    print(f"切換至專案 Python 3.11：{interpreter}", flush=True)
    result = subprocess.run([str(interpreter), str(Path(script_path or __file__).resolve()), *sys.argv[1:]])
    raise SystemExit(result.returncode)


if __name__ == "__main__":
    ensure_project_python()

from functions.ingestion.pdf_to_markdown import conversion_versions, source_hash
from config.settings import SETTINGS, Settings
from functions.markdown_processing.process_batch import process_raw_batch
from functions.markdown_processing.tag_batch import tag_processed_batch
from functions.chunking.batch import chunk_tagged_batch, list_tagged_batches


def run_markdown(pdf_path: Path, settings: Settings = SETTINGS, *, batch_dir=None, progress_callback=None) -> dict:
    """核心回傳記憶體物件；Output 可集中停用，不自動進入目錄解析。"""
    import pypdfium2 as pdfium
    from functions.ingestion.pdf_to_markdown import conversion_versions, convert_pdf, validate_source
    from schemas import MARKDOWN_SCHEMA_VERSION

    pdf_path = validate_source(pdf_path, settings)
    if settings.export_enabled:
        # EXPERIMENT_ONLY：提前檢查集中紀錄，避免轉換後才發現檔案已存在。
        from functions.experiments.export_output import create_markdown_batch, markdown_run_paths, check_markdown_paths
        batch_dir = batch_dir if batch_dir is not None else create_markdown_batch(settings.markdown_output_dir)
        check_markdown_paths(markdown_run_paths(settings.markdown_output_dir, batch_dir, pdf_path.stem))
    start = time.perf_counter()
    before = source_hash(pdf_path)
    document = None
    record = {
        "schema_version": MARKDOWN_SCHEMA_VERSION,
        "started_at": datetime.now(timezone(timedelta(hours=8))).isoformat(),
        "source": {"filename": pdf_path.name, "sha256": before},
        "settings": settings.pdf_manifest(), "package_versions": conversion_versions(),
        "runtime_environment": {"python": platform.python_version(), "executable": sys.executable},
        "status": "running", "stage": "inspect_pdf", "document": None,
    }

    def progress(event):
        if event.kind == "page_completed":
            if progress_callback is not None:
                progress_callback({
                    "kind": "page_completed",
                    "completed_pages": event.completed_pages,
                    "total_pages": event.total_pages,
                    "page_no": event.page_no,
                    "success": event.success,
                })
            print(f"已處理 {event.completed_pages}/{event.total_pages} 頁；PDF 第 {event.page_no} 頁："
                  + ("完成" if event.success else "失敗"), flush=True)
        elif event.kind == "phase_started":
            print(f"Docling 階段：{event.phase.value}", flush=True)

    try:
        with pdfium.PdfDocument(pdf_path) as pdf:
            count = len(pdf)
        record["source"]["pdf_page_count"] = count
        if count < 3:
            raise ValueError('PDF 不足3頁，無法判定目錄範圍')
        from schemas import MarkdownDocument
        from functions.ingestion.page_selection import select_from_toc, find_notes_in_body, _compact
        from config.page_selection import SELECTION_RULE_VERSION, NORMALIZATION_FORM
        record['selection_rule_version'] = SELECTION_RULE_VERSION
        record['comparison_normalization'] = NORMALIZATION_FORM
        from functions.ingestion.pdf_to_markdown import create_converter
        from functions.markdown_processing.page_markers import format_page_marker
        from functions.markdown_processing.file_identity import source_identity
        from functions.ingestion.timings import wall_timer
        with wall_timer(record, 'converter_setup'):
            converter_bundle = create_converter(settings)
        converted = {}
        documents = []

        def convert_range(first, last):
            current_settings, current_bundle = settings, converter_bundle
            if settings.pdf_parser == 'inspector' and (first,last) == (2,3):
                # 目錄沿用已驗證的Docling結構；inspector的平面目錄可能把頁碼配到錯列。
                current_settings = replace(settings,pdf_parser='docling')
                session = converter_bundle[0]
                if session.fallback is None:
                    session.fallback = create_converter(current_settings)
                current_bundle = session.fallback
                record['toc_parser'] = 'docling'
            part = convert_pdf(pdf_path, count, current_settings, record, progress,
                               page_range=(first, last), converter_bundle=current_bundle)
            documents.append(part)
            for page in part.pages:
                converted[page.pdf_page] = page

        def page_text(number):
            if number in converted:
                return converted[number].markdown
            if settings.ocr_enabled or settings.pdf_parser == 'inspector':
                # Inspector備援搜尋亦讀自身快取，不能退回不同字型解碼的PDFium原生文字。
                # 備援搜尋頁仍交由既有按需 OCR 判斷，不因局部原生文字漏掉影像標題。
                convert_range(number, number)
                return converted[number].markdown
            with pdfium.PdfDocument(pdf_path) as source_pdf:
                source_page = source_pdf[number - 1]
                try:
                    native = source_page.get_textpage().get_text_range()
                finally:
                    source_page.close()
            if native.strip():
                return native
            raise ValueError(f'PDF 第{number}頁沒有可讀文字且OCR關閉；無法確認選頁範圍')

        record['stage'] = 'read_local_toc'
        convert_range(2, 3)
        if not settings.ocr_enabled and converted[2].status == 'no_text_extracted':
            raise ValueError('PDF 第2頁沒有可讀文字且OCR關閉；無法辨識目錄')
        try:
            selection = select_from_toc(converted[2].markdown, converted[3].markdown, count)
            toc_end = selection['toc_pages'][-1]
            selection['notes_source'] = 'local_toc' if selection['notes_start'] else None
            selection['audit_source'] = 'local_toc' if selection['audit_pages'] else None
        except ValueError as error:
            # 目錄讀不到時，先避開可能的第2、3頁目錄，再從正文尋找明確文字。
            selection = {'toc_pages': [], 'audit_pages': None, 'notes_start': None,
                         'toc_error': str(error)}
            toc_end = 3
        notes_start = selection['notes_start']
        record['selection'] = selection
        if notes_start is None:
            notes_start, notes_source = find_notes_in_body(
                page_text, toc_end + 1, count,
                audit_end=selection['audit_pages'][1] if selection['audit_pages'] else None)
            selection.update(notes_start=notes_start, notes_source=notes_source)
        if notes_start is None:
            raise ValueError('目錄與正文均未找到公司沿革或獨立附註主標，無法定位附註')
        audit = selection['audit_pages']
        if audit is None:
            candidates = [(number, _compact(page_text(number)))
                          for number in range(toc_end + 1, notes_start)]
            starts = [number for number, body in candidates if '會計師查核報告' in body]
            statements = [number for number, body in candidates if '合併資產負債表' in body]
            if starts and any(number > starts[0] for number in statements):
                audit = (starts[0], min(number for number in statements if number > starts[0]) - 1)
                selection['audit_source'] = 'body_headings'
                selection['audit_heading_pages'] = {'report': starts[0], 'statement': audit[1] + 1}
            else:
                firms = ('勤業', '資誠', '安永', '安侯')
                matched = [{'pdf_page': number, 'terms': [firm for firm in firms if firm in body]}
                           for number, body in candidates if any(firm in body for firm in firms)]
                hits = [item['pdf_page'] for item in matched]
                if hits:
                    audit = (hits[0], hits[-1])
                    selection['audit_source'] = 'firm_name_needs_review'
                    selection['firm_hits'] = matched
        if audit is None or not toc_end < audit[0] <= audit[1] < notes_start:
            raise ValueError('無法可靠定位完整會計師查核報告；未輸出裁切結果')
        selected = {*range(audit[0], audit[1] + 1), *range(notes_start, count + 1)}
        selection.update(audit_pages=list(audit), notes_start=notes_start,
                         selected_pdf_pages=sorted(selected), page_number_policy='original_pdf_physical_page')
        record['selection'] = selection
        record['stage'] = 'convert_selected_pages'
        ocr_label = "開啟（CPU ch_lite，按需辨識）" if settings.ocr_enabled else "關閉（只擷取可讀取的文字）"
        print(f"選定轉換 {pdf_path.name}，保留 {len(selected)}/{count} 頁；CPU／OCR：{ocr_label}。", flush=True)
        remaining = sorted(selected - converted.keys())
        while remaining:
            first = last = remaining[0]
            while last + 1 in remaining:
                last += 1
            convert_range(first, last)
            remaining = sorted(selected - converted.keys())
        assemble_started = time.perf_counter()
        identity = source_identity(pdf_path)
        pages = tuple(converted[number] for number in sorted(selected))
        from functions.ingestion.section_markers import assemble_selected_pages
        marked = assemble_selected_pages(pages, identity, audit[0], notes_start)
        document = MarkdownDocument('\n'.join(page.markdown for page in pages), marked,
                                    pages, tuple(w for part in documents for w in part.warnings),
                                    tuple(part.docling_document for part in documents))
        markdown_timing = record.setdefault('timing_details', {}).setdefault('markdown_output',
            {'seconds': 0.0, 'calls': 0, 'failed_calls': 0})
        markdown_timing['seconds'] += time.perf_counter() - assemble_started
        markdown_timing['calls'] += 1
        record.update(
            status="converted_needs_review", document=document,
            pages=[page.metadata() for page in document.pages], warnings=list(document.warnings),
        )
        missing_text = [page.pdf_page for page in document.pages if page.status == 'no_text_extracted'
                        and page.pdf_page != 1]
        if missing_text:
            record.update(status='failed', error=f'保留頁沒有擷取到文字：{missing_text}；請核對 OCR 與原始 PDF')
            document = None
            record['document'] = None
        print(f"轉換狀態：{record['status']}；仍需人工核對目錄、表格與數值。")
    except KeyboardInterrupt:
        record.update(status="interrupted", error="使用者中止轉換")
        print("已中止；此次未視為完整轉換。")
    except Exception as error:
        record.update(status="failed", error=f"{type(error).__name__}: {error}")
        print(f"階段 {record['stage']} 失敗：{record['error']}", file=sys.stderr)
    finally:
        record["elapsed_seconds"] = round(time.perf_counter() - start, 3)
        from functions.ingestion.timings import finalize_timings, timing_text
        print('階段耗時（不可直接加總）：' + timing_text(finalize_timings(record)))
        record["source"]["unchanged"] = source_hash(pdf_path) == before
        if not record["source"]["unchanged"]:
            record.update(status="failed", error="原始 PDF 在執行期間發生變更；請重新核對來源")
            document = None
            record['document'] = None
        if settings.export_enabled:
            # EXPERIMENT_ONLY：移除此呼叫不影響核心回傳的 MarkdownDocument。
            from functions.experiments.export_output import export_markdown_run
            output = export_markdown_run(settings.markdown_output_dir, pdf_path.stem, record, document,
                                         batch_dir=batch_dir)
            record["output_dir"] = str(output)
            print(f"檢查產物：{output}")
    return record


def check_environment(settings: Settings = SETTINGS):
    import psutil

    print(json.dumps({
        "python": platform.python_version(), "executable": sys.executable,
        "packages": conversion_versions(),
        "ram_total_gib": round(psutil.virtual_memory().total / 1024**3, 2),
        "ram_available_gib": round(psutil.virtual_memory().available / 1024**3, 2),
        "settings": settings.pdf_manifest(),
    }, ensure_ascii=False, indent=2))


def run_toc(*_args, **_kwargs):
    """舊程式相容名稱；目錄 Gemini 入口已停用，不傳送任何 PDF。"""
    raise RuntimeError('Gemini 目錄入口已停用；請使用第一階段本機選頁')


def run_mark_headings(path: Path, settings: Settings = SETTINGS) -> dict:
    """獨立處理既有 Markdown，不進入 PDF／OCR 流程。"""
    import hashlib
    from dataclasses import asdict
    from config.markdown_headings import (MAX_CANDIDATE_LENGTH, EXCLUDED_ENDINGS, MARKER_PATTERNS,
                                         LIST_PREFIX_PATTERN, PAGE_NUMBER_PATTERN)
    from functions.markdown_processing.load_source import load_source
    from functions.markdown_processing.note_processing import process_note_content
    source, text, before = load_source(path)
    started = time.perf_counter()
    result, removed, scope = process_note_content(text)
    from functions.markdown_processing.page_cleanup import CLEANUP_VERSION
    if hashlib.sha256(source.read_bytes()).hexdigest() != before:
        raise RuntimeError('來源 Markdown 在處理期間改變；未輸出結果')
    record = {
        'schema_version': 'markdown-heading-run/1.0', 'rule_version': result.rule_version,
        'started_at': datetime.now(timezone(timedelta(hours=8))).isoformat(),
        'status': 'processed_needs_review',
        'source': {'path': str(source), 'sha256': before, 'unchanged': True},
        'output_sha256': hashlib.sha256(result.markdown.encode('utf-8')).hexdigest(),
        'settings': {'max_candidate_length': MAX_CANDIDATE_LENGTH,
                     'excluded_endings': sorted(EXCLUDED_ENDINGS),
                     'marker_patterns': dict(MARKER_PATTERNS), 'export_enabled': settings.export_enabled,
                     'list_prefix_pattern': LIST_PREFIX_PATTERN, 'page_number_pattern': PAGE_NUMBER_PATTERN},
        'change_count': len(result.changes), 'changes': [asdict(change) for change in result.changes],
        'page_cleanup_version': CLEANUP_VERSION, 'removed_page_lines': list(removed),
        'processing_scope': scope,
        'elapsed_seconds': round(time.perf_counter()-started, 6),
    }
    # EXPERIMENT_ONLY：停用寫檔仍回傳 result 記憶體資料，不依賴 Output 傳遞。
    from functions.experiments.export_output import export_heading_run
    target = export_heading_run(settings, source, record, result)
    print(f'補標記完成：{len(result.changes)} 行；仍需人工核對。')
    if target:
        print(f'檢查產物：{target}')
    return {**record, 'result': result, 'output_dir': str(target) if target else None}


def run_tag_markdown(path: Path, settings: Settings = SETTINGS, *, notes_scope=None) -> dict:
    """獨立載入已補標記Markdown；不解析PDF或目錄、不呼叫LLM。"""
    from collections import Counter
    from dataclasses import asdict
    from functions.markdown_processing.load_source import load_source
    from functions.markdown_processing.tag_markdown import tag_markdown, text_hash
    from schemas import TaggingMetadata
    from functions.markdown_processing.notes_scope import confirmed_notes_scope
    source,text,before=load_source(path)
    started_at=datetime.now(timezone(timedelta(hours=8))).isoformat()
    started=time.perf_counter()
    from functions.markdown_processing.file_identity import filename_identity
    identity=filename_identity(source.name)
    metadata=TaggingMetadata(stock_code=identity[1],report_year=identity[0]) if identity else TaggingMetadata()
    scope=notes_scope if notes_scope is not None else confirmed_notes_scope(text)
    result=tag_markdown(text,metadata,notes_scope=scope)
    if source_hash(source)!=before:
        raise RuntimeError('來源Markdown在處理期間改變，未輸出')
    record={
        'schema_version':'markdown-tagging-run/1.0','tagging_version':result.version,
        'started_at':started_at,'status':'tagged_needs_review',
        'source':{'path':str(source),'sha256':before,'unchanged':True},
        'original_markdown_sha256':result.original_sha256,'output_sha256':text_hash(result.markdown),
        'metadata':asdict(metadata),
        'notes_scope':asdict(result.notes_scope),
        'metadata_sources':{key:('filename_prefix' if identity and key in ('stock_code','report_year') else 'unknown') for key in asdict(metadata)},
        'block_counts':dict(Counter(block.kind for block in result.blocks)),
        'heading_counts_by_level':dict(Counter(str(b.path[-1].level) for b in result.blocks if b.kind=='heading')),
        'issues':list(result.issues),'printed_page_candidates':list(result.printed_page_candidates),
        'settings':{'export_enabled':settings.export_enabled,'only_two_hash_headings':True},
        'elapsed_seconds':round(time.perf_counter()-started,6),
    }
    # EXPERIMENT_ONLY：移除輸出仍可使用result，不以Output傳遞核心資料。
    from functions.experiments.export_output import export_tagging_run
    target=export_tagging_run(settings,source,record,result)
    print(f'加標籤完成：{len(result.blocks)} 個標記區塊；仍需人工核對階層。')
    if target:
        print(f'檢查產物：{target}')
    return {**record,'result':result,'output_dir':str(target) if target else None}


def choose_markdown(settings: Settings, *, root: Path | None = None) -> Path | None:
    from functions.markdown_processing.load_source import is_selectable_markdown
    root=root if root is not None else settings.markdown_output_dir
    files = sorted(p for p in root.rglob('*.md') if is_selectable_markdown(p))
    if not files:
        print(f'{root.name} 內沒有可載入的Markdown結果。')
        return None
    print('\n既有 Markdown 清單：')
    for index, path in enumerate(files, 1):
        print(f'{index}. {path.relative_to(root).as_posix()}')
    while True:
        value = input('選擇單一 Markdown 編號（0 返回）：').strip()
        if value == '0':
            return None
        if value.isascii() and value.isdigit() and 1 <= int(value) <= len(files):
            return files[int(value)-1]
        print('請輸入有效的單一編號，或 0 返回。')


def choose_raw_batch(settings: Settings) -> Path | None:
    from functions.markdown_processing.process_batch import list_raw_batches
    batches = list_raw_batches(settings)
    if not batches:
        print('沒有新格式的 raw 批次；請先執行第一階段轉換。')
        return None
    print('\n可用 raw 批次（本機補標題與清理頁碼）：')
    for index, batch in enumerate(batches, 1):
        print(f'{index}. {batch.name}（{len(list(batch.glob("*_raw.md")))}份）')
    while True:
        value = input('選擇批次編號（0 返回）：').strip()
        if value == '0':
            return None
        if value.isascii() and value.isdigit() and 1 <= int(value) <= len(batches):
            return batches[int(value) - 1]
        print('請輸入有效批次編號，或 0 返回。')


def choose_processed_batch(settings: Settings) -> Path | None:
    from functions.markdown_processing.tag_batch import list_processed_batches
    batches = list_processed_batches(settings)
    if not batches:
        print('沒有新格式的 processed 批次，請先執行第二階段。')
        return None
    for index, batch in enumerate(batches, 1):
        print(f'{index}. {batch.name}')
    while True:
        value = input('選擇 processed 批次（0 返回）：').strip()
        if value == '0':
            return None
        if value.isascii() and value.isdigit() and 1 <= int(value) <= len(batches):
            return batches[int(value) - 1]
        print('請輸入有效批次編號，或 0 返回。')


def choose_pdf(settings: Settings, *, single: bool = False) -> list[Path]:
    if not settings.source_dir.is_dir():
        print("找不到 Financial Statements 資料夾。")
        return []
    files = sorted(
        (path for path in settings.source_dir.rglob("*.pdf") if path.is_file()),
        key=lambda path: path.relative_to(settings.source_dir).as_posix(),
    )
    if not files:
        print("Financial Statements 內沒有 PDF。")
        return []
    print("\n可用的財報清單：")
    for index, path in enumerate(files, 1):
        rel = path.relative_to(settings.source_dir).as_posix()
        print(f"{index}. {rel}")
    if not single:
        print("A. 全選（處理以上所有財報）")
    print("0. 返回")
    while True:
        value = input('選擇單一PDF編號（0 返回）：' if single else "請選擇編號（可單選、輸入逗號分隔多選，或輸入 A 全選）：").strip()
        if value == "0":
            return []
        if not single and value.lower() in ("a", "all", "全選"):
            return files
        parts = [p.strip() for p in re.split(r"[,，\s]+", value) if p.strip()]
        if parts and (not single or len(parts) == 1) and all(p.isdigit() and 1 <= int(p) <= len(files) for p in parts):
            indices = sorted(set(int(p) - 1 for p in parts))
            return [files[i] for i in indices]
        print('請輸入有效的單一編號，或0返回。' if single else "請輸入有效的編號（例如 1 或 1,2）、A 全選，或 0 返回。")


def choose_tagged_batch(settings):
    batches = list_tagged_batches(settings)
    if not batches:
        print('沒有可載入的tagged Financial批次。')
        return None
    print('\n可用tagged批次（本機切chunk，不呼叫API）：')
    for index, batch in enumerate(batches, 1):
        print(f'{index}. {batch.name}')
    while True:
        answer = input('選擇單一批次編號（0 返回）：').strip()
        if answer == '0':
            return None
        if answer.isascii() and answer.isdigit() and 1 <= int(answer) <= len(batches):
            return batches[int(answer)-1]
        print('請輸入有效編號，或0返回。')


def main() -> int:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="完整財報 RAG：本機 PDF 轉 Markdown")
    parser.add_argument("--pdf-parser", choices=("docling","inspector"), default=SETTINGS.pdf_parser)
    parser.add_argument("--check-env", action="store_true", help="檢查環境，不載入模型")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--pdf", type=Path, help="指定 Financial Statements 內的 PDF；省略時使用互動選單")
    mode.add_argument('--mark-headings', type=Path, help='只對既有 .md 補標記；也接受含 document.md 的資料夾')
    mode.add_argument('--process-batch', type=Path, help='raw批次本機補標題並清理頁碼')
    mode.add_argument('--tag-markdown', type=Path, help='舊版XML標籤相容入口；新格式請使用 --tag-batch')
    mode.add_argument('--tag-batch', type=Path, help='processed批次分類標題與區塊；不讀目錄、不產生大標')
    mode.add_argument('--chunk-batch', type=Path, help='tagged批次本機切chunk，輸出Markdown與JSON')
    parser.add_argument('--chunk-mode', choices=('original','parent_child'), default=SETTINGS.chunking.mode)
    parser.add_argument('--parent-limit', type=int, default=SETTINGS.chunking.parent_limit)
    parser.add_argument('--child-target', type=int, default=SETTINGS.chunking.child_target)
    parser.add_argument('--chunk-threshold', type=int, default=SETTINGS.chunking.recursive_threshold)
    parser.add_argument('--text-embedding-mode', choices=('body','description','full'), default=SETTINGS.chunking.text_embedding_mode)
    parser.add_argument('--table-embedding-mode', choices=('body','description','full'), default=SETTINGS.chunking.table_embedding_mode)
    parser.add_argument('--no-export', action='store_true', help='不寫實驗 Output')
    parser.add_argument("--ocr", action=argparse.BooleanOptionalAction, default=SETTINGS.ocr_enabled,
                        help="開啟按需 MinerU ch_lite OCR；--no-ocr 關閉，預設關閉")
    args = parser.parse_args()
    if args.no_export and all(value is None for value in (args.mark_headings, args.tag_markdown,
                                                         args.process_batch, args.tag_batch, args.chunk_batch)):
        parser.error('--no-export 請搭配Markdown／目錄／chunk處理入口')
    settings = replace(SETTINGS, pdf_parser=args.pdf_parser, ocr_enabled=args.ocr, chunking=replace(SETTINGS.chunking,
        mode=args.chunk_mode, parent_limit=args.parent_limit, child_target=args.child_target,
        recursive_threshold=args.chunk_threshold, text_embedding_mode=args.text_embedding_mode,
        table_embedding_mode=args.table_embedding_mode))
    try:
        if args.check_env:
            check_environment(settings)
            return 0
        if args.chunk_batch is not None:
            records = chunk_tagged_batch(args.chunk_batch, replace(settings, export_enabled=not args.no_export and settings.export_enabled))
            return 0 if all(r['status'] == 'chunked_needs_review' for r in records) else 1
        if args.process_batch is not None:
            records = process_raw_batch(args.process_batch, replace(settings, export_enabled=not args.no_export and settings.export_enabled))
            return 0 if all(r['status'] == 'processed_needs_review' for r in records) else 1
        if args.tag_batch is not None:
            records = tag_processed_batch(args.tag_batch, replace(settings, export_enabled=not args.no_export and settings.export_enabled))
            return 0 if all(r['status'] == 'tagged_needs_review'
                            for r in records) else 1
        if args.tag_markdown is not None:
            run_tag_markdown(args.tag_markdown, replace(settings,export_enabled=not args.no_export and settings.export_enabled))
            return 0
        if args.mark_headings is not None:
            run_mark_headings(args.mark_headings, replace(settings, export_enabled=not args.no_export and settings.export_enabled))
            return 0
        if args.pdf:
            record = run_markdown(args.pdf, settings)
            return 0 if record["status"] == "converted_needs_review" else 1
        while True:
            print(f"\n目前 OCR：{'開啟（按需）' if settings.ocr_enabled else '關閉'}")
            print("1. 完整 PDF 選頁轉 Markdown（本機）\n2. 切換 OCR 開關\n3. raw批次補標題與清理頁碼（本機）\n4. processed批次加註解標籤（本機）\n6. tagged批次切chunk（本機，輸出Markdown與JSON）\n0. 離開")
            action = input("選擇階段：").strip()
            if action == "0":
                return 0
            if action == "2":
                settings = replace(settings, ocr_enabled=not settings.ocr_enabled)
                continue
            if action == '3':
                batch = choose_raw_batch(settings)
                if batch is not None:
                    records = process_raw_batch(batch, settings)
                    print(f'第二階段完成：{sum(r["status"] == "processed_needs_review" for r in records)}/{len(records)} 份；仍需人工核對。')
                continue
            if action == '4':
                batch = choose_processed_batch(settings)
                if batch is not None:
                    records = tag_processed_batch(batch, settings)
                    normal = sum(r['status'] == 'tagged_needs_review' for r in records)
                    print(f'第三階段：正文標籤完成{normal}份、待確認{len(records)-normal}份；請核對同批 Record。')
                continue
            if action == '6':
                batch = choose_tagged_batch(settings)
                if batch is not None:
                    records = chunk_tagged_batch(batch, settings)
                    print(f'chunk完成：{sum(r["status"] == "chunked_needs_review" for r in records)}/{len(records)}份；詳見同批Record。')
                continue
            if action != "1":
                print("請輸入 1、2、3、4、6 或 0。")
                continue
            pdfs = choose_pdf(settings)
            if pdfs:
                total = len(pdfs)
                batch_dir = None
                if settings.export_enabled:
                    # EXPERIMENT_ONLY：一次選取共用一個批次，跨午夜不更換。
                    from functions.experiments.export_output import create_markdown_batch
                    batch_dir = create_markdown_batch(settings.markdown_output_dir)
                for idx, pdf in enumerate(pdfs, 1):
                    rel = pdf.relative_to(settings.source_dir).as_posix()
                    print(f"\n[{idx}/{total}] 開始處理：{rel}", flush=True)
                    record = run_markdown(pdf, settings, batch_dir=batch_dir)
                    if record.get("status") == "interrupted":
                        print("已中止後續批次轉換。")
                        break
    except (KeyboardInterrupt, EOFError):
        print("\n已離開。")
        return 130
    except Exception as error:
        print(f"執行失敗：{type(error).__name__}: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
