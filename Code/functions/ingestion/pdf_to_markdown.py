"""
程式主要目的與功能：
本程式為財報 PDF 轉 Markdown 的核心轉換模組，負責：
1. 本機建立 Docling DocumentConverter，配置 CPU、PDFium 與可選擇開啟的 MinerU ch_lite OCR 辨識。
2. 完整轉換整份 PDF，保留原始 PDF 實體頁序標記（<!-- Page: 股票代號_年份_P頁序 -->）。
3. 自訂表格序列化器（TableWithFootnotes），保留 HTML 表格結構（rowspan/colspan）、表題與表下注。
4. 檢查缺頁、無文字頁面與跨頁元素，回傳 MarkdownDocument 記憶體物件供後續模組使用。

使用之外部套件與用途：
- docling / docling-core: 文件版面分析、表格結構識別與 Markdown/HTML 序列化。
- MinerU OCR 最小元件：本機 PP-OCRv5 det/rec（PyTorch）。
- pypdfium2: PDF 解析後端，支援跨平台檔案讀取與字元擷取。
- torch / torchvision: 提供 Docling 與 OCR 深度學習模型於 CPU 之張量運算推論支援。
"""

import hashlib
import os
import re
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path

from schemas import MarkdownDocument, MarkdownPage
from config.settings import Settings
from functions.ingestion.timings import wall_timer, capture_docling_timings


def source_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def conversion_versions() -> dict:
    result = {}
    for name in ("docling-slim", "docling-core", "docling-parse", "docling-ibm-models",
                 "torch", "torchvision", "pdf-inspector", "transformers", "pypdfium2", "PyYAML", "shapely", "pyclipper"):
        try:
            result[name] = version(name)
        except PackageNotFoundError:
            result[name] = None
    return result


def validate_source(pdf_path: Path, settings: Settings) -> Path:
    source = pdf_path.resolve()
    if not source.is_relative_to(settings.source_dir.resolve()) or source.suffix.lower() != ".pdf":
        raise ValueError("請選擇 Financial Statements 內的 PDF；參考來源不納入語料")
    if not source.is_file():
        raise FileNotFoundError(f"找不到 PDF：{source}")
    return source


def create_converter(settings: Settings):
    if settings.pdf_parser == 'inspector':
        from functions.ingestion.inspector_pdf import InspectorSession
        return InspectorSession(settings), {'engine':'pdf-inspector','version':'1.25.2','fallback':'docling_if_ocr_enabled'}
    if settings.pdf_parser != 'docling':
        raise ValueError('PDF解析器須為docling或inspector')
    # 首次只下載公開模型；PDF、文字及表格均在本機處理。
    cache = settings.docling_cache_dir
    os.environ["HF_HOME"] = str(cache / "huggingface")
    os.environ["HF_HUB_CACHE"] = str(cache / "huggingface" / "hub")
    os.environ["HF_HUB_DISABLE_TELEMETRY"] = "1"
    os.environ["HF_HUB_DISABLE_XET"] = "1"
    os.environ["HF_HUB_DISABLE_SYMLINKS_WARNING"] = "1"
    os.environ["TORCH_HOME"] = str(cache / "torch")
    from docling.datamodel.accelerator_options import AcceleratorDevice, AcceleratorOptions
    from config.devices import select_torch_device
    from docling.backend.pypdfium2_backend import PyPdfiumDocumentBackend
    from docling.datamodel.base_models import InputFormat
    from docling.datamodel.pipeline_options import PdfPipelineOptions, TableStructureOptions, TableFormerMode
    from docling.document_converter import DocumentConverter, PdfFormatOption
    from functions.integrations.docling_mineru_ocr import MineruOcrOptions, register_ocr
    from dataclasses import asdict
    register_ocr()

    device = select_torch_device(settings.compute_device)
    options = PdfPipelineOptions(
        enable_remote_services=False,
        allow_external_plugins=False,
        do_ocr=settings.ocr_enabled,
        do_table_structure=True,
        table_structure_options=TableStructureOptions(mode=TableFormerMode(settings.table_mode)),
        ocr_options=MineruOcrOptions(
            cache_dir=str(settings.ocr_cache_dir), parameters=asdict(settings.ocr),
            scale=settings.ocr.scale, cpu_threads=settings.pdf_cpu_threads, device=device.actual,
        ),
        accelerator_options=AcceleratorOptions(
            device=AcceleratorDevice.CUDA if device.actual == 'cuda' else AcceleratorDevice.CPU,
            num_threads=settings.pdf_cpu_threads,
        ),
        ocr_batch_size=settings.pdf_batch_size,
        layout_batch_size=settings.pdf_batch_size,
        table_batch_size=settings.pdf_batch_size,
        queue_max_size=settings.pdf_batch_size,
        generate_page_images=False,
        generate_picture_images=False,
        do_picture_description=False,
    )
    converter = DocumentConverter(
        allowed_formats=[InputFormat.PDF],
        format_options={InputFormat.PDF: PdfFormatOption(pipeline_options=options, backend=PyPdfiumDocumentBackend)},
    )
    return converter, options.model_dump(mode="json", serialize_as_any=True)


def serialize_document(document, page_count: int, table_format: str, *, selected_pages=None, pdf_identity=None) -> MarkdownDocument:
    """保留整份序列化結果，另外按 provenance 建立可定位的逐頁檢查版。

    跨頁項目依 Docling 的首個來源頁呈現，保留全部來源頁識別，不推測切割位置。
    """
    from docling_core.transforms.serializer.html import HTMLTableSerializer
    from docling_core.transforms.serializer.markdown import MarkdownDocSerializer, MarkdownParams, MarkdownTableSerializer
    from docling_core.transforms.serializer.common import create_ser_result
    from docling_core.types.doc import ContentLayer, DocItemLabel

    class TableWithFootnotes(HTMLTableSerializer if table_format == 'html' else MarkdownTableSerializer):
        """官方所選格式的表格序列化器外補上表題及表下注，避免轉換時遺失。"""

        def serialize(self, *, item, doc_serializer, doc, **kwargs):
            caption = doc_serializer.serialize_captions(item=item, **kwargs)
            labels = set(kwargs.get("labels", doc_serializer.params.labels)) - {DocItemLabel.CAPTION}
            table = super().serialize(item=item, doc_serializer=doc_serializer, doc=doc,
                                      **{**kwargs, "labels": labels})
            footnotes = doc_serializer.serialize_footnotes(item=item, **kwargs)
            return create_ser_result(text="\n\n".join(part.text for part in (caption, table, footnotes) if part.text),
                                     span_source=[caption, table, footnotes])

    if table_format not in {'html', 'markdown'}:
        raise ValueError("表格格式必須為html或markdown")
    if page_count < 1:
        raise ValueError("PDF 頁數必須大於零")
    expected = set(range(1, page_count + 1)) if selected_pages is None else set(selected_pages)
    if not expected or not expected <= set(range(1, page_count+1)):
        raise ValueError("選定頁序超出來源文件")
    actual = set(document.pages)
    if actual != expected:
        raise ValueError(f"Docling 頁序不完整：缺少 {sorted(expected - actual)}，額外 {sorted(actual - expected)}")
    # 保留頁首、頁尾等內容，避免依預設 BODY 篩選而默默遺失原始資料。
    params = MarkdownParams(layers=set(ContentLayer), traverse_pictures=True)
    def serialize(pages=None):
        page_params = params.model_copy(update={"pages": pages})
        return MarkdownDocSerializer(
            doc=document, params=page_params, table_serializer=TableWithFootnotes(),
        ).serialize().text

    raw = serialize()
    refs: dict[int, list[str]] = {page: [] for page in expected}
    cross: dict[int, list[str]] = {page: [] for page in expected}
    warnings = []
    for item, _ in document.iterate_items(included_content_layers=set(ContentLayer), traverse_pictures=True):
        if table_format == 'markdown' and any(
                getattr(cell, 'row_span', 1) > 1 or getattr(cell, 'col_span', 1) > 1
                for cell in getattr(getattr(item, 'data', None), 'table_cells', ())):
            warnings.append(f'表格 {item.self_ref} 含合併儲存格；管線表格已依Docling規則展平，請核對原PDF欄列關係')
        provenance = getattr(item, "prov", ())
        source_pages = {prov.page_no for prov in provenance}
        if source_pages - expected:
            raise ValueError(f"項目 {item.self_ref} 的 provenance 超出原始 PDF 頁序")
        if not source_pages:
            warnings.append(f"項目 {item.self_ref} 無來源頁序；請從 raw.md 與原始結構核對")
        for page in source_pages:
            refs[page].append(item.self_ref)
            if len(source_pages) > 1:
                cross[page].append(item.self_ref)
    pages = []
    marked = []
    for number in sorted(expected):
        text = serialize({number})
        # 圖片／HTML 標記不能當成文字擷取成功。
        visible = re.sub(r"<!--.*?-->|<[^>]*>", "", text, flags=re.DOTALL).strip()
        status = "text_extracted" if visible else "no_text_extracted"
        if not visible:
            warnings.append(f"PDF 第 {number} 頁未擷取到文字；可能是空白、圖片或 OCR 未辨識，需人工核對")
        page = MarkdownPage(number, text, status, tuple(dict.fromkeys(refs[number])),
                            tuple(dict.fromkeys(cross[number])))
        pages.append(page)
        from functions.markdown_processing.page_markers import format_page_marker
        marker = format_page_marker(number, pdf_identity) + '\n'
        if cross[number]:
            marker += "<!-- CROSS_PAGE_ITEMS: " + ", ".join(page.cross_page_item_refs) + " -->\n"
        if not visible:
            marker += "<!-- NO_TEXT_EXTRACTED: 請核對原 PDF，本頁不視為文字辨識成功 -->\n"
        marked.append(marker + "\n" + text + "\n")
    if any(cross.values()):
        warnings.append("跨頁項目完整呈現在首個來源頁，其他來源頁保留其識別碼；不得視為精確的逐頁文字切割，請核對 raw.md 及原 PDF")
    return MarkdownDocument(raw, "\n".join(marked), tuple(pages), tuple(dict.fromkeys(warnings)), document)


def convert_pdf(pdf_path: Path, page_count: int, settings: Settings, runtime: dict,
                progress_callback=None, *, page_range=None, converter_bundle=None) -> MarkdownDocument:
    """轉換指定原 PDF 頁段；部分成功或錯誤不得視為完整轉換。"""
    if settings.pdf_parser == 'inspector':
        if converter_bundle is None:
            converter_bundle = create_converter(settings)
        return converter_bundle[0].convert(pdf_path, page_count, runtime, progress_callback, page_range=page_range)
    runtime["stage"] = "initialize_docling"
    if converter_bundle is None:
        with wall_timer(runtime, 'converter_setup'):
            converter_bundle = create_converter(settings)
    converter, pipeline_options = converter_bundle
    from docling.datamodel.base_models import ConversionStatus
    runtime["pipeline_options"] = pipeline_options
    runtime["stage"] = "convert_pdf"
    from functions.integrations.docling_mineru_ocr import collect_diagnostics
    from docling.datamodel.settings import settings as docling_settings
    from docling.datamodel.base_models import InputFormat
    previous_profile = docling_settings.debug.profile_pipeline_timings
    docling_settings.debug.profile_pipeline_timings = True
    result = None
    try:
        if not converter.initialized_pipelines:
            with wall_timer(runtime, 'pipeline_model_load'):
                converter.initialize_pipeline(InputFormat.PDF)
        options = {'page_range': page_range} if page_range is not None else {}
        with wall_timer(runtime, 'docling_conversion'):
            result = converter.convert(pdf_path, raises_on_error=False, progress_callback=progress_callback, **options)
    finally:
        if result is not None:
            capture_docling_timings(runtime, result)
        docling_settings.debug.profile_pipeline_timings = previous_profile
        prior = runtime.get("ocr_diagnostics", [])
        current = collect_diagnostics(converter)
        runtime["ocr_diagnostics"] = list({item['pdf_page']: item for item in [*prior, *current]}.values())
    runtime["docling_status"] = result.status.value
    runtime["docling_errors"] = [error.model_dump(mode="json") for error in result.errors]
    if result.status != ConversionStatus.SUCCESS:
        raise RuntimeError(f"Docling 狀態為 {result.status.value}；未完成整份轉換，請查看執行紀錄")
    runtime["stage"] = "serialize_markdown"
    from functions.markdown_processing.file_identity import source_identity
    with wall_timer(runtime, 'markdown_output'):
        return serialize_document(result.document, page_count, settings.table_format,
                                  selected_pages=range(page_range[0], page_range[1] + 1) if page_range else None,
                                  pdf_identity=source_identity(pdf_path))
