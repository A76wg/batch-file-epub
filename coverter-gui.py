#!/usr/bin/env python3
"""batch-file-epub GUI — tkinter front-end for main.py API.

Run:
    python coverter-gui.py
"""
from __future__ import annotations

import json
import logging
import os
import sys
import threading
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from pathlib import Path

# ── Ensure project root is on sys.path ──
_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

from main import build_epub, pack_epub

logger = logging.getLogger("batch-file-epub-gui")


# ═══════════════════════════════════════════
#  Re-usable labelled widget helpers
# ═══════════════════════════════════════════

class LabelEntry(ttk.Frame):
    """A labelled text entry."""
    def __init__(self, parent, label: str, default: str = "", **kwargs):
        super().__init__(parent)
        self.var = tk.StringVar(value=default)
        self.label = ttk.Label(self, text=label)
        self.entry = ttk.Entry(self, textvariable=self.var, **kwargs)
        self.label.pack(side=tk.LEFT, padx=(0, 4))
        self.entry.pack(side=tk.LEFT, fill=tk.X, expand=True)

    def get(self) -> str:
        return self.var.get()

    def set(self, value: str) -> None:
        self.var.set(value)


class LabelCombo(ttk.Frame):
    """A labelled combo box."""
    def __init__(self, parent, label: str, values: list[str],
                 default: str = "", **kwargs):
        super().__init__(parent)
        self.var = tk.StringVar(value=default)
        self.label = ttk.Label(self, text=label)
        self.combo = ttk.Combobox(self, textvariable=self.var,
                                  values=values, state="readonly", **kwargs)
        self.label.pack(side=tk.LEFT, padx=(0, 4))
        self.combo.pack(side=tk.LEFT, fill=tk.X, expand=True)

    def get(self) -> str:
        return self.var.get()


class LabelCheck(ttk.Frame):
    """A labelled check button."""
    def __init__(self, parent, label: str, default: bool = True):
        super().__init__(parent)
        self.var = tk.BooleanVar(value=default)
        self.cb = ttk.Checkbutton(self, text=label, variable=self.var)
        self.cb.pack(side=tk.LEFT)

    def get(self) -> bool:
        return self.var.get()


class PathPicker(ttk.Frame):
    """A labelled entry with a 'Browse…' button for selecting directories."""
    def __init__(self, parent, label: str, default: str = ""):
        super().__init__(parent)
        self.var = tk.StringVar(value=default)
        self.label = ttk.Label(self, text=label)
        self.entry = ttk.Entry(self, textvariable=self.var)
        self.btn = ttk.Button(self, text="Browse…", command=self._browse)
        self.label.pack(side=tk.LEFT, padx=(0, 4))
        self.entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 4))
        self.btn.pack(side=tk.LEFT)

    def get(self) -> str:
        return self.var.get()

    def set(self, value: str) -> None:
        self.var.set(value)

    def _browse(self) -> None:
        d = filedialog.askdirectory(title=f"Select {self.label['text']}")
        if d:
            self.var.set(d)


# ═══════════════════════════════════════════
#  Main Application
# ═══════════════════════════════════════════

class EpubBuilderGUI(tk.Tk):
    """tkinter GUI for batch-file-epub."""

    WINDOW_TITLE = "batch-file-epub — EPUB Builder"
    WINDOW_SIZE = "720x760"
    LANGUAGES = ["ja", "zh", "en", "ko", "de", "fr", "es", "it", "pt", "ru"]

    def __init__(self):
        super().__init__()
        self.title(self.WINDOW_TITLE)
        self.geometry(self.WINDOW_SIZE)
        self.minsize(640, 680)
        self.resizable(True, True)

        # ── State ──
        self._running = False

        self._build_ui()
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    # ─────────────────────────────────────────
    #  UI Construction
    # ─────────────────────────────────────────

    def _build_ui(self) -> None:
        # Scrollable outer frame
        self._canvas = tk.Canvas(self, borderwidth=0, highlightthickness=0)
        self._scrollbar = ttk.Scrollbar(self, orient=tk.VERTICAL,
                                        command=self._canvas.yview)
        self._scroll_frame = ttk.Frame(self._canvas)
        self._scroll_frame.bind("<Configure>",
                                lambda e: self._canvas.configure(
                                    scrollregion=self._canvas.bbox("all")))
        self._canvas.create_window((0, 0), window=self._scroll_frame,
                                   anchor="nw")
        self._canvas.configure(yscrollcommand=self._scrollbar.set)

        self._canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self._scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        # ── Mouse wheel scrolling ──
        def _on_mousewheel(event):
            self._canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")
        self._canvas.bind_all("<MouseWheel>", _on_mousewheel)

        f = self._scroll_frame
        # Make columns expand
        f.columnconfigure(1, weight=1)

        # ─── Section: Input / Output ───
        sec_io = ttk.LabelFrame(f, text="Input / Output", padding=10)
        sec_io.grid(row=0, column=0, columnspan=3, sticky="nsew",
                    padx=10, pady=(10, 4))
        sec_io.columnconfigure(1, weight=1)

        self.src_picker = PathPicker(sec_io, "Source folder:")
        self.src_picker.grid(row=0, column=0, columnspan=3, sticky="ew",
                             pady=2)

        self.dst_picker = PathPicker(sec_io, "Output folder:")
        self.dst_picker.grid(row=1, column=0, columnspan=3, sticky="ew",
                             pady=2)

        # ─── Section: Metadata ───
        sec_meta = ttk.LabelFrame(f, text="Metadata", padding=10)
        sec_meta.grid(row=1, column=0, columnspan=3, sticky="nsew",
                      padx=10, pady=4)
        sec_meta.columnconfigure(1, weight=1)

        self.title_entry = LabelEntry(sec_meta, "Title:", width=40)
        self.title_entry.grid(row=0, column=0, columnspan=3, sticky="ew",
                              pady=2)

        self.author_entry = LabelEntry(sec_meta, "Author:", width=40)
        self.author_entry.grid(row=1, column=0, columnspan=3, sticky="ew",
                               pady=2)

        self.publisher_entry = LabelEntry(sec_meta, "Publisher:", width=40)
        self.publisher_entry.grid(row=2, column=0, columnspan=3, sticky="ew",
                                  pady=2)

        self.lang_combo = LabelCombo(sec_meta, "Language:",
                                     values=self.LANGUAGES, default="ja",
                                     width=10)
        self.lang_combo.grid(row=3, column=0, sticky="w", pady=2)

        # ─── Section: Page Progression ───
        sec_dir = ttk.LabelFrame(f, text="Page Progression", padding=10)
        sec_dir.grid(row=2, column=0, columnspan=3, sticky="nsew",
                     padx=10, pady=4)
        sec_dir.columnconfigure(1, weight=1)

        self.progression_var = tk.StringVar(value="rtl")
        rtl_rb = ttk.Radiobutton(sec_dir, text="Right-to-Left (RTL) — Manga",
                                 variable=self.progression_var, value="rtl")
        ltr_rb = ttk.Radiobutton(sec_dir, text="Left-to-Right (LTR) — Western",
                                 variable=self.progression_var, value="ltr")
        rtl_rb.grid(row=0, column=0, sticky="w", padx=(0, 20))
        ltr_rb.grid(row=0, column=1, sticky="w")

        # ─── Section: Image Processing ───
        sec_img = ttk.LabelFrame(f, text="Image Processing", padding=10)
        sec_img.grid(row=3, column=0, columnspan=3, sticky="nsew",
                     padx=10, pady=4)
        sec_img.columnconfigure(1, weight=1)

        self.normalize_cb = LabelCheck(sec_img, "Normalize images (recommended)",
                                       default=True)
        self.normalize_cb.grid(row=0, column=0, sticky="w", pady=2)

        # Quality
        ttk.Label(sec_img, text="Re-encode quality:").grid(row=1, column=0,
                                                           sticky="w", pady=2)
        self.quality_var = tk.IntVar(value=85)
        self.quality_scale = ttk.Scale(sec_img, from_=1, to=100,
                                       variable=self.quality_var,
                                       orient=tk.HORIZONTAL,
                                       command=self._on_quality_change)
        self.quality_scale.grid(row=1, column=1, sticky="ew", padx=(4, 0),
                                pady=2)
        self.quality_label = ttk.Label(sec_img, text="85")
        self.quality_label.grid(row=1, column=2, padx=(4, 0), pady=2)

        # ─── Section: Chapters ───
        sec_ch = ttk.LabelFrame(f, text="Chapters", padding=10)
        sec_ch.grid(row=4, column=0, columnspan=3, sticky="nsew",
                    padx=10, pady=4)
        sec_ch.columnconfigure(1, weight=1)

        # Mode selection
        ttk.Label(sec_ch, text="Mode:").grid(row=0, column=0, sticky="w",
                                             pady=(0, 6))
        self._ch_mode_var = tk.StringVar(value="① Custom table (chapters → pages)")
        self._ch_mode_combo = ttk.Combobox(sec_ch,
                                           textvariable=self._ch_mode_var,
                                           values=[
                                               "① Custom table (chapters → pages)",
                                               "② Auto-detect from folders",
                                               "③ No chapters",
                                           ],
                                           state="readonly", width=40)
        self._ch_mode_combo.grid(row=0, column=1, columnspan=2, sticky="w",
                                 pady=(0, 6))
        self._ch_mode_combo.bind("<<ComboboxSelected>>",
                                 self._on_chapter_mode_change)

        # ── Mode 1: Custom table ──
        self._ch_custom_frame = ttk.Frame(sec_ch)
        self._ch_custom_frame.grid(row=1, column=0, columnspan=3,
                                   sticky="nsew")
        self._ch_custom_frame.columnconfigure(0, weight=1)

        # Treeview table
        columns = ("name", "page")
        self._ch_tree = ttk.Treeview(self._ch_custom_frame,
                                     columns=columns, show="headings",
                                     height=5, selectmode="browse")
        self._ch_tree.heading("name", text="Chapter Name")
        self._ch_tree.heading("page", text="Start Page")
        self._ch_tree.column("name", width=220, anchor="w")
        self._ch_tree.column("page", width=80, anchor="center")
        self._ch_tree.grid(row=0, column=0, columnspan=3, sticky="nsew",
                           pady=(0, 4))

        # Table action buttons
        tbtn_f = ttk.Frame(self._ch_custom_frame)
        tbtn_f.grid(row=1, column=0, sticky="w", pady=(0, 4))
        ttk.Button(tbtn_f, text="＋ Add Row",
                   command=self._add_chapter_row).pack(side=tk.LEFT,
                                                       padx=(0, 4))
        ttk.Button(tbtn_f, text="✕ Remove Selected",
                   command=self._remove_chapter_row).pack(side=tk.LEFT,
                                                          padx=(0, 4))
        ttk.Button(tbtn_f, text="Clear All",
                   command=self._clear_chapter_table).pack(side=tk.LEFT)

        # JSON preview
        ttk.Label(self._ch_custom_frame,
                  text="Preview (JSON, auto-generated):").grid(
            row=2, column=0, sticky="w", pady=(6, 2))
        self._ch_json_preview = tk.Text(self._ch_custom_frame, height=3,
                                         wrap=tk.WORD,
                                         font=("Consolas", 9),
                                         state=tk.DISABLED,
                                         bg="#f5f5f5", fg="#333333")
        self._ch_json_preview.grid(row=3, column=0, sticky="ew",
                                   pady=(0, 4))

        # ── Mode 2: Auto from folders ──
        self._ch_auto_frame = ttk.Frame(sec_ch)
        self._ch_auto_frame.grid(row=1, column=0, columnspan=3,
                                 sticky="nsew")
        ttk.Label(self._ch_auto_frame,
                  text="ℹ️  Chapters will be automatically detected from\n"
                  "subdirectory structure. Each subfolder becomes a\n"
                  "chapter; nested folders produce a hierarchical TOC.",
                  wraplength=480, foreground="#555555",
                  justify=tk.LEFT).pack(padx=10, pady=12, anchor="w")

        # ── Mode 3: No chapters ──
        self._ch_none_frame = ttk.Frame(sec_ch)
        self._ch_none_frame.grid(row=1, column=0, columnspan=3,
                                 sticky="nsew")
        ttk.Label(self._ch_none_frame,
                  text="ℹ️  No chapter table of contents will be\n"
                  "generated. All images are treated as a single\n"
                  "continuous sequence.",
                  wraplength=480, foreground="#555555",
                  justify=tk.LEFT).pack(padx=10, pady=12, anchor="w")

        # Show default mode
        self._on_chapter_mode_change()

        # ─── Section: Packing ───
        sec_pack = ttk.LabelFrame(f, text="EPUB Packing", padding=10)
        sec_pack.grid(row=5, column=0, columnspan=3, sticky="nsew",
                      padx=10, pady=4)
        sec_pack.columnconfigure(1, weight=1)

        self.pack_cb = LabelCheck(sec_pack, "Pack to .epub after building",
                                  default=True)
        self.pack_cb.grid(row=0, column=0, sticky="w", pady=2)

        self.compress_cb = LabelCheck(sec_pack, "Enable ZIP compression (smaller file)",
                                      default=False)
        self.compress_cb.grid(row=1, column=0, sticky="w", pady=2)

        ttk.Label(sec_pack, text="Output .epub name (optional):").grid(
            row=2, column=0, sticky="w", pady=(6, 2))
        self.pack_name_entry = LabelEntry(sec_pack, "", width=40)
        self.pack_name_entry.grid(row=3, column=0, columnspan=2, sticky="ew",
                                  pady=2)

        # ─── Section: Actions ───
        sec_actions = ttk.Frame(f)
        sec_actions.grid(row=6, column=0, columnspan=3, sticky="ew",
                         padx=10, pady=(8, 4))
        sec_actions.columnconfigure(0, weight=1)
        sec_actions.columnconfigure(1, weight=1)
        sec_actions.columnconfigure(2, weight=1)

        self.build_btn = ttk.Button(sec_actions, text="🚀  Build EPUB",
                                    command=self._build)
        self.build_btn.grid(row=0, column=0, sticky="ew", padx=(0, 4))

        self.clear_btn = ttk.Button(sec_actions, text="Clear",
                                    command=self._clear_log)
        self.clear_btn.grid(row=0, column=1, sticky="ew", padx=4)

        self.quit_btn = ttk.Button(sec_actions, text="Quit",
                                   command=self._on_close)
        self.quit_btn.grid(row=0, column=2, sticky="ew", padx=(4, 0))

        # ─── Section: Log ───
        sec_log = ttk.LabelFrame(f, text="Log", padding=6)
        sec_log.grid(row=7, column=0, columnspan=3, sticky="nsew",
                     padx=10, pady=(4, 10))
        f.rowconfigure(7, weight=1)
        sec_log.rowconfigure(0, weight=1)
        sec_log.columnconfigure(0, weight=1)

        self.log_text = tk.Text(sec_log, height=12, width=72,
                                wrap=tk.WORD, state=tk.DISABLED,
                                font=("Consolas", 9),
                                bg="#1e1e1e", fg="#d4d4d4",
                                insertbackground="#d4d4d4")
        self.log_text.grid(row=0, column=0, sticky="nsew")

        log_scroll = ttk.Scrollbar(sec_log, orient=tk.VERTICAL,
                                   command=self.log_text.yview)
        log_scroll.grid(row=0, column=1, sticky="ns")
        self.log_text.configure(yscrollcommand=log_scroll.set)

        # ── Redirect logging to the GUI ──
        self._setup_logging()

        # ── Keyboard shortcuts ──
        self.bind("<Control-Return>", lambda e: self._build())

    # ─────────────────────────────────────────
    #  Logging
    # ─────────────────────────────────────────

    def _setup_logging(self) -> None:
        """Install a handler that writes log records to the GUI text widget."""
        class GuiHandler(logging.Handler):
            def __init__(self, text_widget: tk.Text):
                super().__init__()
                self.text = text_widget

            def emit(self, record: logging.LogRecord) -> None:
                msg = self.format(record)
                # Colour-code by level
                tag = {
                    logging.DEBUG: "debug",
                    logging.INFO: "info",
                    logging.WARNING: "warning",
                    logging.ERROR: "error",
                    logging.CRITICAL: "critical",
                }.get(record.levelno, "info")

                def append():
                    self.text.configure(state=tk.NORMAL)
                    self.text.insert(tk.END, msg + "\n", tag)
                    self.text.see(tk.END)
                    self.text.configure(state=tk.DISABLED)
                self.text.after(0, append)

        handler = GuiHandler(self.log_text)
        handler.setFormatter(logging.Formatter(
            "%(asctime)s  %(levelname)-8s  %(message)s",
            datefmt="%H:%M:%S"))
        # Capture our logger + root logger so build_epub logs appear
        root_logger = logging.getLogger()
        root_logger.setLevel(logging.INFO)
        # Remove existing handlers to avoid double output
        for h in root_logger.handlers[:]:
            root_logger.removeHandler(h)
        root_logger.addHandler(handler)

        # Define colour tags
        self.log_text.tag_configure("debug", foreground="#888888")
        self.log_text.tag_configure("info", foreground="#d4d4d4")
        self.log_text.tag_configure("warning", foreground="#ffcc00")
        self.log_text.tag_configure("error", foreground="#ff5555")
        self.log_text.tag_configure("critical", foreground="#ff0000",
                                    font=("Consolas", 9, "bold"))

    def _log(self, msg: str, level: str = "info") -> None:
        """Convenience: log a message at the given level string."""
        getattr(logger, level, logger.info)(msg)

    # ─────────────────────────────────────────
    #  Callbacks
    # ─────────────────────────────────────────

    def _on_quality_change(self, _=None) -> None:
        self.quality_label.configure(text=str(self.quality_var.get()))

    # ─────────────────────────────────────────
    #  Chapter helpers (custom table mode)
    # ─────────────────────────────────────────

    def _on_chapter_mode_change(self, _=None) -> None:
        """Show/hide chapter sub-frames based on selected mode."""
        mode = self._ch_mode_var.get()
        if mode.startswith("①"):
            self._ch_custom_frame.grid()
            self._ch_auto_frame.grid_remove()
            self._ch_none_frame.grid_remove()
        elif mode.startswith("②"):
            self._ch_custom_frame.grid_remove()
            self._ch_auto_frame.grid()
            self._ch_none_frame.grid_remove()
        else:
            self._ch_custom_frame.grid_remove()
            self._ch_auto_frame.grid_remove()
            self._ch_none_frame.grid()

    def _get_chapter_table_data(self) -> dict[str, int] | None:
        """Read the custom table and return a dict or None if empty."""
        data: dict[str, int] = {}
        for child in self._ch_tree.get_children():
            name, page_str = self._ch_tree.item(child, "values")
            name = name.strip()
            if name:
                data[name] = int(page_str)
        return data if data else None

    def _sync_chapter_json(self) -> None:
        """Update the JSON preview from the treeview data."""
        data = self._get_chapter_table_data()
        text = json.dumps(data, indent=2, ensure_ascii=False) if data else "{}"
        self._ch_json_preview.configure(state=tk.NORMAL)
        self._ch_json_preview.delete("1.0", tk.END)
        self._ch_json_preview.insert("1.0", text)
        self._ch_json_preview.configure(state=tk.DISABLED)

    def _add_chapter_row(self) -> None:
        """Prompt user for chapter name & page, insert into table."""
        from tkinter import simpledialog
        name = simpledialog.askstring("Add Chapter",
                                      "Chapter name:",
                                      parent=self)
        if not name or not name.strip():
            return
        name = name.strip()
        last_page = 1
        children = self._ch_tree.get_children()
        if children:
            # Suggest next page after last entry
            _, last_page_str = self._ch_tree.item(children[-1], "values")
            last_page = int(last_page_str) + 1
        page = simpledialog.askinteger("Add Chapter",
                                       f"Start page for \"{name}\":",
                                       parent=self,
                                       initialvalue=last_page,
                                       minvalue=1)
        if page is None:
            return
        self._ch_tree.insert("", tk.END, values=(name, str(page)))
        self._sync_chapter_json()
        self._log(f"Chapter added: \"{name}\" → page {page}")

    def _remove_chapter_row(self) -> None:
        """Remove selected row from the table."""
        sel = self._ch_tree.selection()
        if not sel:
            messagebox.showinfo("Remove", "Please select a row first.")
            return
        for item in sel:
            name = self._ch_tree.item(item, "values")[0]
            self._ch_tree.delete(item)
            self._log(f"Chapter removed: \"{name}\"")
        self._sync_chapter_json()

    def _clear_chapter_table(self) -> None:
        """Remove all rows from the table."""
        if not self._ch_tree.get_children():
            return
        if not messagebox.askyesno("Clear", "Remove all chapter entries?"):
            return
        for item in self._ch_tree.get_children():
            self._ch_tree.delete(item)
        self._sync_chapter_json()
        self._log("Chapter table cleared")

    def _clear_log(self) -> None:
        self.log_text.configure(state=tk.NORMAL)
        self.log_text.delete("1.0", tk.END)
        self.log_text.configure(state=tk.DISABLED)

    def _on_close(self) -> None:
        if self._running:
            if not messagebox.askokcancel(
                    "Quit", "A build is in progress. Quit anyway?"):
                return
        self.destroy()

    # ─────────────────────────────────────────
    #  Build
    # ─────────────────────────────────────────

    def _build(self) -> None:
        if self._running:
            messagebox.showwarning("Busy", "A build is already running.")
            return

        # ── Validate inputs ──
        src = self.src_picker.get().strip()
        dst = self.dst_picker.get().strip()
        title = self.title_entry.get().strip()

        if not src:
            messagebox.showerror("Missing input", "Please select a source folder.")
            return
        if not dst:
            messagebox.showerror("Missing input", "Please select an output folder.")
            return
        if not title:
            messagebox.showerror("Missing input", "Please enter a book title.")
            return
        if not Path(src).is_dir():
            messagebox.showerror("Invalid input",
                                 f"Source folder does not exist:\n{src}")
            return

        # ── Chapter data ──
        mode_prefix = self._ch_mode_var.get()[:2]  # "① ", "② ", "③ "
        if mode_prefix == "① ":
            # Custom table → convert to dict
            chapters = self._get_chapter_table_data()
            no_chapters = False
        elif mode_prefix == "② ":
            # Auto-detect from folders
            chapters = None
            no_chapters = False
        else:
            # No chapters
            chapters = None
            no_chapters = True

        # ── Disable UI ──
        self._running = True
        self.build_btn.configure(state=tk.DISABLED, text="⏳ Building…")

        # ── Run in background thread ──
        args = {
            "src": src,
            "dst": dst,
            "title": title,
            "author": self.author_entry.get().strip(),
            "publisher": self.publisher_entry.get().strip(),
            "lang": self.lang_combo.get() or "ja",
            "rtl": self.progression_var.get() == "rtl",
            "no_chapters": no_chapters,
            "chapters": chapters,
            "normalize": self.normalize_cb.get(),
            "encode_quality": self.quality_var.get(),
        }

        pack_enabled = self.pack_cb.get()
        compress = self.compress_cb.get()
        pack_name = self.pack_name_entry.get().strip()

        t = threading.Thread(target=self._build_thread,
                             args=(args, pack_enabled, compress, pack_name),
                             daemon=True)
        t.start()

    def _build_thread(self, args: dict, pack_enabled: bool,
                      compress: bool, pack_name: str) -> None:
        """Run build_epub (and optionally pack_epub) in a worker thread."""
        try:
            self._log("=" * 50)
            self._log(f"Starting build: {args['title']}")
            self._log(f"  Source   → {args['src']}")
            self._log(f"  Output   → {args['dst']}")
            self._log(f"  Language → {args['lang']}")
            self._log(f"  RTL      → {args['rtl']}")
            ch_desc = "custom table" if args['chapters'] else "disabled" if args['no_chapters'] else "auto-detect"
            self._log(f"  Chapters → {ch_desc}")
            self._log(f"  Normalize → {args['normalize']}")
            self._log(f"  Quality   → {args['encode_quality']}")

            # ── Build ──
            out_dir = build_epub(**args)

            self._log(f"✅ EPUB structure built at: {out_dir}")

            # ── Pack ──
            if pack_enabled:
                stem = pack_name if pack_name else Path(args["dst"]).name.rstrip("/\\")
                # Remove extension if user included it
                stem = stem.removesuffix(".epub")
                epub_path = Path(args["dst"]).resolve() / f"{stem}.epub"
                pack_epub(out_dir, epub_path, no_compress=not compress)
                size_mb = epub_path.stat().st_size / (1024 * 1024)
                self._log(f"📦 Packed → {epub_path}  ({size_mb:.1f} MB)")
                self._log(f"   Compression: {'ZIP_DEFLATED' if compress else 'ZIP_STORED (none)'}")
            else:
                self._log("ℹ️  Skipped packing. Use '--pack' CLI or re-run with pack enabled.")

            self._log("✅ Done!")
            self._log("=" * 50)

        except Exception as e:
            self._log(f"❌ ERROR: {e}", level="error")
            import traceback
            self._log(traceback.format_exc(), level="debug")
        finally:
            self.after(0, self._build_done)

    def _build_done(self) -> None:
        """Re-enable UI after build completes."""
        self._running = False
        self.build_btn.configure(state=tk.NORMAL, text="🚀  Build EPUB")


# ═══════════════════════════════════════════
#  Entry point
# ═══════════════════════════════════════════

def main() -> None:
    app = EpubBuilderGUI()
    app.mainloop()


if __name__ == "__main__":
    main()
