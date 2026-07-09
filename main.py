#!/usr/bin/env python3
"""batch-file-epub — Build a fixed-layout EPUB3 for Apple Books from a folder of images.

Usage (CLI):
    python main.py --src ./my-manga/ --dst ./output/ \\
        --title "My Manga Vol.1" --author "Author" --lang zh

Usage (agent / import):
    from main import build_epub
    build_epub(src="...", dst="...", title="...", author="...", lang="...")
"""
from __future__ import annotations

import argparse
import logging
import shutil
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

from libs.config import (
    ITEMS_1_TEMP, ITEMS_2_TEMP, ITEMREF_TEMP, TEMPLATE_DIR,
)
from libs.modules import (
    collect_images, convert_and_copy_images, detect_chapters,
    detect_chapter_tree, count_tree_images, ChapterTree,
    get_image_sizes, get_page_spread, page_number_str, replace_placeholders,
)

logger = logging.getLogger("batch-file-epub")


# ═══════════════════════════════════════════
#  EPUB builder
# ═══════════════════════════════════════════

def build_epub(
    src: str | Path,
    dst: str | Path,
    title: str,
    author: str = "",
    publisher: str = "",
    lang: str = "ja",
    rtl: bool = True,
    no_chapters: bool = False,
    chapters: dict[str, int] | None = None,
    normalize: bool = True,
    encode_quality: int = 85,
) -> Path:
    """Build a fixed-layout EPUB3 from images in *src* and write to *dst*.

    Parameters
    ----------
    src : str | Path
        Directory containing images (jpg, png, webp, bmp, gif, tiff).
        Subdirectories are auto-detected as chapters.
    dst : str | Path
        Output directory where the unpacked EPUB structure will be written.
    title : str
        Book title (required).
    author : str
        Creator / author.
    publisher : str
        Publisher name.
    lang : str
        Language code (e.g. ``ja``, ``zh``, ``en``).  Default ``ja``.
    rtl : bool
        Right-to-left page progression (manga).  Default ``True``.
    chapters : dict | None
        Explicit chapter map: ``{"Name": start_page, ...}``.  Overrides auto-detection.
    no_chapters : bool
        Disable auto-detection of chapters from subdirectories.
    normalize : bool
        Normalize all images to a common canvas (median dimensions) with
        aspect-ratio-preserving letterboxing.  Eliminates blank space from
        inconsistent image sizes.
    encode_quality : int
        Quality for resized images (1-100).  Lower = smaller files.  Preserves source format.

    Returns
    -------
    Path
        The *dst* directory containing the unpacked EPUB.
    """
    src = Path(src).resolve()
    dst = Path(dst).resolve()
    if not src.is_dir():
        raise NotADirectoryError(f"Source is not a directory: {src}")

    # ── 0. Determine chapters ──
    chapter_ranges: list[tuple[str, int]] = []  # (name, start_page_1based)
    chapter_tree: ChapterTree | None = None
    if not no_chapters:
        if chapters:
            # Option B: explicit JSON-style chapter map
            chapter_ranges = sorted(chapters.items(), key=lambda kv: kv[1])
            logger.info("Chapters (explicit): %d", len(chapter_ranges))
        else:
            # Option A: auto-detect — try tree first, fall back to flat
            chapter_tree = detect_chapter_tree(src)
            if chapter_tree:
                tree_total = count_tree_images(chapter_tree)
                logger.info("Chapters (tree): %d images across nested structure", tree_total)

    logger.info("Building EPUB → %s", dst)

    # ── 1. Collect & convert images ──
    images = collect_images(src)
    image_dst = dst / "item" / "image"
    total = convert_and_copy_images(images, image_dst, normalize=normalize, encode_quality=encode_quality)
    page_sizes, max_w, max_h = get_image_sizes(image_dst)
    logger.info("Images: %d  max size: %dx%d", total, max_w, max_h)

    # ── 2. Load templates ──
    templates = _load_templates()

    # ── 3. Write static files ──
    _write_static_files(dst, templates)

    # ── 4. Write per-page XHTML ──
    _write_pages(dst, templates, total, page_sizes, max_w, max_h)

    # ── 5. Write OPF ──
    _write_opf(dst, templates, title, author, publisher, lang, rtl, total, max_w, max_h)

    # ── 6. Write nav.xhtml ──
    _write_nav(dst, templates, title, chapter_ranges, chapter_tree)

    logger.info("EPUB structure written to %s", dst)
    return dst


def pack_epub(src_dir: str | Path, output_epub: str | Path,
               compress: bool = False) -> Path:
    """Zip *src_dir* into an .epub file at *output_epub*.
    If *compress* is False (default), files are stored without compression
    for fastest packing. Set to True for smaller output."""
    import zipfile
    src_dir = Path(src_dir).resolve()
    output_epub = Path(output_epub).resolve()
    output_epub.parent.mkdir(parents=True, exist_ok=True)

    if compress:
        compress_all = zipfile.ZIP_DEFLATED
        compress_img = zipfile.ZIP_STORED
    else:
        # Pure container — no compression, 1:1 file sizes
        compress_all = zipfile.ZIP_STORED
        compress_img = zipfile.ZIP_STORED

    # Determine the default compression for ZipFile (used only for files
    # where zf.write() is called without an explicit compress_type).
    default_compress = compress_all

    with zipfile.ZipFile(output_epub, "w", default_compress) as zf:
        # mimetype must be first, uncompressed
        mimetype = src_dir / "mimetype"
        if mimetype.exists():
            zf.write(mimetype, "mimetype", zipfile.ZIP_STORED)
        for f in sorted(src_dir.rglob("*")):
            if f.is_file() and f.name != "mimetype":
                # ⚠  Skip the output .epub itself — it lives inside src_dir
                #    and would otherwise be recursively included on re-runs,
                #    causing exponential size bloat.
                if f.resolve() == output_epub:
                    continue
                arcname = f.relative_to(src_dir).as_posix()
                # Images are already compressed — store as-is
                if f.parent.name == "image" and f.suffix.lower() in (".jpeg", ".jpg", ".png", ".webp"):
                    zf.write(f, arcname, compress_img)
                else:
                    zf.write(f, arcname, compress_all)
    logger.info("Packed → %s", output_epub)
    return output_epub


# ═══════════════════════════════════════════
#  Internal helpers
# ═══════════════════════════════════════════

def _xml_escape(text: str) -> str:
    """Escape &, <, > for XML text content."""
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _parse_chapters(raw: str) -> dict[str, int]:
    """Parse --chapters argument: inline JSON string or path to .json file."""
    import json
    raw = raw.strip()
    # Try as file path first
    path = Path(raw)
    if path.suffix == ".json" and path.exists():
        data = json.loads(path.read_text(encoding="utf-8"))
    else:
        data = json.loads(raw)
    if not isinstance(data, dict):
        raise ValueError("--chapters must be a JSON object: {\"Name\": page, ...}")
    # Validate: all keys are strings, all values are positive ints
    result: dict[str, int] = {}
    for k, v in data.items():
        if not isinstance(v, int) or v < 1:
            raise ValueError(f"Chapter '{k}' page must be a positive integer, got {v!r}")
        result[str(k)] = v
    return result

def _load_templates() -> dict[str, str]:
    """Read all template files into a dict keyed by relative path."""
    templates: dict[str, str] = {}
    for f in TEMPLATE_DIR.rglob("*"):
        if f.is_file():
            rel = f.relative_to(TEMPLATE_DIR).as_posix()
            templates[rel] = f.read_text(encoding="utf-8")
    return templates


def _write_static_files(dst: Path, tpl: dict[str, str]) -> None:
    """Copy template files that don't need placeholder substitution."""
    for rel, content in tpl.items():
        if rel.startswith("item/xhtml/") or rel == "item/standard.opf" or rel == "item/nav.xhtml":
            continue  # handled separately
        out = dst / rel
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(content, encoding="utf-8")


def _write_pages(
    dst: Path,
    tpl: dict[str, str],
    total: int,
    page_sizes: dict[int, tuple[int, int]],
    max_w: int,
    max_h: int,
) -> None:
    section_tpl = tpl.get("item/xhtml/pages.xhtml", "")
    xhtml_dir = dst / "item" / "xhtml"
    xhtml_dir.mkdir(parents=True, exist_ok=True)

    # Cover page (image 001) — use its own dimensions so it fills the page
    cover_w, cover_h = page_sizes.get(1, (max_w, max_h))
    cover_html = replace_placeholders(section_tpl, {
        "width": str(cover_w), "height": str(cover_h),
        "width_this": str(cover_w), "height_this": str(cover_h),
        "page_n": "001", "page": "cover",
    })
    (xhtml_dir / "p-cover.xhtml").write_text(cover_html, encoding="utf-8")

    # Content pages — each page uses its own image dimensions as viewport,
    # so the image fills the entire screen without blank space.
    for idx in range(1, total + 1):
        page_n = page_number_str(idx)
        w, h = page_sizes.get(idx, (max_w, max_h))
        html = replace_placeholders(section_tpl, {
            "width": str(w), "height": str(h),
            "width_this": str(w), "height_this": str(h),
            "page_n": page_n, "page": str(idx),
        })
        (xhtml_dir / f"p-{page_n}.xhtml").write_text(html, encoding="utf-8")


def _write_opf(
    dst: Path,
    tpl: dict[str, str],
    title: str,
    author: str,
    publisher: str,
    lang: str,
    rtl: bool,
    total: int,
    max_w: int,
    max_h: int,
) -> None:
    opf_tpl = tpl.get("item/standard.opf", "")
    progression = "rtl" if rtl else "ltr"

    items1_parts, items2_parts, itemref_parts = [], [], []
    for idx in range(1, total + 1):
        pn = page_number_str(idx)
        spr = get_page_spread(idx, rtl=rtl)
        items1_parts.append(replace_placeholders(ITEMS_1_TEMP, {"page_n": pn}))
        items2_parts.append(replace_placeholders(ITEMS_2_TEMP, {"page_n": pn}))
        itemref_parts.append(replace_placeholders(ITEMREF_TEMP, {"page_n": pn, "spr": spr}))

    book_uuid = str(uuid.uuid4())
    now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    content = replace_placeholders(opf_tpl, {
        "title": title,
        "creator": author,
        "publisher": publisher,
        "language": lang,
        "lang": lang,
        "width": str(max_w),
        "height": str(max_h),
        "items1": "\n    ".join(items1_parts),
        "items2": "\n    ".join(items2_parts),
        "itemref": "\n    ".join(itemref_parts),
    })
    # Fix page-progression-direction
    content = content.replace('page-progression-direction="rtl"', f'page-progression-direction="{progression}"')
    # Replace hardcoded identifier and date
    content = content.replace(">000000<", f">{book_uuid}<", 1)
    content = content.replace('property="dcterms:modified">2025-05-06T18:51:17Z<', f'property="dcterms:modified">{now_iso}<')

    (dst / "item" / "standard.opf").write_text(content, encoding="utf-8")


def _write_nav(dst: Path, tpl: dict[str, str], title: str,
               chapters: list[tuple[str, int]],
               chapter_tree: ChapterTree | None = None) -> None:
    """Write nav.xhtml with optional chapter TOC entries (flat or nested)."""
    if not chapters and not chapter_tree:
        nav = replace_placeholders(tpl.get("item/nav.xhtml", ""), {"title": title})
        (dst / "item" / "nav.xhtml").write_text(nav, encoding="utf-8")
        return

    # Build TOC items — use tree if available, else flat list
    toc_ol: str
    if chapter_tree:
        toc_ol = _build_nested_toc(chapter_tree, offset=1)
    else:
        toc_items = []
        for ch_name, start_page in chapters:
            pn = page_number_str(start_page)
            toc_items.append(
                f'      <li><a href="xhtml/p-{pn}.xhtml">{_xml_escape(ch_name)}</a></li>'
            )
        toc_ol = "\n".join(toc_items)

    nav = f'''<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE html>
<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops" xml:lang="ja">
<head><meta charset="UTF-8"/><title>{_xml_escape(title)}</title></head>
<body>
  <nav epub:type="toc" id="toc">
    <h1>{_xml_escape(title)}</h1>
    <ol>
{toc_ol}
    </ol>
  </nav>
</body>
</html>
'''
    (dst / "item" / "nav.xhtml").write_text(nav, encoding="utf-8")


def _build_nested_toc(tree: ChapterTree, offset: int) -> str:
    """Recursively build nested <ol> from a chapter tree, computing page offsets."""
    items: list[str] = []
    current_offset = offset
    for name, val in tree:
        pn = page_number_str(current_offset)
        if isinstance(val, int):
            # Leaf: direct images
            items.append(
                f'        <li><a href="xhtml/p-{pn}.xhtml">{_xml_escape(name)}</a></li>'
            )
            current_offset += val
        else:
            # Parent: nested chapters
            sub_ol = _build_nested_toc(val, current_offset)
            items.append(
                f'        <li><a href="xhtml/p-{pn}.xhtml">{_xml_escape(name)}</a>\n'
                f'          <ol>\n{sub_ol}\n          </ol>\n'
                f'        </li>'
            )
            current_offset += count_tree_images(val)
    return "\n".join(items)


# ═══════════════════════════════════════════
#  CLI
# ═══════════════════════════════════════════

def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(
        description="Build a fixed-layout EPUB3 for Apple Books from images.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python main.py --src ./images/ --dst ./out/ --title "My Manga" --author Me
  python main.py --src ./images/ --dst ./out/ --title "Webtoon" --ltr --lang ko
  python main.py --src ./images/ --dst ./out/ --title "Manga" --author Me --pack ./out.epub
""",
    )
    ap.add_argument("--src", required=True, help="Source image directory")
    ap.add_argument("--dst", required=True, help="Output directory for unpacked EPUB")
    ap.add_argument("--title", required=True, help="Book title")
    ap.add_argument("--author", default="", help="Author / creator")
    ap.add_argument("--publisher", default="", help="Publisher")
    ap.add_argument("--lang", default="ja", help="Language code (default: ja)")
    ap.add_argument("--rtl", dest="rtl", action="store_true", default=True,
                    help="Right-to-left page progression (manga, default)")
    ap.add_argument("--ltr", dest="rtl", action="store_false",
                    help="Left-to-right page progression (western comics, webtoons)")
    ap.add_argument("--pack", default=None, const="__AUTO__", nargs="?", metavar="PATH",
                    help="Zip --dst into an .epub. Defaults to <dst>.epub if no PATH given")
    ap.add_argument("--compress", action="store_true", default=False,
                    help="Enable ZIP deflate compression (smaller file, slower packing)")
    ap.add_argument("--no-chapters", action="store_true",
                    help="Disable auto-detection of chapters from subdirectories")
    ap.add_argument("--chapters", default=None, metavar="JSON",
                    help='Chapter map as JSON: \'{"第1话":1,"第2话":25}\' or path to a .json file')
    ap.add_argument("--no-normalize", action="store_false", dest="normalize", default=True,
                    help="Skip image normalization (keep original sizes)")
    ap.add_argument("--jpg-quality", type=int, dest="quality", default=85, metavar="1-100",
                    help="Quality for resized images (default: 85, lower = smaller file). Preserves source format.")
    ap.add_argument("--quiet", action="store_true", help="Suppress info logs")
    args = ap.parse_args(argv)

    logging.basicConfig(
        level=logging.WARNING if args.quiet else logging.INFO,
        format="%(levelname)s: %(message)s",
    )

    # Parse --chapters (inline JSON or .json file path)
    chapters_dict = None
    if args.chapters:
        chapters_dict = _parse_chapters(args.chapters)

    out_dir = build_epub(
        src=args.src, dst=args.dst,
        title=args.title, author=args.author,
        publisher=args.publisher, lang=args.lang,
        rtl=args.rtl,
        no_chapters=args.no_chapters,
        chapters=chapters_dict,
        normalize=args.normalize,
        encode_quality=args.quality,
    )
    if args.pack:
        pack_stem = args.pack if args.pack != "__AUTO__" else Path(args.dst).name.rstrip("/\\")
        pack_path = str(Path(args.dst).resolve() / f"{pack_stem}.epub")
        pack_epub(out_dir, pack_path, compress=args.compress)
        print(pack_path)


if __name__ == "__main__":
    main()
