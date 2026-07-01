"""Core modules for batch-file-epub: image processing, placeholder replacement, EPUB assembly."""
import re
import os
import shutil
import logging
import json
from collections import Counter
from pathlib import Path
from typing import Optional

from libs.config import SUPPORTED_INPUT_EXTS

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════
#  Placeholder substitution
# ═══════════════════════════════════════════

def replace_placeholders(text: str, mapping: dict) -> str:
    """Replace [key] placeholders in *text* with values from *mapping*."""
    def _replacer(match):
        key = match.group(1)
        return str(mapping.get(key, match.group(0)))
    return re.sub(r'\[(.*?)\]', _replacer, text)


# ═══════════════════════════════════════════
#  Image collection & conversion
# ═══════════════════════════════════════════

def collect_images(src_dir: Path, chapters: list[tuple[str, list[Path]]] | None = None) -> list[Path]:
    """Return a naturally-sorted list of all supported image files under *src_dir*.
    If *chapters* is provided, it will be populated with chapter info (name, image list)
    when subdirectories are detected."""
    files: list[Path] = []
    for f in sorted(src_dir.iterdir()):
        if f.is_file() and f.suffix.lower() in SUPPORTED_INPUT_EXTS:
            files.append(f)
        elif f.is_dir():
            sub_files = collect_images(f, chapters)
            if chapters is not None and sub_files:
                chapters.append((f.name, sub_files))
            files.extend(sub_files)
    files.sort(key=_natural_sort_key)
    return files


def detect_chapters(src_dir: Path) -> list[tuple[str, list[Path]]] | None:
    """Detect flat chapter structure from immediate subdirectories.
    Returns list of (chapter_name, [image_paths]) or None."""
    chapters: list[tuple[str, list[Path]]] = []
    for d in sorted(src_dir.iterdir()):
        if d.is_dir() and d.name not in ("__MACOSX", ".git"):
            imgs = [f for f in sorted(d.iterdir())
                    if f.is_file() and f.suffix.lower() in SUPPORTED_INPUT_EXTS]
            if imgs:
                imgs.sort(key=_natural_sort_key)
                chapters.append((d.name, imgs))
    return chapters if chapters else None


# Chapter tree: [("name", 5) | ("name", [subtree]), ...]
# Leaf = (str, int) — name + image_count
# Parent = (str, list) — name + children
ChapterTree = list[tuple[str, int | list]]


def detect_chapter_tree(src_dir: Path) -> ChapterTree | None:
    """Recursively detect nested chapter structure.
    Returns a tree of (name, image_count) leaves and (name, [children]) parents,
    or None for a flat directory.
    Loose images at the same level as subdirectories become a leading \"Front Matter\" section."""
    result: ChapterTree = []
    # Loose images at this level (not in subdirs)
    loose_imgs = [f for f in src_dir.iterdir()
                  if f.is_file() and f.suffix.lower() in SUPPORTED_INPUT_EXTS]
    has_subdirs = False
    for d in sorted(src_dir.iterdir()):
        if not d.is_dir() or d.name in ("__MACOSX", ".git"):
            continue
        direct_imgs = [f for f in d.iterdir()
                       if f.is_file() and f.suffix.lower() in SUPPORTED_INPUT_EXTS]
        sub_chapters = detect_chapter_tree(d)
        if sub_chapters:
            result.append((d.name, sub_chapters))
            has_subdirs = True
        elif direct_imgs:
            result.append((d.name, len(direct_imgs)))
            has_subdirs = True
    if has_subdirs and loose_imgs:
        # Prepend loose images as a front-matter section
        result.insert(0, ("Front Matter", len(loose_imgs)))
    return result if result else None


def count_tree_images(tree: ChapterTree) -> int:
    """Total image count across a chapter tree."""
    total = 0
    for _, val in tree:
        if isinstance(val, int):
            total += val
        else:
            total += count_tree_images(val)
    return total


def convert_and_copy_images(src_images: list[Path], dst_dir: Path,
                            normalize: bool = False,
                            ratio_tolerance: float = 0.03,
                            jpeg_quality: int = 92) -> int:
    """Copy/convert images to *dst_dir* as JPEG, named i-001.jpeg … i-NNN.jpeg.

    If *normalize* is True, images are first normalized to a consistent canvas
    size (majority-ratio images → average size; outliers → fitted within canvas).

    Returns number of images processed.
    """
    dst_dir.mkdir(parents=True, exist_ok=True)
    if normalize:
        _normalize_images(src_images, dst_dir, ratio_tolerance, jpeg_quality)
        return len(src_images)
    for idx, src in enumerate(src_images, start=1):
        page_n = f"{idx:03d}"
        dst = dst_dir / f"i-{page_n}.jpeg"
        _to_jpeg(src, dst)
    return len(src_images)


def _to_jpeg(src: Path, dst: Path) -> None:
    """Copy *src* to *dst* as .jpeg (keeps original encoding, iBooks handles it)."""
    shutil.copy2(src, dst)


# ═══════════════════════════════════════════
#  Image size normalization
# ═══════════════════════════════════════════

def _normalize_images(src_images: list[Path], dst_dir: Path,
                      ratio_tolerance: float = 0.03,
                      jpeg_quality: int = 92) -> None:
    """Normalize image sizes for consistent EPUB output.

    1. Scan all images for dimensions & aspect ratios (via imagesize).
    2. Find the dominant aspect ratio (most common, within *ratio_tolerance*).
    3. Majority-ratio images → resize all to the median dimensions.
    4. Aspect-ratio outliers → scale to fit within the canvas, centered (letterboxed).

    All output is JPEG (re-encoded when resized, copy+rename when unchanged).
    """
    import imagesize

    if not src_images:
        return

    # ── 1. Scan ──
    img_meta: list[dict] = []
    for src in src_images:
        w, h = imagesize.get(str(src))
        ratio = w / h
        img_meta.append({"src": src, "w": w, "h": h, "ratio": ratio})

    # ── 2. Find dominant ratio ──
    # Group ratios into buckets by tolerance
    ratio_buckets: dict[float, list[dict]] = {}
    for m in img_meta:
        bucket = round(m["ratio"] / ratio_tolerance) * ratio_tolerance
        ratio_buckets.setdefault(bucket, []).append(m)
    dominant_bucket = max(ratio_buckets, key=lambda k: len(ratio_buckets[k]))
    majority = ratio_buckets[dominant_bucket]
    outliers = [m for m in img_meta if round(m["ratio"] / ratio_tolerance) * ratio_tolerance != dominant_bucket]

    # ── 3. Calculate target canvas for majority ──
    # Use median of majority dimensions
    sorted_w = sorted(m["w"] for m in majority)
    sorted_h = sorted(m["h"] for m in majority)
    n = len(sorted_w)
    canvas_w = sorted_w[n // 2]
    canvas_h = sorted_h[n // 2]

    logger.info("Normalize: %d majority (%.4f) → %dx%d, %d outliers",
                len(majority), dominant_bucket, canvas_w, canvas_h, len(outliers))

    # ── 4. Process ──
    for idx, m in enumerate(img_meta, start=1):
        page_n = f"{idx:03d}"
        dst = dst_dir / f"i-{page_n}.jpeg"
        src = m["src"]
        w, h = m["w"], m["h"]
        is_outlier = m in outliers

        if not is_outlier and w == canvas_w and h == canvas_h:
            # Already perfect — 假转 (copy + rename, no re-encode)
            shutil.copy2(src, dst)
        elif not is_outlier:
            # Majority ratio but wrong size → resize to canvas
            _resize_to_fit(src, dst, canvas_w, canvas_h, jpeg_quality)
        else:
            # Outlier → scale to fit within canvas, center on white background
            _resize_to_fit_letterbox(src, dst, canvas_w, canvas_h, jpeg_quality)

    # ── 5. Write summary ──
    summary = {
        "total": len(img_meta),
        "majority_ratio": round(dominant_bucket, 4),
        "majority_count": len(majority),
        "outlier_count": len(outliers),
        "canvas": f"{canvas_w}x{canvas_h}",
        "outliers": [
            {"name": m["src"].name, "original": f"{m['w']}x{m['h']}",
             "ratio": round(m["ratio"], 4)}
            for m in outliers
        ],
    }
    summary_path = dst_dir / "_normalize_summary.json"
    summary_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False),
                            encoding="utf-8")
    logger.info("Normalization summary → %s", summary_path)


def _resize_to_fit(src: Path, dst: Path, tw: int, th: int, quality: int) -> None:
    """Resize *src* to exactly *tw*×*th*, preserving content via LANCZOS."""
    from PIL import Image
    img = Image.open(src).convert("RGB")
    img = img.resize((tw, th), Image.LANCZOS)
    img.save(dst, "JPEG", quality=quality)


def _resize_to_fit_letterbox(src: Path, dst: Path, canvas_w: int, canvas_h: int,
                              quality: int) -> None:
    """Scale *src* to fit within *canvas_w*×*canvas_h* (keep ratio), center on white."""
    from PIL import Image
    img = Image.open(src).convert("RGB")
    ow, oh = img.size
    scale = min(canvas_w / ow, canvas_h / oh)
    new_w = int(ow * scale)
    new_h = int(oh * scale)
    img_resized = img.resize((new_w, new_h), Image.LANCZOS)
    canvas = Image.new("RGB", (canvas_w, canvas_h), (255, 255, 255))
    x = (canvas_w - new_w) // 2
    y = (canvas_h - new_h) // 2
    canvas.paste(img_resized, (x, y))
    canvas.save(dst, "JPEG", quality=quality)


# ═══════════════════════════════════════════
#  Image dimensions
# ═══════════════════════════════════════════

def get_image_sizes(image_dir: Path) -> tuple[dict, int, int]:
    """Return ({index: (w,h)}, max_w, max_h) for JPEG images in *image_dir*."""
    import imagesize
    sizes: dict[int, tuple[int, int]] = {}
    all_sizes: list[tuple[int, int]] = []
    for f in sorted(image_dir.glob("i-*.jpeg")):
        idx = int(f.stem.split("-")[1])
        w, h = imagesize.get(str(f))
        sizes[idx] = (w, h)
        all_sizes.append((w, h))
    if not all_sizes:
        raise FileNotFoundError(f"No i-*.jpeg images found in {image_dir}")
    max_w = max(s[0] for s in all_sizes)
    max_h = max(s[1] for s in all_sizes)
    return sizes, max_w, max_h


# ═══════════════════════════════════════════
#  Page spread helpers
# ═══════════════════════════════════════════

_PAGE_SPREAD_RTL = ("right", "left")     # 1st page = right, 2nd = left  (manga)
_PAGE_SPREAD_LTR = ("left", "right")     # 1st page = left,  2nd = right (western)


def get_page_spread(page_index: int, rtl: bool = True) -> str:
    """Return 'left' or 'right' spread property for one-based *page_index*."""
    pair = _PAGE_SPREAD_RTL if rtl else _PAGE_SPREAD_LTR
    return pair[(page_index - 1) % 2]


def page_number_str(idx: int) -> str:
    """Zero-padded 3-digit page number string."""
    return f"{idx:03d}"


# ═══════════════════════════════════════════
#  Natural sort key
# ═══════════════════════════════════════════

def _natural_sort_key(path: Path) -> list[str]:
    """Natural sort key: zero-pad digit groups so they compare correctly.
    All elements are strings → no int/str comparison errors."""
    name = path.stem
    return [part.zfill(8) if part.isdigit() else part.casefold()
            for part in re.split(r"(\d+)", name) if part]
