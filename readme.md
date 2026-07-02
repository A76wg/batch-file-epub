# batch-file-epub

Convert a folder of manga / comic images into a fixed-layout EPUB3 optimised for Apple Books (iBooks).

## Features

- **Fixed-layout EPUB3** — pixel-perfect image rendering with SVG-wrapped pages
- **Per-page viewport** — every page uses its own image dimensions, so each image fills the screen edge-to-edge with zero blank space
- **Automatic image normalisation** — all images are scaled (aspect-ratio preserved) to a common median canvas with centred letterboxing; **enabled by default**
- **No compression by default** — images stored as-is for fastest packing; optional ZIP deflate via `--compress`
- **Chapter TOC** — flat or nested, auto-detected from subdirectories or explicit JSON
- **RTL / LTR** page progression (manga vs western comics)
- **CLI + Python API** — shell-friendly and agent-importable
- 電書協 CSS templates for full iBooks compatibility

## Requirements

- Python 3.9+
- [Pillow](https://pypi.org/project/Pillow/) (only needed when `--no-normalize` is used without normalisation; always required for letterboxing)
- [imagesize](https://pypi.org/project/imagesize/)

```bash
pip install pillow imagesize
```

## Usage

### CLI

```bash
# Basic — normalisation on, no compression (fastest)
python main.py --src ./images/ --dst ./out/ --title "My Manga" --lang zh --pack

# With compression (smaller .epub, slower to pack)
python main.py --src ./images/ --dst ./out/ --title "My Manga" --lang zh --pack --compress

# Skip normalisation (keep original image dimensions untouched)
python main.py --src ./images/ --dst ./out/ --title "My Manga" --lang zh --pack --no-normalize

# Explicit pack path
python main.py --src ./images/ --dst ./out/ --title "My Manga" --lang zh --pack ./manga.epub

# With chapters (inline JSON)
python main.py --src ./images/ --dst ./out/ --title "My Manga" --lang zh \
    --chapters '{"Ch.1":1,"Ch.2":25}' --pack

# Chapters from a JSON file
python main.py --src ./images/ --dst ./out/ --title "My Manga" --lang zh \
    --chapters chapters.json --pack

# Left-to-right (western comics / webtoons)
python main.py --src ./images/ --dst ./out/ --title "Webtoon" --lang ko --ltr --pack

# Lower re-encode quality = smaller output (only affects normalised images)
python main.py --src ./images/ --dst ./out/ --title "Manga" --lang zh --jpg-quality 70 --pack

# Disable chapter auto-detection
python main.py --src ./images/ --dst ./out/ --title "Manga" --lang zh --no-chapters --pack
```

### Python API

```python
from main import build_epub, pack_epub

out = build_epub(
    src="/path/to/images",
    dst="/tmp/epub-out",
    title="My Manga",
    lang="zh",
)
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
| `--lang` | `"ja"` | Language code (e.g. `ja`, `zh`, `en`, `ko`) |
| `--rtl` | on | Right-to-left page progression (manga, default) |
| `--ltr` | — | Left-to-right page progression (western comics, webtoons) |
| `--pack` | — | Zip output into `.epub`; defaults to `<dst>/<dst-dirname>.epub` |
| `--compress` | off | Enable ZIP deflate compression (smaller file, slower packing) |
| `--no-normalize` | off | Skip image normalisation (keep original pixel dimensions) |
| `--no-chapters` | off | Disable chapter auto-detection from subdirectories |
| `--chapters` | — | Chapter map as inline JSON `'{"Name":page}'` or `.json` file path |
| `--jpg-quality` | `85` | Re-encoding quality 1–100 (only applies when normalisation resizes an image) |
| `--quiet` | off | Suppress info-level log output |

## Normalisation (default: on)

Normalisation is **enabled by default** and works as follows:

1. All images are scanned with `imagesize` to collect their physical dimensions.
2. The **median width and height** across all images become the target canvas.
3. Every image is **scaled** (preserving aspect ratio) to fit within this canvas.
4. Images that don't fill the canvas exactly are **centred on a white background** (letterboxed).

This guarantees that every page has the **same viewport size**, no image overflows the screen, and blank space is minimised — even when the source images have wildly different dimensions.

Images that already match the canvas are copied as-is (no re-encode). Others are re-encoded in their **original format** (webp → webp, jpg → jpg) at the specified `--jpg-quality`.

```bash
# Normalisation is on by default — just don't pass --no-normalize
python main.py --src ./images/ --dst ./out/ --title "Manga" --lang zh --pack

# Tweak quality
python main.py --src ./images/ --dst ./out/ --title "Manga" --lang zh --jpg-quality 70 --pack

# Keep original sizes untouched
python main.py --src ./images/ --dst ./out/ --title "Manga" --lang zh --no-normalize --pack
```

## Per-Page Viewport Sizing

Without `--no-normalize`, each page's XHTML sets its SVG `viewBox` to the **image's own pixel dimensions** rather than a global maximum. This means:

- Every image fills the entire screen edge-to-edge.
- No blank space from a single oversized image stretching all viewports.
- Pages may have slightly different viewport sizes — the reader (Apple Books) handles this seamlessly with fixed-layout rendering.

## Packing & Compression

By default, `pack_epub` stores all files **without compression** (`ZIP_STORED`), making the `.epub` practically the same size as the source directory and very fast to produce. Pass `--compress` to enable `ZIP_DEFLATED` for a smaller file at the cost of packing time.

The packer also **skips the output `.epub` file itself** if it already exists inside the source directory, preventing recursive inclusion that could balloon file size on repeated runs.

## Supported Input Formats

`jpg`, `jpeg`, `png`, `webp`, `bmp`, `gif`, `tiff`, `tif`. Images are naturally sorted by filename (1 < 2 < 10 < 20) before processing.

## Chapter TOC

Chapters are generated in order of priority:

1. **`--chapters`** — Explicit JSON map or `.json` file path
2. **Auto-detect from folders** — Subdirectories become chapters:
   - **Flat**: `src/Ch01/*.png` → single-level TOC
   - **Nested**: `src/Vol.1/Ch01/*.png` → hierarchical TOC
   - **Mixed**: loose images at root level become a *Front Matter* section
3. **`--no-chapters`** — Skip TOC entirely

## CSS Templates

The bundled CSS originates from 電書協 EPUB 3 制作ガイド (ver.1.1.1) by the Japan Electronic Book Publishers Association (日本電子書籍出版社協会). Extracted from commercially published fixed-layout manga EPUBs for iBooks rendering compatibility.

Modify with caution.

## GUI (tkinter)

A graphical front-end is provided in `coverter-gui.py`. It wraps `main.py`'s API with a
user-friendly interface — no command-line knowledge required.

```bash
python coverter-gui.py
```

### GUI Features

| Section | Controls |
|---------|----------|
| **Input / Output** | Browse buttons for source image folder and output directory |
| **Metadata** | Title, Author, Publisher text fields; Language dropdown (ja, zh, en, ko, …) |
| **Page Progression** | Radio buttons: Right-to-Left (manga) / Left-to-Right (western) |
| **Image Processing** | Normalisation toggle (on by default); Re-encode quality slider (1–100) |
| **Chapters** | Three-mode selector: **Custom table** (add/remove chapter→page rows, auto-generates JSON), **Auto-detect** (subdirectories), or **No chapters** |
| **EPUB Packing** | Pack to `.epub` toggle; ZIP compression toggle; optional output filename |
| **Log** | Real-time coloured log output showing build progress and any errors |

### GUI Workflow

1. Select your **source folder** containing images (and optionally chapter subdirectories).
2. Choose an **output folder** where the EPUB structure will be written.
3. Fill in the **title** (required) and optionally author, publisher, language.
4. Choose **RTL (manga)** or **LTR (western)** page progression.
5. Toggle **normalisation** and adjust **quality** as needed.
6. Choose a **chapter mode** (default: custom table):
   - **Custom table** — click **＋ Add Row** and enter chapter name + start page; repeat for each chapter. The JSON is generated automatically.
   - **Auto-detect** — chapters are derived from subdirectory structure automatically.
   - **No chapters** — all images are treated as a single continuous sequence.
7. Enable **pack to .epub** if you want the final compressed file.
8. Click **🚀 Build EPUB** and watch the log for progress.
9. When complete, the `.epub` file will be in the output folder.

> **Note:** The build runs in a background thread so the GUI stays responsive. You
> can scroll the log while it works.

## License

MIT
