"""Constants and templates for batch-file-epub.
User-facing parameters are passed via CLI or function arguments — not hardcoded here.
"""
from pathlib import Path

# ── EPUB template paths (relative to project root) ──
TEMPLATE_DIR = Path(__file__).resolve().parent.parent / "epubtemplates"

# ── OPF spine itemref template ──
ITEMS_1_TEMP = r'<item id="i-[page_n]" href="image/i-[page_n].jpeg" media-type="image/jpeg"/>'
ITEMS_2_TEMP = r'<item media-type="application/xhtml+xml" id="p-[page_n]" href="xhtml/p-[page_n].xhtml" properties="svg" fallback="i-[page_n]"/>'
ITEMREF_TEMP = r'<itemref idref="p-[page_n]" linear="yes" properties="page-spread-[spr]"/>'

# ── Supported input image extensions ──
SUPPORTED_INPUT_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".gif", ".tiff", ".tif"}
