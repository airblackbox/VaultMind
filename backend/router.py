"""
VaultMind Model Router — Phase 1
Routes incoming files and queries to the right model:
  VLM  → scanned PDFs, images, forms, handwriting
  SLM  → text queries, RAG, summarization
  LAM  → agentic commands (Phase 3)
"""

import os
from enum import Enum
from pathlib import Path

# ── Route Types ────────────────────────────────────────────────

class RouteType(str, Enum):
    VLM   = "vlm"    # Vision-Language Model — image/scan processing
    SLM   = "slm"    # Small Language Model  — text RAG + reasoning
    LAM   = "lam"    # Large Action Model    — agentic task execution

# ── File Extension Maps ────────────────────────────────────────

IMAGE_EXTENSIONS = {
    ".jpg", ".jpeg", ".png", ".gif",
    ".bmp", ".webp", ".heic", ".tiff", ".tif"
}

TEXT_EXTENSIONS = {
    ".pdf", ".docx", ".txt", ".md",
    ".csv", ".xml", ".zip"
}

# Action keywords that trigger LAM routing
LAM_TRIGGERS = [
    "prepare for", "create a document", "draft a", "schedule",
    "move file", "tag", "summarize and file", "extract dates",
    "log time", "check conflicts", "send email", "calendar",
    "organize", "file this", "create task",
]

# ── Scanned PDF Detection ──────────────────────────────────────

def is_scanned_pdf(pdf_bytes: bytes, text_threshold: int = 100) -> bool:
    """
    Returns True if the PDF is image-heavy (scanned) vs text-based.
    Scanned PDFs have little/no extractable text — need VLM processing.
    """
    try:
        import io
        import pypdf
        reader = pypdf.PdfReader(io.BytesIO(pdf_bytes))
        total_text = ""
        for page in reader.pages[:5]:  # check first 5 pages
            total_text += page.extract_text() or ""
        return len(total_text.strip()) < text_threshold
    except Exception:
        return False  # assume text-based if we can't check

# ── Main Router ────────────────────────────────────────────────

def route_file(filename: str, file_bytes: bytes) -> RouteType:
    """
    Determine which model pipeline should handle this file.

    Logic:
    - Images → always VLM
    - PDFs   → VLM if scanned, SLM if text-based
    - Other  → SLM (text extraction)
    """
    ext = Path(filename).suffix.lower()

    # Images always go to VLM
    if ext in IMAGE_EXTENSIONS:
        return RouteType.VLM

    # PDFs: check if scanned or text-based
    if ext == ".pdf":
        if is_scanned_pdf(file_bytes):
            return RouteType.VLM
        return RouteType.SLM

    # Everything else is text-based
    return RouteType.SLM


def route_query(query: str) -> RouteType:
    """
    Determine whether a user query is a RAG search or an action command.

    - Action commands → LAM (Phase 3)
    - Everything else → SLM
    """
    q_lower = query.lower()
    for trigger in LAM_TRIGGERS:
        if trigger in q_lower:
            return RouteType.LAM
    return RouteType.SLM


def describe_route(route: RouteType, filename: str = "") -> str:
    """Human-readable description of why a file was routed this way."""
    if route == RouteType.VLM:
        ext = Path(filename).suffix.lower() if filename else ""
        if ext in IMAGE_EXTENSIONS:
            return f"Image file ({ext}) → VLM vision processing"
        return "Scanned PDF (minimal extractable text) → VLM vision processing"
    elif route == RouteType.LAM:
        return "Action command detected → LAM agent mode"
    else:
        return "Text-based document → SLM text extraction + RAG"
