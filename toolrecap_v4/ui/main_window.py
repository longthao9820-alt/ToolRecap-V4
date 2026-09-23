"""Main desktop application window for ToolRecap V4 matching V2 visual layout.

Invariants:
- Visual styling, layout, fonts, and dimensions aligned with ToolRecap V2 ui.py (1120x760, min 920x680, vista/clam theme).
- Header with Title, Subtitle, Update check button, and Settings button.
- In-app NotificationBanner with visible [X] close button.
- Movie Source section with File and Folder selection buttons and clean status label.
- Unified 5-column Source Episodes & Output Queue table (Episode, Source Video, Stage, Progress, Status).
- Progress bar and bottom action controls: Start, Stop, Open Output Folder, Resume, Render from JSON (0 AI), Clear.
- Status bar showing current status on left and hardware GPU encoder info on right.
- Thread-safe background worker communication exclusively via queue (no Tk calls from worker).
- Safe window close with cancellation and checkpoint preservation.
"""

from __future__ import annotations

from datetime import datetime, timezone
import logging
import os
from pathlib import Path
import queue
import subprocess
import sys
import threading
from typing import Any, Callable, Dict, List, Optional, Sequence, Union

# Ensure Tcl/Tk paths on Windows for robust portable execution
if sys.platform == "win32":
    tcl_path = os.path.join(sys.base_prefix, "tcl", "tcl8.6")
    tk_path = os.path.join(sys.base_prefix, "tcl", "tk8.6")
    if os.path.isdir(tcl_path) and "TCL_LIBRARY" not in os.environ:
        os.environ["TCL_LIBRARY"] = tcl_path
    if os.path.isdir(tk_path) and "TK_LIBRARY" not in os.environ:
        os.environ["TK_LIBRARY"] = tk_path

    if getattr(sys, "frozen", False):
        base_mei = getattr(sys, "_MEIPASS", None)
        if base_mei:
            for candidate in [
                os.path.join(base_mei, "_tcl_data"),
                os.path.join(base_mei, "tcl", "tcl8.6"),
                os.path.join(base_mei, "tcl8.6"),
                os.path.join(base_mei, "tcl"),
            ]:
                if os.path.isdir(candidate):
                    os.environ["TCL_LIBRARY"] = candidate.replace("\\", "/")
                    break
            for candidate in [
                os.path.join(base_mei, "_tk_data"),
                os.path.join(base_mei, "tcl", "tk8.6"),
                os.path.join(base_mei, "tk8.6"),
                os.path.join(base_mei, "tk"),
            ]:
                if os.path.isdir(candidate):
                    os.environ["TK_LIBRARY"] = candidate.replace("\\", "/")
                    break

import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from toolrecap_v4.__version__ import __version__
from toolrecap_v4.discovery import (
    SUPPORTED_EXTENSIONS,
    SourceFingerprint,
    compute_file_fingerprint,
    discover_sources,
    natural_sort_key,
)
from toolrecap_v4.media import detect_gpu_encoder, probe_media
from toolrecap_v4.persistence import ProjectPersistence, read_json
from toolrecap_v4.settings import AppSettings, SettingsManager
from toolrecap_v4.ui.notifications import WindowsNotificationService
from toolrecap_v4.ui.settings_dialog import SettingsDialog
from toolrecap_v4.ui.worker import SourceDiscoveryWorker, WorkerMessage, WorkflowWorker
from toolrecap_v4.workflow import OutputStatus, ProjectStatus

logger = logging.getLogger(__name__)

SEASON_STAGE_TRANSLATIONS: dict[str, str] = {
    "Finalizer": "Finalizer",
    "finalizer": "Finalizer",
    "Technical JSON Validation": "Kiểm tra kỹ thuật Final JSON",
    "json_validation": "Kiểm tra kỹ thuật Final JSON",
    "Final JSON Repair": "Sửa Final JSON",
    "json_repair": "Sửa Final JSON",
    "CANDIDATE_DISCOVERY": "Khám phá ứng viên",
    "candidate_discovery": "Khám phá ứng viên",
    "Candidate Discovery": "Khám phá ứng viên",
    "CANDIDATE_CONSOLIDATION": "Hợp nhất ứng viên",
    "candidate_consolidation": "Hợp nhất ứng viên",
    "Candidate Consolidation": "Hợp nhất ứng viên",
    "CANDIDATE_VERIFYING": "Xác minh kết quả 0 output",
    "candidate_verifying": "Xác minh kết quả 0 output",
    "Candidate Verifying": "Xác minh kết quả 0 output",
    "ZERO_OUTPUT_VERIFICATION": "Xác minh kết quả 0 output",
    "zero_output_verification": "Xác minh kết quả 0 output",
    "Zero Output Verification": "Xác minh kết quả 0 output",
    "Season Mining": "Khai thác cốt truyện",
    "season_mining": "Khai thác cốt truyện",
    "Season Batch": "Phân tích nhóm mùa",
    "season_batch": "Phân tích nhóm mùa",
    "Episode Summarizing": "Tóm tắt tập",
    "episode_summarizing": "Tóm tắt tập",
    "Season Merging": "Hợp nhất cốt truyện",
    "season_merging": "Hợp nhất cốt truyện",
}


def translate_season_stage(stage: str) -> str:
    if not stage:
        return "Sẵn sàng"
    return SEASON_STAGE_TRANSLATIONS.get(stage, stage)


def safe_after(widget: tk.Misc | None, ms: int, func: Callable, *args: Any) -> str | None:
    """Safely schedule a callback on a tkinter widget, catching post-destroy / mainloop exceptions."""
    if widget is None:
        return None

    def _wrapped() -> None:
        try:
            if hasattr(widget, "_is_closed") and getattr(widget, "_is_closed", False):
                return
            if hasattr(widget, "winfo_exists") and not widget.winfo_exists():
                return
            func(*args)
        except (tk.TclError, RuntimeError):
            pass
        except Exception:
            pass

    try:
        if hasattr(widget, "_is_closed") and getattr(widget, "_is_closed", False):
            return None
        if hasattr(widget, "winfo_exists") and not widget.winfo_exists():
            return None
        return widget.after(ms, _wrapped)
    except (tk.TclError, RuntimeError):
        return None
    except Exception:
        return None


def format_bytes(size_bytes: int) -> str:
    """Format bytes into readable human unit (MB, GB)."""
    if size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f} KB"
    elif size_bytes < 1024 * 1024 * 1024:
        return f"{size_bytes / (1024 * 1024):.1f} MB"
    return f"{size_bytes / (1024 * 1024 * 1024):.2f} GB"


def format_duration(seconds: float) -> str:
    """Format seconds into HH:MM:SS or MM:SS."""
    secs = int(round(seconds))
    mins, s = divmod(secs, 60)
    hrs, m = divmod(mins, 60)
    if hrs > 0:
        return f"{hrs:02d}:{m:02d}:{s:02d}"
    return f"{m:02d}:{s:02d}"


class NotificationBanner(ttk.Frame):
    """Dismissible in-app banner with a visible 'X' button, using consistent grid geometry."""

    def __init__(
        self,
        parent: tk.Widget,
        *,
        on_dismiss: Callable[[], None] | None = None,
    ) -> None:
        super().__init__(parent, padding=(10, 6))
        self.on_dismiss = on_dismiss
        self._visible = False
        self._auto_dismiss_job: str | None = None

        self.columnconfigure(1, weight=1)

        self.icon_label = ttk.Label(self, text="ℹ", font=("Segoe UI", 11, "bold"))
        self.icon_label.grid(row=0, column=0, padx=(4, 8), sticky="w")

        self.message_label = ttk.Label(self, text="", font=("Segoe UI", 9), wraplength=700)
        self.message_label.grid(row=0, column=1, sticky="ew")

        self.close_button = ttk.Button(
            self,
            text="✕",
            width=3,
            command=self.dismiss,
            style="NotificationClose.TButton",
        )
        self.close_button.grid(row=0, column=2, padx=(8, 4), sticky="e")

        self._configure_styles()

    def _configure_styles(self) -> None:
        style = ttk.Style(self)
        style.configure("NotificationClose.TButton", font=("Segoe UI", 9, "bold"), padding=2)

    @property
    def is_visible(self) -> bool:
        return self._visible

    def show(
        self,
        message: str,
        level: str = "info",
        *,
        auto_dismiss_ms: int = 0,
        row: int = 1,
        column: int = 0,
    ) -> None:
        """Display notification message using grid geometry consistently with parent container."""
        if self._auto_dismiss_job:
            try:
                self.after_cancel(self._auto_dismiss_job)
            except Exception:
                pass
            self._auto_dismiss_job = None

        icons = {
            "info": "ℹ",
            "success": "✓",
            "warning": "⚠",
            "error": "✕",
        }
        self.icon_label.config(text=icons.get(level, "ℹ"))
        self.message_label.config(text=message)

        self.grid(row=row, column=column, sticky="ew", pady=(0, 8))
        self._visible = True

        if auto_dismiss_ms > 0:
            self._auto_dismiss_job = self.after(auto_dismiss_ms, self.dismiss)

    def dismiss(self) -> None:
        """Hide notification via grid_remove and invoke dismiss callback."""
        if self._auto_dismiss_job:
            try:
                self.after_cancel(self._auto_dismiss_job)
            except Exception:
                pass
            self._auto_dismiss_job = None

        if self._visible:
            try:
                self.grid_remove()
            except Exception:
                pass
            self._visible = False

        if self.on_dismiss:
            try:
                self.on_dismiss()
            except Exception:
                pass

    def destroy(self) -> None:
        if self._auto_dismiss_job:
            try:
                self.after_cancel(self._auto_dismiss_job)
            except Exception:
                pass
            self._auto_dismiss_job = None
        super().destroy()


class MainWindow(tk.Tk):
    """Main desktop application window for ToolRecap V4 matching V2 visual layout."""

    def __init__(self, persistence: Optional[ProjectPersistence] = None) -> None:
        for attempt in range(3):
            try:
                super().__init__()
                break
            except tk.TclError:
                if attempt == 2:
                    raise
                import time
                time.sleep(0.05)

        self.title(f"ToolRecap V4 — Tự Động Hóa Video Recap (v{__version__})")
        self.geometry("1120x760")
        self.minsize(920, 680)
        self.protocol("WM_DELETE_WINDOW", self._on_close)

        # Storage & State
        self.persistence = persistence or ProjectPersistence()
        self.settings_manager = SettingsManager(persistence=self.persistence)
        self.notification_service = WindowsNotificationService()

        self.msg_queue: queue.Queue[WorkerMessage] = queue.Queue()
        self.worker = WorkflowWorker(
            msg_queue=self.msg_queue,
            persistence=self.persistence,
            settings_manager=self.settings_manager,
        )
        self.discovery_worker = SourceDiscoveryWorker(
            msg_queue=self.msg_queue,
        )
        self._active_discovery_token: int = 0
        self._is_closed: bool = False
        self._poll_job: Optional[str] = None
        self._gpu_detect_job: Optional[str] = None
        self._close_job: Optional[str] = None

        self.settings = self.settings_manager.load()
        self.discovered_sources: List[SourceFingerprint] = []
        self.current_project_id: Optional[str] = None
        self.current_project_name: Optional[str] = None
        self._resume_project_ids: Dict[str, str] = {}
        self._output_paths: Dict[str, str] = {}

        # Tkinter variables matching V2
        self.source_var = tk.StringVar(value="Chưa chọn video hoặc thư mục.")
        self.status_var = tk.StringVar(value="Sẵn sàng.")
        self.progress_var = tk.DoubleVar(value=0.0)
        self.progress_label_var = tk.StringVar(value="0%")
        self.gpu_status_var = tk.StringVar(value="Đang kiểm tra phần cứng...")

        self._build_style()
        self._build_ui()
        self._refresh_queue_table()

        # Background tasks
        self._gpu_detect_job = safe_after(self, 200, self._detect_gpu_background)

        # Check restartable projects
        self._check_restart_projects()

        # Start periodic queue polling
        self._poll_job = safe_after(self, 100, self._poll_queue)

    def _build_style(self) -> None:
        style = ttk.Style(self)
        theme = "vista" if "vista" in style.theme_names() else "clam"
        style.theme_use(theme)

        style.configure("Title.TLabel", font=("Segoe UI Semibold", 16))
        style.configure("Subtitle.TLabel", font=("Segoe UI", 10), foreground="#555555")
        style.configure("Primary.TButton", font=("Segoe UI Semibold", 10), padding=(16, 8))
        style.configure("TButton", font=("Segoe UI", 9), padding=(10, 5))
        style.configure("Danger.TButton", font=("Segoe UI Semibold", 10), padding=(14, 8))
        style.configure("Treeview", rowheight=32, font=("Segoe UI", 9))
        style.configure("Treeview.Heading", font=("Segoe UI Semibold", 9), padding=6)
        style.configure("Horizontal.TProgressbar", thickness=14)
        self.style = style

    def _build_ui(self) -> None:
        container = ttk.Frame(self, padding=16)
        container.pack(fill="both", expand=True)
        container.columnconfigure(0, weight=1)
        container.rowconfigure(3, weight=1)

        # 1. Top Header
        header = ttk.Frame(container)
        header.grid(row=0, column=0, sticky="ew", pady=(0, 10))
        header.columnconfigure(1, weight=1)

        ttk.Label(header, text="ToolRecap V4", style="Title.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Label(
            header,
            text="Tự động sản xuất video recap hoàn chỉnh chỉ với một cú nhấp chuột",
            style="Subtitle.TLabel",
        ).grid(row=1, column=0, sticky="w", pady=(2, 0))

        btn_box = ttk.Frame(header)
        btn_box.grid(row=0, column=2, rowspan=2, sticky="e")
        self.update_btn = ttk.Button(btn_box, text="🔄 Kiểm tra cập nhật", command=self._on_check_update)
        self.update_btn.pack(side="left", padx=4)
        self.settings_btn = ttk.Button(btn_box, text="⚙ Settings", command=self._on_open_settings)
        self.settings_btn.pack(side="left", padx=4)

        # 2. Notification Banner (with visible [X])
        self.banner = NotificationBanner(container, on_dismiss=self._on_banner_dismissed)
        self.banner.grid(row=1, column=0, sticky="ew", pady=(0, 8))
        self.banner.grid_remove()

        # 3. Movie Source Section (Clean, without voice selector)
        source_box = ttk.LabelFrame(container, text="Movie Source", padding=12)
        source_box.grid(row=2, column=0, sticky="ew", pady=(0, 10))
        source_box.columnconfigure(0, weight=1)

        src_btn_bar = ttk.Frame(source_box)
        src_btn_bar.pack(fill="x", pady=(0, 6))
        self.btn_select_file = ttk.Button(src_btn_bar, text="📁 Select File", command=self._choose_file)
        self.btn_select_file.pack(side="left", padx=(0, 6))
        self.btn_select_folder = ttk.Button(src_btn_bar, text="📂 Select Folder", command=self._choose_folder)
        self.btn_select_folder.pack(side="left")

        self.lbl_source = ttk.Label(
            source_box,
            textvariable=self.source_var,
            font=("Segoe UI", 9),
            foreground="#0969da",
            wraplength=900,
        )
        self.lbl_source.pack(fill="x")

        # Restored projects must remain visible after a fresh application start.
        self.resume_banner = ttk.Frame(source_box)
        ttk.Label(self.resume_banner, text="Dự án chưa hoàn thành:").pack(side="left", padx=(0, 8))
        self.cmb_resume_projects = ttk.Combobox(self.resume_banner, state="readonly", width=54)
        self.cmb_resume_projects.pack(side="left", fill="x", expand=True, padx=(0, 8))
        self.cmb_resume_projects.bind("<<ComboboxSelected>>", self._on_select_resume_project)
        self.btn_resume_saved = ttk.Button(
            self.resume_banner, text="⏯ Tiếp tục dự án đã lưu", command=self._on_resume_detected_project,
        )
        self.btn_resume_saved.pack(side="left")

        # 4. Source Episodes & Queue Table Frame (5 columns)
        queue_frame = ttk.LabelFrame(container, text="Source Episodes & Output Queue", padding=8)
        queue_frame.grid(row=3, column=0, sticky="nsew", pady=(0, 10))
        queue_frame.columnconfigure(0, weight=1)
        queue_frame.rowconfigure(0, weight=1)

        columns = ("episode", "source_video", "stage", "progress", "status")
        self.tree = ttk.Treeview(queue_frame, columns=columns, show="headings", selectmode="browse")
        self.tree.heading("episode", text="Episode")
        self.tree.heading("source_video", text="Source Video")
        self.tree.heading("stage", text="Stage")
        self.tree.heading("progress", text="Progress")
        self.tree.heading("status", text="Status")

        self.tree.column("episode", width=90, anchor="center")
        self.tree.column("source_video", width=260, anchor="w")
        self.tree.column("stage", width=150, anchor="center")
        self.tree.column("progress", width=90, anchor="center")
        self.tree.column("status", width=420, anchor="w")

        scroll = ttk.Scrollbar(queue_frame, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=scroll.set)
        self.tree.grid(row=0, column=0, sticky="nsew")
        scroll.grid(row=0, column=1, sticky="ns")
        self.tree.bind("<Double-1>", self._on_double_click_tree)

        # 5. Progress Section
        prog_frame = ttk.LabelFrame(container, text="Progress", padding=(10, 6))
        prog_frame.grid(row=4, column=0, sticky="ew", pady=(0, 8))
        prog_frame.columnconfigure(0, weight=1)

        self.progressbar = ttk.Progressbar(prog_frame, variable=self.progress_var, maximum=100)
        self.progressbar.grid(row=0, column=0, sticky="ew")

        # 6. Action Controls Frame
        action_frame = ttk.Frame(container)
        action_frame.grid(row=5, column=0, sticky="ew", pady=(0, 8))

        self.btn_start = ttk.Button(
            action_frame,
            text="▶ Start Creating Recap Videos",
            style="Primary.TButton",
            command=self._on_start_project,
        )
        self.btn_start.pack(side="left", padx=(0, 8))

        self.btn_stop = ttk.Button(
            action_frame,
            text="⏹ Stop",
            style="Danger.TButton",
            command=self._on_stop_project,
            state="disabled",
        )
        self.btn_stop.pack(side="left", padx=(0, 8))

        self.btn_open_out = ttk.Button(
            action_frame,
            text="📂 Open Output Folder",
            command=self._open_output_folder,
        )
        self.btn_open_out.pack(side="left", padx=(0, 8))

        self.btn_resume = ttk.Button(
            action_frame,
            text="⏯ Tiếp tục",
            command=self._on_resume_current,
            state="disabled",
        )
        self.btn_resume.pack(side="left", padx=(0, 8))

        self.btn_render_json = ttk.Button(
            action_frame,
            text="📄 Dựng từ JSON (0 AI)",
            command=self._on_render_existing_json,
        )
        self.btn_render_json.pack(side="left", padx=(0, 8))

        self.btn_clear = ttk.Button(
            action_frame,
            text="Xóa danh sách",
            command=self._clear_queue,
        )
        self.btn_clear.pack(side="right")

        # 7. Status Bar Frame
        status_bar = ttk.Frame(container, relief="sunken", padding=(8, 6))
        status_bar.grid(row=6, column=0, sticky="ew")
        status_bar.columnconfigure(1, weight=1)

        ttk.Label(status_bar, text="Trạng thái:", font=("Segoe UI Semibold", 9)).grid(row=0, column=0, sticky="w", padx=(0, 6))
        ttk.Label(status_bar, textvariable=self.status_var, font=("Segoe UI", 9)).grid(row=0, column=1, sticky="w")
        ttk.Label(status_bar, textvariable=self.gpu_status_var, font=("Segoe UI", 8), foreground="#555").grid(row=0, column=2, sticky="e")

        # Compatibility & Internal Aliases
        self.btn_cancel = self.btn_stop
        self.tree_sources = self.tree
        self.tree_outputs = self.tree
        self.lbl_src_summary = self.lbl_source
        self.progress_bar = self.progressbar

        # Offscreen logging & stage label for internal message tracking / testing
        self.lbl_stage = ttk.Label(self, textvariable=self.status_var)
        self.txt_log = tk.Text(self, height=1)

    # -------------------------------------------------------------------------
    # GPU and Updater Background Checks
    # -------------------------------------------------------------------------
    def _detect_gpu_background(self) -> None:
        msg_queue = self.msg_queue

        def _check() -> None:
            try:
                status = detect_gpu_encoder()
                if status.available:
                    label = f"Mã hóa: {status.label} ({status.gpu_name})" if status.gpu_name else f"Mã hóa: {status.label}"
                else:
                    label = "Mã hóa: CPU (libx264)"
            except Exception:
                label = "Phần cứng: CPU"
            msg_queue.put(WorkerMessage(kind="gpu_status", data=label))

        threading.Thread(target=_check, daemon=True, name="GpuCheckThread").start()

    def _set_discovery_busy(self, is_busy: bool, msg: str = "") -> None:
        if is_busy:
            self.btn_start.config(state="disabled")
            self.btn_stop.config(state="normal")
            self.btn_resume.config(state="disabled")
            self.btn_render_json.config(state="disabled")
            if msg:
                self.status_var.set(msg)
                self.source_var.set(msg)
        else:
            if not self.worker.is_running:
                self.btn_start.config(state="normal")
                self.btn_stop.config(state="disabled")
                self.btn_resume.config(state="normal" if self.current_project_id else "disabled")
                self.btn_render_json.config(state="normal")
                self.btn_select_file.config(state="normal")
                self.btn_select_folder.config(state="normal")
                self.btn_clear.config(state="normal")

    # -------------------------------------------------------------------------
    # Source Loading (Single File -> Single Episode, Folder -> Season)
    # -------------------------------------------------------------------------
    def _choose_file(self) -> None:
        if self.worker.is_running:
            return
        filetypes = [
            ("Video files", "*.mp4;*.mkv;*.mov;*.avi;*.webm;*.m4v;*.ts;*.m2ts"),
            ("All files", "*.*"),
        ]
        chosen = filedialog.askopenfilename(
            parent=self,
            title="Chọn file video",
            filetypes=filetypes,
        )
        if chosen:
            self._load_file(Path(chosen))

    def _choose_folder(self) -> None:
        if self.worker.is_running:
            return
        chosen = filedialog.askdirectory(
            parent=self,
            title="Chọn thư mục chứa video",
        )
        if chosen:
            self._load_folder(Path(chosen))

    def _load_file(self, path: Path) -> None:
        p = Path(path).resolve()
        self._active_discovery_token = self.discovery_worker.start_discovery(p, is_folder=False)
        self._set_discovery_busy(True, f"Đang kiểm tra file: {p.name}")

    def _load_folder(self, path: Path) -> None:
        p = Path(path).resolve()
        self._active_discovery_token = self.discovery_worker.start_discovery(p, is_folder=True)
        self._set_discovery_busy(True, f"Đang quét thư mục: {p.name}")

    def _clear_queue(self) -> None:
        if self.worker.is_running:
            return
        if self.discovery_worker.is_running:
            self.discovery_worker.cancel()
        self._active_discovery_token = 0
        self._set_discovery_busy(False)
        self.discovered_sources.clear()
        self._output_paths.clear()
        self._refresh_queue_table()
        self.source_var.set("Chưa chọn video hoặc thư mục.")
        self.status_var.set("Sẵn sàng.")
        self.progress_var.set(0.0)
        self.banner.dismiss()

    def _on_clear_sources(self) -> None:
        self._clear_queue()

    def _on_select_file(self) -> None:
        self._choose_file()

    def _on_select_folder(self) -> None:
        self._choose_folder()

    def _refresh_queue_table(self) -> None:
        for item in self.tree.get_children():
            self.tree.delete(item)

        count = len(self.discovered_sources)
        if count == 0:
            self.source_var.set("Chưa chọn video hoặc thư mục.")
            return

        if count == 1:
            fp = self.discovered_sources[0]
            self.source_var.set(f"File: {fp.basename}")
            self.tree.insert(
                "",
                "end",
                iid="ep_1",
                values=("1", fp.basename, "Sẵn sàng", "0%", "Sẵn sàng"),
            )
        else:
            self.source_var.set(f"Folder: {count} video")
            for idx, fp in enumerate(self.discovered_sources, start=1):
                self.tree.insert(
                    "",
                    "end",
                    iid=f"ep_{idx}",
                    values=(str(idx), fp.basename, "Sẵn sàng", "0%", "Sẵn sàng"),
                )
            if self.current_project_id and "season" in self.current_project_id:
                self.tree.insert(
                    "",
                    "end",
                    iid="season",
                    values=("Season", "Toàn bộ mùa phim", "Sẵn sàng", "0%", "Sẵn sàng"),
                )

    def _refresh_sources_table(self) -> None:
        self._refresh_queue_table()

    # -------------------------------------------------------------------------
    # WORKFLOW CONTROL (START / STOP / RESUME / JSON)
    # -------------------------------------------------------------------------
    def _on_start_project(self) -> None:
        if self.worker.is_running or self.discovery_worker.is_running:
            messagebox.showwarning("Đang thực hiện", "Một tác vụ đang chạy. Vui lòng chờ hoặc bấm Dừng.", parent=self)
            return

        if not self.discovered_sources:
            self.banner.show("Chưa có video nào trong danh sách. Hãy chọn file hoặc thư mục trước.", level="warning")
            return

        selected_paths = {str(Path(source.path).resolve()).casefold() for source in self.discovered_sources}
        for project in self.persistence.list_projects():
            if project.get("status") not in {status.value for status in ProjectStatus if status != ProjectStatus.COMPLETED}:
                continue
            saved_paths = {
                str(Path(entry["fingerprint"]["path"]).resolve()).casefold()
                for entry in project.get("sources", [])
                if isinstance(entry, dict) and isinstance(entry.get("fingerprint"), dict)
                and isinstance(entry["fingerprint"].get("path"), str)
            }
            if saved_paths and saved_paths == selected_paths:
                self._check_restart_projects(select_project_id=project["project_id"])
                self.banner.show(
                    f"Nguồn này đã thuộc dự án chưa hoàn thành '{project['project_id']}'. "
                    "Hãy dùng 'Tiếp tục dự án đã lưu'.",
                    level="warning",
                )
                return

        self.settings = self.settings_manager.load()
        if not self.settings.prompt.strip():
            ans = messagebox.askyesno(
                "Kịch bản đang để trống",
                "Kịch bản biên tập (Prompt) đang để trống. Bạn cần hướng dẫn biên tập để AI hiểu ý đồ recap.\n\n"
                "Bạn có muốn mở Cài đặt để nhập hoặc dùng Mẫu gợi ý ngay không?",
                parent=self,
            )
            if ans:
                self._on_open_settings()
            return

        now_str = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        first_path = Path(self.discovered_sources[0].path)
        if len(self.discovered_sources) == 1:
            stem = first_path.stem
            proj_name = stem
            clean_stem = "".join(c if c.isalnum() or c in "._-" else "_" for c in stem)[:24]
            proj_id = f"proj_{clean_stem}_{now_str}"
        else:
            parent_name = first_path.parent.name or "Season"
            proj_name = parent_name
            clean_parent = "".join(c if c.isalnum() or c in "._-" else "_" for c in parent_name)[:24]
            proj_id = f"season_{clean_parent}_{now_str}"

        self.current_project_id = proj_id
        self.current_project_name = proj_name

        self._refresh_queue_table()
        self._set_running_state(True)
        self.status_var.set(f"Bắt đầu dự án: {proj_name}")
        self._log(f"Khởi động dự án mới '{proj_name}' (ID: {proj_id})...")

        source_paths = [fp.path for fp in self.discovered_sources]
        out_dir = self.settings.output_dir if self.settings.output_dir.strip() else None

        self.worker.start_new_project(
            project_id=proj_id,
            project_name=proj_name,
            source_input=source_paths,
            prompt=self.settings.prompt,
            output_dir=out_dir,
            settings=self.settings,
        )

    def _on_stop_project(self) -> None:
        if self.discovery_worker.is_running:
            self.discovery_worker.cancel()
            self.status_var.set("Đang dừng tác vụ chọn nguồn...")
            self._log("Người dùng bấm Dừng chọn nguồn. Đang gửi tín hiệu hủy...")
            return

        if not self.worker.is_running:
            return

        ans = messagebox.askyesno(
            "Xác nhận dừng",
            "Bạn có chắc chắn muốn dừng tiến trình hiện tại không?\n"
            "Dự án sẽ dừng an toàn và lưu điểm dừng (checkpoint) để có thể tiếp tục sau.",
            parent=self,
        )
        if ans:
            self.status_var.set("Đang dừng các tác vụ và đóng tiến trình...")
            self._log("Người dùng bấm Dừng. Đang gửi tín hiệu hủy...")
            self.worker.cancel()

    def _on_resume_current(self) -> None:
        if self.worker.is_running or self.discovery_worker.is_running:
            return
        if not self.current_project_id:
            messagebox.showinfo("Tiếp tục", "Không có dự án đang hoạt động để tiếp tục.", parent=self)
            return

        self._set_running_state(True)
        self._log(f"Tiếp tục dự án '{self.current_project_id}'...")
        self.status_var.set(f"Tiếp tục dự án '{self.current_project_name or self.current_project_id}'...")
        self.worker.resume_project(
            project_id=self.current_project_id,
            output_dir=self.settings.output_dir or None,
            settings=self.settings,
        )

    def _on_render_existing_json(self) -> None:
        if self.worker.is_running or self.discovery_worker.is_running:
            messagebox.showwarning("Đang thực hiện", "Một tác vụ đang chạy. Vui lòng chờ hoặc bấm Dừng.", parent=self)
            return

        json_path_str = filedialog.askopenfilename(
            parent=self,
            title="Chọn tệp Final JSON có sẵn để dựng (0 AI)",
            filetypes=[("JSON Files", "*.json"), ("All Files", "*.*")],
        )
        if not json_path_str:
            return

        try:
            final_data = read_json(Path(json_path_str))
        except Exception as e:
            messagebox.showerror("Lỗi đọc JSON", f"Không thể đọc tệp JSON: {e}", parent=self)
            return

        if not self.discovered_sources:
            messagebox.showinfo(
                "Chọn video nguồn",
                "Vui lòng chọn tệp video hoặc thư mục chứa các video nguồn trước khi dùng tính năng dựng từ JSON.",
                parent=self,
            )
            return

        now_str = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        proj_id = f"import_{now_str}"
        proj_name = Path(json_path_str).stem

        self.current_project_id = proj_id
        self.current_project_name = proj_name

        self._refresh_queue_table()
        self._populate_outputs_from_json(final_data)
        self._set_running_state(True)
        self.status_var.set(f"Dựng từ JSON có sẵn: {proj_name}")
        self._log(f"Dựng từ JSON có sẵn '{proj_name}' (0 yêu cầu AI)...")

        source_paths = [fp.path for fp in self.discovered_sources]
        out_dir = self.settings.output_dir if self.settings.output_dir.strip() else None

        self.worker.render_existing_json(
            project_id=proj_id,
            project_name=proj_name,
            source_input=source_paths,
            final_json=final_data,
            output_dir=out_dir,
            settings=self.settings,
        )

    def _open_output_folder(self) -> None:
        target_dir = None
        if self.current_project_id:
            try:
                state = self.persistence.load_project(self.current_project_id)
                target_dir = state.get("output_dir")
            except Exception:
                pass

        if not target_dir:
            target_dir = self.settings.output_dir or str(self.persistence.root / "outputs")

        p = Path(target_dir).resolve()
        p.mkdir(parents=True, exist_ok=True)
        if sys.platform == "win32":
            os.startfile(str(p))
        else:
            subprocess.Popen(["xdg-open", str(p)])

    def _on_open_output_dir(self) -> None:
        self._open_output_folder()

    def _on_open_settings(self, initial_tab: Optional[int | str] = None) -> None:
        def _on_saved(new_settings: AppSettings) -> None:
            self.settings = new_settings
            self.banner.show("Đã lưu cài đặt thành công!", level="success")
            self._log("Cài đặt hệ thống đã được cập nhật.")

        SettingsDialog(
            parent=self,
            settings_manager=self.settings_manager,
            persistence=self.persistence,
            on_saved=_on_saved,
            initial_tab=initial_tab,
        )

    def _on_check_update(self) -> None:
        self._on_open_settings(initial_tab="update")

    def _manual_check_update(self) -> None:
        self._on_check_update()

    # -------------------------------------------------------------------------
    # RESTARTS / RESUME DETECTION
    # -------------------------------------------------------------------------
    def _show_persisted_project(self, project: Dict[str, Any]) -> None:
        project_id = project["project_id"]
        self.current_project_id = project_id
        self.current_project_name = project.get("project_name") or project_id
        self.discovered_sources.clear()
        self._output_paths.clear()
        for item in self.tree.get_children():
            self.tree.delete(item)
        sources = project.get("sources", [])
        for index, source in enumerate(sources, start=1):
            source_name = source.get("source_file", "") if isinstance(source, dict) else ""
            self.tree.insert(
                "", "end", iid=f"saved_ep_{index}",
                values=(str(index), source_name, project.get("status", ""), "", "Đã lưu"),
            )
        self.source_var.set(f"Dự án đã lưu: {self.current_project_name} ({len(sources)} video)")
        self.status_var.set(f"Có thể tiếp tục dự án '{self.current_project_name}' từ checkpoint đã lưu.")
        self.btn_resume.config(state="normal")

    def _on_select_resume_project(self, _event: Any = None) -> None:
        project_id = self._resume_project_ids.get(self.cmb_resume_projects.get())
        if not project_id:
            return
        try:
            self._show_persisted_project(self.persistence.load_project(project_id))
        except Exception as exc:
            self.banner.show(f"Không thể nạp dự án đã lưu: {exc}", level="error")

    def _check_restart_projects(self, *, select_project_id: str | None = None) -> None:
        """Detect any unfinished projects from past sessions and offer resume."""
        try:
            projects = self.persistence.list_projects()
            resumable: Dict[str, str] = {}
            statuses = {status.value for status in ProjectStatus if status != ProjectStatus.COMPLETED}
            for p in projects:
                status = p.get("status")
                project_id = p.get("project_id")
                if status in statuses and isinstance(project_id, str) and project_id:
                    name = p.get("project_name") or project_id
                    resumable[f"{name} — {project_id} ({status})"] = project_id

            if resumable:
                previous_id = select_project_id or self._resume_project_ids.get(self.cmb_resume_projects.get())
                self._resume_project_ids = resumable
                self.cmb_resume_projects.config(values=list(resumable))
                selected = next((label for label, project_id in resumable.items() if project_id == previous_id), None)
                if selected is None:
                    selected = next(iter(resumable))
                self.cmb_resume_projects.set(selected)
                if not self.resume_banner.winfo_manager():
                    self.resume_banner.pack(fill="x", pady=(8, 0))
                project_id = resumable[selected]
                self._show_persisted_project(self.persistence.load_project(project_id))
                self.banner.show(
                    f"Phát hiện dự án chưa hoàn thành: {project_id}. Chọn dự án và nhấn 'Tiếp tục dự án đã lưu'.",
                    level="info",
                )
            else:
                self._resume_project_ids = {}
                self.cmb_resume_projects.set("")
                self.cmb_resume_projects.config(values=[])
                self.resume_banner.pack_forget()
                self.btn_resume.config(state="disabled")
        except Exception as e:
            logger.warning("Failed to check restart projects: %s", e)

    def _on_resume_detected_project(self) -> None:
        if self.worker.is_running or self.discovery_worker.is_running:
            return
        proj_id = self._resume_project_ids.get(self.cmb_resume_projects.get())
        if not proj_id:
            return
        try:
            proj_data = self.persistence.load_project(proj_id)
            self._show_persisted_project(proj_data)

            final_json = proj_data.get("final_json")
            if final_json:
                self._populate_outputs_from_json(final_json)

            self._set_running_state(True)
            self._log(f"Tiếp tục thực hiện dự án: '{proj_id}'...")
            self.settings = self.settings_manager.load()
            self.worker.resume_project(
                project_id=proj_id,
                output_dir=self.settings.output_dir or None,
                settings=self.settings,
            )
        except Exception as e:
            messagebox.showerror("Lỗi nạp dự án", f"Không thể nạp dự án {proj_id}: {e}", parent=self)

    # -------------------------------------------------------------------------
    # QUEUE POLLING & DISPATCHING (THREAD SAFE)
    # -------------------------------------------------------------------------
    def _poll_queue(self) -> None:
        if getattr(self, "_is_closed", False):
            return
        try:
            while True:
                msg = self.msg_queue.get_nowait()
                self._handle_worker_message(msg)
        except queue.Empty:
            pass
        except Exception:
            pass
        finally:
            if not getattr(self, "_is_closed", False):
                self._poll_job = safe_after(self, 100, self._poll_queue)

    def _handle_worker_message(self, msg: WorkerMessage) -> None:
        kind = msg.kind
        data = msg.data

        if kind == "log":
            self._log(str(data))

        elif kind == "status_change":
            status = str(data)
            status_map = {
                ProjectStatus.CREATED.value: "Sẵn sàng phân tích (NEW)",
                ProjectStatus.NEW.value: "Sẵn sàng phân tích (NEW)",
                ProjectStatus.ANALYZING.value: "Đang phân tích video qua AI Gateway...",
                ProjectStatus.ANALYZED.value: "Đã phân tích xong kịch bản (JSON_READY)",
                ProjectStatus.JSON_READY.value: "Đã có kịch bản JSON (JSON_READY)",
                ProjectStatus.RENDERING.value: "Đang dựng video thành phẩm...",
                ProjectStatus.COMPLETED.value: "Đã hoàn thành toàn bộ dự án!",
                ProjectStatus.CANCELLED.value: "Đã dừng tiến trình tại điểm checkpoint.",
                ProjectStatus.FAILED.value: "Dự án gặp sự cố dừng lại.",
            }
            display_status = status_map.get(status, status)
            self.status_var.set(display_status)
            self.lbl_stage.config(text=f"Trạng thái: {display_status}")

            if status == ProjectStatus.ANALYZING.value:
                self.progress_var.set(25.0)
                for item in self.tree.get_children():
                    if item.startswith("ep_") or item == "season":
                        self.tree.set(item, "stage", "Analyzing")
                        self.tree.set(item, "status", "Đang phân tích")
            elif status in (ProjectStatus.ANALYZED.value, ProjectStatus.JSON_READY.value):
                self.progress_var.set(50.0)
                for item in self.tree.get_children():
                    if item.startswith("ep_") or item == "season":
                        self.tree.set(item, "stage", "Evidence Complete")
                        self.tree.set(item, "progress", "100%")
                        self.tree.set(item, "status", "Hoàn tất")
            elif status == ProjectStatus.RENDERING.value:
                self.progress_var.set(75.0)
            elif status == ProjectStatus.COMPLETED.value:
                self.progress_var.set(100.0)

        elif kind == "final_json":
            if isinstance(data, dict):
                self._populate_outputs_from_json(data)

        elif kind == "output_started":
            render_id = str(data)
            if self.tree.exists(render_id):
                self.tree.set(render_id, "stage", "Rendering")
                self.tree.set(render_id, "status", "Đang dựng...")
            elif self.tree.exists(f"out_{render_id}"):
                self.tree.set(f"out_{render_id}", "stage", "Rendering")
                self.tree.set(f"out_{render_id}", "status", "Đang dựng...")

        elif kind == "output_completed":
            info = data.get("data", {}) if isinstance(data, dict) else {}
            render_id = data.get("render_id", "") if isinstance(data, dict) else str(data)
            out_path = info.get("output_path", "")
            target_id = render_id if self.tree.exists(render_id) else f"out_{render_id}"
            if self.tree.exists(target_id):
                if out_path:
                    self.tree.set(target_id, "source_video", Path(out_path).name)
                    self._output_paths[target_id] = out_path
                    self._output_paths[render_id] = out_path
                self.tree.set(target_id, "stage", "Hoàn thành")
                self.tree.set(target_id, "progress", "100%")
                self.tree.set(target_id, "status", "Hoàn tất")

        elif kind == "output_skipped":
            info = data.get("data", {}) if isinstance(data, dict) else {}
            render_id = data.get("render_id", "") if isinstance(data, dict) else str(data)
            out_path = info.get("output_path", "")
            target_id = render_id if self.tree.exists(render_id) else f"out_{render_id}"
            if self.tree.exists(target_id):
                if out_path:
                    self.tree.set(target_id, "source_video", Path(out_path).name)
                    self._output_paths[target_id] = out_path
                    self._output_paths[render_id] = out_path
                self.tree.set(target_id, "stage", "Bỏ qua")
                self.tree.set(target_id, "progress", "100%")
                self.tree.set(target_id, "status", "Đã có sẵn")

        elif kind == "output_failed":
            render_id = data.get("render_id", "") if isinstance(data, dict) else str(data)
            err = data.get("error", "Lỗi dựng") if isinstance(data, dict) else ""
            target_id = render_id if self.tree.exists(render_id) else f"out_{render_id}"
            if self.tree.exists(target_id):
                self.tree.set(target_id, "stage", "Lỗi")
                self.tree.set(target_id, "status", f"Thất bại ({err[:30]})")

        elif kind == "error":
            clean_err = data.get("message", "Lỗi không xác định") if isinstance(data, dict) else str(data)
            self._log(f"LỖI: {clean_err}")
            self.banner.show(f"Lỗi: {clean_err}", level="error")

        elif kind == "gpu_status":
            self.gpu_status_var.set(str(data))

        elif kind == "discovery_progress":
            token = data.get("token") if isinstance(data, dict) else 0
            if token != self._active_discovery_token:
                return
            cur = data.get("current", 0)
            tot = data.get("total", 0)
            if tot > 0:
                self.status_var.set(f"Đang kiểm tra danh sách video ({cur}/{tot})...")

        elif kind == "discovery_completed":
            token = data.get("token") if isinstance(data, dict) else 0
            if token != self._active_discovery_token:
                return
            self._set_discovery_busy(False)
            fps = data.get("sources", [])
            p_name = data.get("name", "")
            d_kind = data.get("kind", "")

            if d_kind == "file":
                if not fps:
                    self.banner.show(f"File video không tồn tại: {p_name}", level="warning")
                    return
                self.discovered_sources = fps
                self.source_var.set(f"File: {p_name}")
                self._refresh_queue_table()
                self.status_var.set(f"Đã nạp file {p_name}. Nhấn 'Start Creating Recap Videos' để bắt đầu.")
                self.banner.show(f"Đã chọn file: {p_name} (SINGLE_EPISODE)", level="info")
            elif d_kind == "folder":
                if not fps:
                    self.discovered_sources.clear()
                    self._refresh_queue_table()
                    self.source_var.set(f"Folder: {p_name} (0 video)")
                    self.status_var.set("Không tìm thấy video nào được hỗ trợ.")
                    self.banner.show(f"Không tìm thấy video nào được hỗ trợ trực tiếp trong: {p_name}", level="warning")
                    return
                self.discovered_sources = fps
                self.source_var.set(f"Folder: {p_name} ({len(fps)} video)")
                self._refresh_queue_table()
                self.status_var.set(f"Đã nạp mùa phim {p_name} ({len(fps)} tập). Nhấn 'Start Creating Recap Videos' để bắt đầu.")
                self.banner.show(f"Đã tìm thấy {len(fps)} tập phim trong {p_name}. Sẵn sàng phân tích mùa phim!", level="success")

        elif kind == "discovery_cancelled":
            token = data.get("token") if isinstance(data, dict) else 0
            if token != self._active_discovery_token:
                return
            self._set_discovery_busy(False)
            self.status_var.set("Đã dừng tác vụ chọn nguồn.")
            self._log("Đã dừng tác vụ chọn nguồn.")

        elif kind == "discovery_failed":
            token = data.get("token") if isinstance(data, dict) else 0
            if token != self._active_discovery_token:
                return
            self._set_discovery_busy(False)
            err = data.get("error", "Lỗi nạp nguồn") if isinstance(data, dict) else str(data)
            self.status_var.set(f"Lỗi: {err}")
            lvl = "warning" if "không tồn tại" in err.lower() else "error"
            self.banner.show(f"{err}", level=lvl)
            self._log(f"Lỗi nạp nguồn: {err}")

        elif kind == "finished":
            status = data.get("status") if isinstance(data, dict) else ""
            self._set_running_state(False)

            hwnd = self.winfo_id() if self.settings.flash_taskbar else None
            proj_name = self.current_project_name or "Dự án"

            if status == ProjectStatus.COMPLETED.value:
                self.progress_var.set(100.0)
                msg = f"Đã hoàn thành toàn bộ dự án video recap thành công!"
                self.status_var.set(msg)
                self.banner.show(f"Đã hoàn thành toàn bộ dự án '{proj_name}' thành công!", level="success")
                if self.settings.notify_complete:
                    self.notification_service.notify_project_completed(
                        project_name=proj_name,
                        outputs_count=len(self._output_paths),
                        sound=self.settings.play_completion_sound,
                        hwnd=hwnd,
                        on_open_output=self._on_open_output_dir,
                    )
            elif status == ProjectStatus.CANCELLED.value:
                self.status_var.set("Đã dừng tiến trình tại điểm checkpoint.")
                self.banner.show("Tiến trình đã được dừng an toàn.", level="warning")
            elif status == ProjectStatus.FAILED.value:
                err_text = data.get("error", "Tiến trình bị gián đoạn") if isinstance(data, dict) else "Lỗi"
                self.status_var.set(f"Lỗi: {err_text}")
                self.banner.show(f"Lỗi: {err_text}", level="error")
                if self.settings.notify_error:
                    self.notification_service.notify_project_failed(
                        project_name=proj_name,
                        error_msg=err_text,
                        sound=self.settings.play_completion_sound,
                        hwnd=hwnd,
                    )

            self._check_restart_projects()

    def _populate_outputs_from_json(self, final_json: Dict[str, Any]) -> None:
        outputs = final_json.get("outputs", [])
        for i, out_def in enumerate(outputs, start=1):
            rid = out_def.get("render_id", f"render-{i}")
            title = out_def.get("title", f"Output {i}")
            out_name = f"{title}.mp4" if title else f"output_{i}.mp4"
            if not self.tree.exists(rid):
                self.tree.insert(
                    "",
                    "end",
                    iid=rid,
                    values=(f"Output {i}", out_name, "Chờ dựng", "0%", title),
                )
            else:
                self.tree.set(rid, "stage", "Chờ dựng")
                self.tree.set(rid, "status", title)

    def _on_double_click_tree(self, event: Any) -> None:
        item = self.tree.selection()
        if not item:
            return
        row_id = item[0]
        out_path = self._output_paths.get(row_id)
        if out_path:
            p = Path(out_path)
            if p.is_file():
                if sys.platform == "win32":
                    os.startfile(str(p))
                else:
                    subprocess.Popen(["xdg-open", str(p)])

    def _set_running_state(self, is_running: bool) -> None:
        if is_running:
            self.btn_start.config(state="disabled")
            self.btn_stop.config(state="normal")
            self.btn_resume.config(state="disabled")
            self.btn_render_json.config(state="disabled")
            self.btn_select_file.config(state="disabled")
            self.btn_select_folder.config(state="disabled")
            self.btn_clear.config(state="disabled")
        else:
            self.btn_start.config(state="normal")
            self.btn_stop.config(state="disabled")
            self.btn_resume.config(state="normal" if self.current_project_id else "disabled")
            self.btn_render_json.config(state="normal")
            self.btn_select_file.config(state="normal")
            self.btn_select_folder.config(state="normal")
            self.btn_clear.config(state="normal")

    def _log(self, message: str) -> None:
        now_str = datetime.now().strftime("%H:%M:%S")
        clean_text = f"[{now_str}] {message}\n"
        self.txt_log.config(state=tk.NORMAL)
        self.txt_log.insert(tk.END, clean_text)
        self.txt_log.see(tk.END)
        self.txt_log.config(state=tk.DISABLED)

    def _on_banner_dismissed(self) -> None:
        pass

    def _on_close(self) -> None:
        if self.worker.is_running:
            if not messagebox.askyesno(
                "Đang xử lý",
                "Đang có tiến trình hoạt động. Bạn có chắc chắn muốn dừng và thoát?\n"
                "Dự án sẽ được lưu điểm dừng (checkpoint) an toàn để có thể tiếp tục sau.",
                parent=self,
            ):
                return
            self._log("Đang hủy tác vụ an toàn trước khi đóng ứng dụng...")
            self.worker.cancel()
            if self.discovery_worker.is_running:
                self.discovery_worker.cancel()
            self._close_job = safe_after(self, 1500, self.destroy)
        else:
            if self.discovery_worker.is_running:
                self.discovery_worker.cancel()
            self.destroy()

    def cancel_owned_after(self) -> None:
        """Cancel pending after() callbacks owned by this window."""
        for job_attr in ("_poll_job", "_gpu_detect_job", "_close_job"):
            job = getattr(self, job_attr, None)
            if job:
                try:
                    self.after_cancel(job)
                except Exception:
                    pass
                setattr(self, job_attr, None)

        if hasattr(self, "banner") and getattr(self.banner, "_auto_dismiss_job", None):
            try:
                self.banner.after_cancel(self.banner._auto_dismiss_job)
            except Exception:
                pass
            self.banner._auto_dismiss_job = None

    def destroy(self) -> None:
        """Safe window destruction with closed guard, after cancellation, and worker stopping."""
        if getattr(self, "_is_closed", False):
            return
        self._is_closed = True

        self.cancel_owned_after()

        if hasattr(self, "discovery_worker") and self.discovery_worker.is_running:
            self.discovery_worker.cancel()
        if hasattr(self, "worker") and self.worker.is_running:
            self.worker.cancel()

        try:
            super().destroy()
        except Exception:
            pass


def run_app() -> None:
    """Single-click application entrypoint."""
    if "--selfcheck" in sys.argv:
        from toolrecap_v4.selfcheck import run_selfcheck

        sys.exit(run_selfcheck())
    if "--update-helper" in sys.argv:
        from toolrecap_v4.updater.helper import main
        sys.argv.remove("--update-helper")
        main()
        return
    if "--update-handshake" in sys.argv:
        print("TOOLRECAP_V4_HANDSHAKE_OK")
        sys.exit(0)
    app = MainWindow()
    app.mainloop()
