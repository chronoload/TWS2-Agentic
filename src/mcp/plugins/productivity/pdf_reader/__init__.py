import json
import logging
from pathlib import Path
from typing import Any, Dict

logger = logging.getLogger(__name__)

PDF_READER_SCHEMA = {
    "name": "pdf_reader",
    "description": "读取PDF文件，提取文本内容和元数据。支持指定页码范围。",
    "parameters": {
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "PDF文件路径",
            },
            "start_page": {
                "type": "integer",
                "description": "起始页码（从1开始），默认1",
            },
            "end_page": {
                "type": "integer",
                "description": "结束页码，默认最后一页",
            },
            "extract_metadata": {
                "type": "boolean",
                "description": "是否提取元数据，默认true",
            },
        },
        "required": ["path"],
    },
}


def _check_available() -> bool:
    try:
        import PyPDF2  # noqa: F401
        return True
    except ImportError:
        try:
            import pypdf  # noqa: F401
            return True
        except ImportError:
            try:
                import fitz  # noqa: F401
                return True
            except ImportError:
                return False


def _handle_pdf_reader(args: dict, **kw) -> str:
    path_str = (args.get("path") or "").strip()
    if not path_str:
        return json.dumps({"success": False, "error": "path is required"})

    pdf_path = Path(path_str).expanduser()
    if not pdf_path.exists():
        return json.dumps({"success": False, "error": f"File not found: {pdf_path}"})
    if not pdf_path.suffix.lower() == ".pdf":
        return json.dumps({"success": False, "error": f"Not a PDF file: {pdf_path}"})

    start_page = max(1, int(args.get("start_page", 1)))
    end_page = args.get("end_page")
    extract_meta = args.get("extract_metadata", True)

    try:
        try:
            from PyPDF2 import PdfReader
        except ImportError:
            try:
                from pypdf import PdfReader
            except ImportError:
                import fitz
                return _read_with_fitz(fitz, pdf_path, start_page, end_page, extract_meta)

        reader = PdfReader(str(pdf_path))
        total_pages = len(reader.pages)

        if end_page is None:
            end_page = total_pages
        else:
            end_page = min(int(end_page), total_pages)

        metadata = {}
        if extract_meta and reader.metadata:
            meta = reader.metadata
            metadata = {
                "title": meta.title or "",
                "author": meta.author or "",
                "subject": meta.subject or "",
                "creator": meta.creator or "",
                "producer": meta.producer or "",
                "creation_date": str(meta.creation_date) if meta.creation_date else "",
                "total_pages": total_pages,
            }

        pages = []
        for i in range(start_page - 1, end_page):
            try:
                text = reader.pages[i].extract_text() or ""
                pages.append({
                    "page": i + 1,
                    "text": text,
                })
            except Exception as exc:
                pages.append({
                    "page": i + 1,
                    "text": f"[Error extracting page: {exc}]",
                })

        return json.dumps({
            "success": True,
            "path": str(pdf_path),
            "metadata": metadata,
            "pages": pages,
            "page_range": [start_page, end_page],
        })

    except Exception as exc:
        return json.dumps({"success": False, "error": f"PDF read failed: {exc}"})


def _read_with_fitz(fitz, pdf_path, start_page, end_page, extract_meta):
    doc = fitz.open(str(pdf_path))
    total_pages = len(doc)

    if end_page is None:
        end_page = total_pages
    else:
        end_page = min(int(end_page), total_pages)

    metadata = {}
    if extract_meta:
        meta = doc.metadata
        metadata = {
            "title": meta.get("title", ""),
            "author": meta.get("author", ""),
            "subject": meta.get("subject", ""),
            "creator": meta.get("creator", ""),
            "total_pages": total_pages,
        }

    pages = []
    for i in range(start_page - 1, end_page):
        try:
            text = doc[i].get_text()
            pages.append({"page": i + 1, "text": text})
        except Exception as exc:
            pages.append({"page": i + 1, "text": f"[Error: {exc}]"})

    doc.close()
    return json.dumps({
        "success": True,
        "path": str(pdf_path),
        "metadata": metadata,
        "pages": pages,
        "page_range": [start_page, end_page],
    })


def register(ctx) -> None:
    ctx.register_tool(
        name="pdf_reader",
        toolset="pdf-reader",
        schema=PDF_READER_SCHEMA,
        handler=_handle_pdf_reader,
        check_fn=_check_available,
        emoji="📕",
    )
    logger.info("pdf-reader plugin registered")
