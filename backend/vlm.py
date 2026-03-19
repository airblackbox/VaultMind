"""
VaultMind VLM Layer — Phase 1
Qwen3-VL vision processing for scanned docs, photos, forms, handwriting.
All processing is local via Ollama. Nothing leaves the machine.
"""

import base64
import io
import json
import os
from pathlib import Path
from typing import Optional

import ollama
import pypdf

# Optional PDF-to-image conversion
try:
    from pdf2image import convert_from_bytes
    PDF2IMAGE_OK = True
except ImportError:
    PDF2IMAGE_OK = False
    print("⚠️  pdf2image not installed. Run: pip install pdf2image")
    print("   Also install poppler: brew install poppler")

VLM_MODEL = os.environ.get("VAULTMIND_VLM_MODEL", "qwen2.5vl:7b")

# ── VLM Prompts ────────────────────────────────────────────────

LEGAL_EXTRACTION_PROMPT = """You are a legal document analysis assistant.
Extract ALL content from this document image. Return ONLY valid JSON with this structure:
{
  "full_text": "all visible text verbatim",
  "document_type": "contract|pleading|correspondence|medical|financial|form|other",
  "dates": ["list of all dates found"],
  "parties": ["list of people, companies, or entities named"],
  "key_terms": ["important legal or financial terms"],
  "tables": [{"headers": [], "rows": [[]]}],
  "handwritten_notes": "any handwritten text transcribed",
  "amounts": ["any dollar amounts or numbers found"],
  "confidence": 0.95
}
If a field has no content, use an empty list [] or empty string "".
Return ONLY the JSON object, no other text."""

GENERAL_EXTRACTION_PROMPT = """Extract all text and information from this image.
Return ONLY valid JSON:
{
  "full_text": "all visible text",
  "document_type": "invoice|receipt|form|photo|diagram|screenshot|other",
  "dates": [],
  "key_info": ["important facts or data points"],
  "tables": [],
  "handwritten_notes": "",
  "confidence": 0.9
}
Return ONLY the JSON object."""

# ── VLM Check ──────────────────────────────────────────────────

def vlm_available() -> bool:
    """Check if a VLM model is available in Ollama."""
    try:
        models = ollama.list()
        pulled = [m.model for m in models.models]
        return any(VLM_MODEL in p for p in pulled)
    except Exception:
        return False

def get_available_vlm() -> Optional[str]:
    """Return the best available VLM model name."""
    try:
        models = ollama.list()
        pulled = [m.model for m in models.models]
        # Priority order matching spec
        candidates = [
            "qwen3-vl:8b",
            "qwen2.5vl:7b",
            "qwen2.5-vl:7b",
            "llava:13b",
            "llava:7b",
            "llava",
            "llama3.2-vision",
            "gemma3:4b",
        ]
        for candidate in candidates:
            if any(candidate in p for p in pulled):
                return candidate
        return None
    except Exception:
        return None

# ── Image → Base64 ─────────────────────────────────────────────

def image_to_base64(image_bytes: bytes) -> str:
    return base64.b64encode(image_bytes).decode("utf-8")

# ── VLM Extraction ─────────────────────────────────────────────

def extract_with_vlm(
    image_bytes: bytes,
    prompt: str = GENERAL_EXTRACTION_PROMPT,
    model: Optional[str] = None,
) -> dict:
    """Send an image to VLM and return parsed JSON extraction."""
    vlm = model or get_available_vlm()
    if not vlm:
        return {
            "full_text": "",
            "error": "No VLM model available. Run: ollama pull qwen2.5vl:7b",
            "confidence": 0.0,
        }

    try:
        image_b64 = image_to_base64(image_bytes)
        response = ollama.chat(
            model=vlm,
            messages=[{
                "role": "user",
                "content": prompt,
                "images": [image_b64],
            }],
            options={"temperature": 0.1},  # low temp for extraction accuracy
        )
        raw = response["message"]["content"].strip()

        # Strip markdown code fences if present
        if raw.startswith("```"):
            lines = raw.split("\n")
            raw = "\n".join(lines[1:-1]) if len(lines) > 2 else raw

        result = json.loads(raw)
        return result

    except json.JSONDecodeError as e:
        # VLM returned non-JSON — extract what we can
        print(f"⚠️  VLM returned non-JSON: {e}")
        return {
            "full_text": response["message"]["content"] if "response" in dir() else "",
            "document_type": "other",
            "dates": [],
            "parties": [],
            "key_terms": [],
            "tables": [],
            "handwritten_notes": "",
            "confidence": 0.5,
            "parse_error": str(e),
        }
    except Exception as e:
        print(f"❌ VLM extraction error: {e}")
        return {
            "full_text": "",
            "error": str(e),
            "confidence": 0.0,
        }

# ── PDF → VLM Pipeline ─────────────────────────────────────────

def extract_pdf_with_vlm(
    pdf_bytes: bytes,
    filename: str = "document.pdf",
    doc_type: str = "general",
    max_pages: int = 50,
) -> str:
    """
    Process a scanned PDF through VLM page by page.
    Returns combined extracted text ready for chunking + embedding.
    """
    prompt = LEGAL_EXTRACTION_PROMPT if doc_type == "legal" else GENERAL_EXTRACTION_PROMPT
    all_text_parts = [f"Document: {filename}\n"]

    if not PDF2IMAGE_OK:
        # Fallback: try pypdf text extraction first
        print(f"⚠️  pdf2image not available — trying pypdf text extraction for {filename}")
        try:
            reader = pypdf.PdfReader(io.BytesIO(pdf_bytes))
            text = "\n".join(page.extract_text() or "" for page in reader.pages)
            if text.strip():
                return f"Document: {filename}\n\n{text}"
        except Exception as e:
            print(f"pypdf fallback failed: {e}")
        return f"Document: {filename}\n[Could not extract text — install pdf2image for VLM processing]"

    try:
        print(f"📄 Converting PDF to images for VLM processing: {filename}")
        images = convert_from_bytes(pdf_bytes, dpi=200, fmt="jpeg")
        total = min(len(images), max_pages)
        print(f"   {total} pages to process")

        for i, img in enumerate(images[:max_pages]):
            print(f"   🔍 VLM processing page {i+1}/{total}...")
            # Convert PIL image to bytes
            img_buffer = io.BytesIO()
            img.save(img_buffer, format="JPEG", quality=85)
            img_bytes = img_buffer.getvalue()

            result = extract_with_vlm(img_bytes, prompt)

            # Build structured text for this page
            page_parts = [f"\n--- Page {i+1} ---"]

            if result.get("full_text"):
                page_parts.append(result["full_text"])

            if result.get("document_type") and i == 0:
                all_text_parts.insert(1, f"Document type: {result['document_type']}\n")

            if result.get("dates"):
                page_parts.append(f"Dates: {', '.join(result['dates'])}")

            if result.get("parties"):
                page_parts.append(f"Parties: {', '.join(result['parties'])}")

            if result.get("amounts"):
                page_parts.append(f"Amounts: {', '.join(result['amounts'])}")

            if result.get("key_terms"):
                page_parts.append(f"Key terms: {', '.join(result['key_terms'])}")

            if result.get("handwritten_notes"):
                page_parts.append(f"Handwritten notes: {result['handwritten_notes']}")

            if result.get("tables"):
                for table in result["tables"]:
                    if table.get("headers"):
                        page_parts.append(f"Table: {' | '.join(table['headers'])}")
                        for row in table.get("rows", []):
                            page_parts.append(" | ".join(str(c) for c in row))

            all_text_parts.append("\n".join(page_parts))

        return "\n".join(all_text_parts)

    except Exception as e:
        print(f"❌ PDF VLM pipeline error: {e}")
        return f"Document: {filename}\n[VLM processing failed: {e}]"


# ── Image File → Searchable Text ──────────────────────────────

def extract_image_with_vlm(
    image_bytes: bytes,
    filename: str,
    doc_type: str = "general",
) -> str:
    """Process a single image file through VLM. Returns searchable text."""
    prompt = LEGAL_EXTRACTION_PROMPT if doc_type == "legal" else GENERAL_EXTRACTION_PROMPT
    print(f"🔍 VLM processing image: {filename}")
    result = extract_with_vlm(image_bytes, prompt)

    parts = [f"Image: {filename}"]
    if result.get("document_type"):
        parts.append(f"Type: {result['document_type']}")
    if result.get("full_text"):
        parts.append(result["full_text"])
    if result.get("dates"):
        parts.append(f"Dates: {', '.join(result['dates'])}")
    if result.get("parties"):
        parts.append(f"Parties: {', '.join(result['parties'])}")
    if result.get("amounts"):
        parts.append(f"Amounts: {', '.join(result['amounts'])}")
    if result.get("key_terms"):
        parts.append(f"Key terms: {', '.join(result['key_terms'])}")
    if result.get("handwritten_notes"):
        parts.append(f"Handwritten: {result['handwritten_notes']}")

    return "\n".join(parts)
