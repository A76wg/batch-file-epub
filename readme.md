# batch-file-epub

Convert a folder of manga/comic images into a fixed-layout EPUB3 optimized for Apple Books (iBooks).

## Features

- **Fixed-layout EPUB3** — pixel-perfect image rendering with SVG-wrapped pages
- 電書協 CSS templates for full iBooks compatibility
- **Chapter TOC** — flat or nested, auto-detected from subdirectories or explicit JSON
- **RTL / LTR** page progression (manga vs western comics)
- **CLI + Python API** — shell-friendly and agent-importable

## Requirements

- Python 3.9+
- imagesize

```bash
pip install imagesize
```

## Usage

### CLI

```bash
# Basic conversion with auto-pack
python main.py --src ./images/ --dst ./out/ --title "My Manga" --lang zh --pack

# --pack defaults to <dst>.epub if no path given
python main.py --src ./images/ --dst ./out/ --title "My Manga" --lang zh --pack

# Explicit pack path
python main.py --src ./images/ --dst ./out/ --title "My Manga" --lang zh --pack ./manga.epub

# With chapters (JSON)
python main.py --src ./images/ --dst ./out/ --title "My Manga" --lang zh \
    --chapters '{"Ch.1":1,"Ch.2":25}' --pack

# Chapters from a JSON file
python main.py --src ./images/ --dst ./out/ --title "My Manga" --lang zh \
    --chapters chapters.json --pack

# Auto-detect chapters from folder structure (flat or nested)
python main.py --src ./images/ --dst ./out/ --title "My Manga" --lang zh --pack

# Left-to-right (western comics / webtoons)
python main.py --src ./images/ --dst ./out/ --title "Webtoon" --lang ko --ltr --pack

### Python API

```python
from main import build_epub, pack_epub

out = build_epub(
    src="/path/to/images",
    dst="/tmp/epub-out",
    title="My Manga",
    lang="zh",
pack_epub(out, "/path/to/output.epub")
```

## CLI Reference

| Flag | Default | Description |
|------|---------|-------------|
| `--src` | (required) | Source image directory |
| `--dst` | (required) | Output directory (unpacked EPUB) |
| `--title` | (required) | Book title |
| `--author` | `""` | Author / creator |
| `--publisher` | `""` | Publisher |
| `--lang` | `ja` | Language code |
| `--rtl` | on | Right-to-left (manga) |
| `--ltr` | — | Left-to-right (western) |
| `--chapters` | — | JSON string or .json file path |
| `--normalize` | — | Normalize image sizes to consistent canvas |
| `--quality` | `85` | Encoding quality 1-100, only for resized images |

## Normalization (`--normalize`)

When enabled, images are scanned with `imagesize` and normalized to a consistent canvas:

1. **Detect dominant aspect ratio** — groups images with similar ratios (±3% tolerance)
2. **Majority images** → resize to median dimensions (already-correct images are copied as-is)
3. **Outliers** → scale to fit within canvas, centered with white letterbox

Resized images **keep their original format** (webp→webp, jpg→jpg).

```bash
# Normalize with default quality (85)
python main.py --src ./images/ --dst ./out/ --title "Manga" --lang zh --normalize --pack

# Lower quality = smaller output
python main.py --src ./images/ --dst ./out/ --title "Manga" --lang zh --normalize --quality 70 --pack
```

Without `--normalize`, images are copied as-is with renamed extensions — no re-encoding, no size change.

## Supported Input Formats

jpg, jpeg, png, webp, bmp, gif, tiff. Images are naturally sorted by filename (1 < 2 < 10 < 20) and copied as-is (extension renamed to .jpeg, no re-encoding).

## Chapter TOC

Chapters are detected in order of priority:

1. **`--chapters`** — Explicit JSON map or `.json` file
2. **Auto-detect from folders** — Subdirectories become chapters:
   - **Flat**: `src/Ch01/*.png` → single-level TOC
   - **Nested**: `src/Vol.1/Ch01/*.png` → hierarchical TOC
   - **Mixed**: loose images at root level become a "Front Matter" section
3. **`--no-chapters`** — Skip TOC entirely

## CSS Templates

Originate from 電書協 EPUB 3 制作ガイド (ver.1.1.1) by the Japan Electronic Book Publishers Association (日本電子書籍出版社協会). Extracted from commercially published fixed-layout manga EPUBs where they are used for iBooks rendering compatibility.

Modify with caution.

## License

MIT
