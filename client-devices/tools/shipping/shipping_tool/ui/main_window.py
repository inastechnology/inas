from __future__ import annotations

import queue
import threading
import tkinter as tk
from datetime import datetime
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from shipping_tool.domain.flash_layout import (
    FlashLayout,
    FlashRegion,
    FlashSelection,
    LayoutError,
)
from shipping_tool.domain.diagnostic_profile import (
    DiagnosticEngine,
    DiagnosticProfile,
    DiagnosticProfileError,
    discover_profiles,
)
from shipping_tool.domain.release_module import (
    LoadedReleaseModule,
    ReleaseModuleError,
    load_release_module,
)
from shipping_tool.services.esptool_service import EsptoolService
from shipping_tool.services.serial_console import (
    SerialConsoleService,
    encode_console_command,
)
from shipping_tool.services.serial_ports import SerialPortInfo, list_serial_ports

try:
    from tkinterdnd2 import DND_FILES
except ImportError:
    DND_FILES = None


COLORS = {
    "navy": "#0b1728",
    "blue": "#1769e0",
    "blue_hover": "#0e57c6",
    "surface": "#ffffff",
    "background": "#f4f7fb",
    "border": "#dce3ec",
    "text": "#182230",
    "muted": "#65758b",
    "success": "#168a54",
    "warning": "#b56a00",
    "danger": "#c23b3b",
    "log": "#0d1726",
}


class RegionRow:
    def __init__(
        self,
        owner: "ShippingToolWindow",
        parent: ttk.Frame,
        region: FlashRegion,
        row_index: int,
    ) -> None:
        self.owner = owner
        self.region = region
        self.file_path: Path | None = None
        self.enabled = tk.BooleanVar(value=region.default_enabled)
        self.file_text = tk.StringVar(value="BINをドロップ、またはクリック")
        self.status_text = tk.StringVar(value="未設定")

        self.checkbox = ttk.Checkbutton(parent, variable=self.enabled)
        self.checkbox.grid(row=row_index, column=0, padx=(8, 5), pady=7)
        region_text = region.label
        if region.description:
            region_text += f"\n{region.description}"
        ttk.Label(parent, text=region_text, style="Region.TLabel").grid(
            row=row_index, column=1, sticky="w", padx=5
        )
        ttk.Label(parent, text=f"0x{region.address:X}").grid(
            row=row_index, column=2, sticky="w", padx=5
        )
        size_text = (
            owner.format_size(region.max_size)
            if region.max_size is not None
            else "イメージ全体"
        )
        ttk.Label(parent, text=size_text).grid(
            row=row_index, column=3, sticky="w", padx=5
        )

        expected_names = " / ".join(region.accepted_names) or "任意の.bin"
        drop_text = f"{expected_names}\nクリックまたはD&D"
        self.file_text.set(drop_text)
        self.drop_label = tk.Label(
            parent,
            textvariable=self.file_text,
            bg="#f8fafc",
            fg=COLORS["muted"],
            relief="solid",
            borderwidth=1,
            padx=10,
            pady=6,
            cursor="hand2",
            anchor="w",
        )
        self.drop_label.grid(row=row_index, column=4, sticky="ew", padx=8, pady=5)
        self.drop_label.bind("<Button-1>", lambda _event: self.choose_file())
        if owner.drag_and_drop_available and DND_FILES is not None:
            self.drop_label.drop_target_register(DND_FILES)
            self.drop_label.dnd_bind("<<Drop>>", self.handle_drop)

        self.status_label = ttk.Label(
            parent, textvariable=self.status_text, style="Muted.TLabel"
        )
        self.status_label.grid(row=row_index, column=5, sticky="w", padx=8)

        if region.sensitive:
            self.enabled.set(False)
            self.status_text.set("任意・機密領域")
        elif region.required:
            self.status_text.set("必須")
        else:
            self.status_text.set("任意")

    def choose_file(self) -> None:
        path = filedialog.askopenfilename(
            title=f"{self.region.label}のBINを選択",
            filetypes=[("Binary image", "*.bin"), ("All files", "*.*")],
        )
        if path:
            self.assign_file(Path(path))

    def handle_drop(self, event: tk.Event) -> None:
        paths = self.owner.root.tk.splitlist(event.data)
        if paths:
            self.assign_file(Path(paths[0]))

    def assign_file(self, path: Path) -> None:
        if (
            self.region.accepted_names
            and path.name.casefold()
            not in {name.casefold() for name in self.region.accepted_names}
        ):
            expected = " / ".join(self.region.accepted_names)
            if not messagebox.askyesno(
                "ファイル名が一致しません",
                f"{self.region.label}の推奨ファイルは次です。\n\n"
                f"{expected}\n\n"
                f"選択されたファイル: {path.name}\n\n"
                "この領域へ設定しますか？",
                parent=self.owner.root,
            ):
                return
        try:
            selection = FlashSelection(self.region, path.resolve())
            selection.validate()
        except LayoutError as exc:
            messagebox.showerror("ファイルを使用できません", str(exc), parent=self.owner.root)
            return

        self.file_path = selection.file_path
        self.enabled.set(True)
        self.file_text.set(self.file_path.name)
        self.status_text.set(f"準備完了 • {self.owner.format_size(self.file_path.stat().st_size)}")
        self.drop_label.configure(bg="#eef9f3", fg=COLORS["success"])
        self.owner.update_summary()

    def selection(self) -> FlashSelection | None:
        if not self.enabled.get() or self.file_path is None:
            return None
        return FlashSelection(self.region, self.file_path)


class ShippingToolWindow:
    def __init__(
        self,
        root: tk.Tk,
        application_dir: Path,
        drag_and_drop_available: bool,
    ) -> None:
        self.root = root
        self.application_dir = application_dir
        self.drag_and_drop_available = drag_and_drop_available
        self.esptool = EsptoolService()
        self.console = SerialConsoleService(
            on_data=lambda text: self.events.put(("console_data", text)),
            on_state=lambda connected, detail: self.events.put(
                ("console_state", (connected, detail))
            ),
        )
        self.layout: FlashLayout | None = None
        self.region_rows: list[RegionRow] = []
        self.ports: list[SerialPortInfo] = []
        self.events: queue.Queue[tuple[str, object]] = queue.Queue()
        self.busy = False
        self.console_history = ""
        self.diagnostic_profiles = self.load_diagnostic_profiles()
        self.diagnostic_engine: DiagnosticEngine | None = None
        self.loaded_release_module: LoadedReleaseModule | None = None
        self.tab_scroll_canvases: dict[str, tk.Canvas] = {}
        self.tabs: ttk.Notebook | None = None

        self.port_text = tk.StringVar()
        self.baud_text = tk.StringVar(value="460800")
        self.layout_path_text = tk.StringVar()
        self.layout_status_text = tk.StringVar(value="配置ファイルを選択してください")
        self.connection_status_text = tk.StringVar(value="未接続")
        self.selection_summary_text = tk.StringVar(value="書込み対象 0件")
        self.erase_before_write = tk.BooleanVar(value=False)
        self.console_baud_text = tk.StringVar(value="115200")
        self.console_command_text = tk.StringVar()
        self.console_hex_mode = tk.BooleanVar(value=False)
        self.console_append_newline = tk.BooleanVar(value=True)
        self.console_status_text = tk.StringVar(value="切断")
        self.diagnostic_profile_text = tk.StringVar()
        self.diagnostic_summary_text = tk.StringVar(value="F/W種別を選択してください")

        self.configure_window()
        self.configure_styles()
        self.build_ui()
        self.refresh_ports()
        self.load_default_layout()
        self.root.protocol("WM_DELETE_WINDOW", self.close_window)
        self.root.after(100, self.process_events)

    def configure_window(self) -> None:
        self.root.title("INAS Shipping Tool")
        screen_width = self.root.winfo_screenwidth()
        screen_height = self.root.winfo_screenheight()
        initial_width = max(960, min(1280, screen_width - 80))
        initial_height = max(560, min(820, screen_height - 120))
        self.root.geometry(f"{initial_width}x{initial_height}")
        self.root.minsize(900, 520)
        self.root.configure(bg=COLORS["background"])

    def configure_styles(self) -> None:
        style = ttk.Style(self.root)
        if "clam" in style.theme_names():
            style.theme_use("clam")
        style.configure(".", font=("Yu Gothic UI", 10), foreground=COLORS["text"])
        style.configure("TFrame", background=COLORS["surface"])
        style.configure("Page.TFrame", background=COLORS["background"])
        style.configure("Header.TFrame", background=COLORS["navy"])
        style.configure(
            "Header.TLabel",
            background=COLORS["navy"],
            foreground="#ffffff",
            font=("Yu Gothic UI Semibold", 15),
        )
        style.configure("Title.TLabel", font=("Yu Gothic UI Semibold", 12))
        style.configure("Region.TLabel", font=("Yu Gothic UI Semibold", 10))
        style.configure("Muted.TLabel", foreground=COLORS["muted"])
        style.configure(
            "Primary.TButton",
            background=COLORS["blue"],
            foreground="#ffffff",
            font=("Yu Gothic UI Semibold", 10),
            padding=(16, 9),
        )
        style.map("Primary.TButton", background=[("active", COLORS["blue_hover"])])
        style.configure("TButton", padding=(10, 7))
        style.configure("TLabelframe", background=COLORS["surface"])
        style.configure(
            "TLabelframe.Label",
            background=COLORS["surface"],
            foreground=COLORS["blue"],
            font=("Yu Gothic UI Semibold", 10),
        )

    def build_ui(self) -> None:
        header = ttk.Frame(self.root, style="Header.TFrame")
        header.pack(fill="x")
        ttk.Label(header, text="▣  INAS Shipping Tool", style="Header.TLabel").pack(
            side="left", padx=20, pady=13
        )
        ttk.Label(
            header,
            text="ESP32-S3 出荷書込み",
            style="Header.TLabel",
            font=("Yu Gothic UI", 10),
        ).pack(side="right", padx=20)

        page = ttk.Frame(self.root, style="Page.TFrame", padding=14)
        page.pack(fill="both", expand=True)

        connection = ttk.LabelFrame(page, text="接続", padding=12)
        connection.pack(fill="x", pady=(0, 12))
        ttk.Label(connection, text="ポート").grid(row=0, column=0, padx=(0, 6))
        self.port_combo = ttk.Combobox(
            connection, textvariable=self.port_text, state="readonly", width=35
        )
        self.port_combo.grid(row=0, column=1, sticky="ew", padx=6)
        ttk.Button(connection, text="更新", command=self.refresh_ports).grid(
            row=0, column=2, padx=6
        )
        ttk.Label(connection, text="書込み速度").grid(row=0, column=3, padx=(20, 6))
        ttk.Combobox(
            connection,
            textvariable=self.baud_text,
            values=("115200", "230400", "460800", "921600"),
            state="readonly",
            width=12,
        ).grid(row=0, column=4, padx=6)
        self.connect_button = ttk.Button(
            connection, text="接続確認", command=self.connect_device
        )
        self.connect_button.grid(row=0, column=5, padx=(20, 6))
        ttk.Label(
            connection, textvariable=self.connection_status_text, style="Muted.TLabel"
        ).grid(row=0, column=6, padx=8)
        connection.columnconfigure(1, weight=1)

        tabs = ttk.Notebook(page)
        tabs.pack(fill="both", expand=True)
        self.tabs = tabs
        flash_tab = self.create_scrollable_tab(
            tabs, "  F/W書込み  ", padding=12
        )
        console_tab = self.create_scrollable_tab(
            tabs, "  コンソール  ", padding=12
        )
        diagnostic_tab = self.create_scrollable_tab(
            tabs, "  ステータス診断  ", padding=12
        )
        settings_tab = self.create_scrollable_tab(
            tabs, "  デバイス設定（将来）  ", padding=24
        )
        self.root.bind_all("<MouseWheel>", self.scroll_active_tab, add="+")
        self.root.bind_all("<Button-4>", self.scroll_active_tab, add="+")
        self.root.bind_all("<Button-5>", self.scroll_active_tab, add="+")
        ttk.Label(
            settings_tab,
            text="RS485アドレス・baud rateなどの出荷設定をここへ追加します。",
            style="Title.TLabel",
        ).pack(anchor="w")
        ttk.Label(
            settings_tab,
            text="書込み機能と分離したサービスとして実装できる構造になっています。",
            style="Muted.TLabel",
        ).pack(anchor="w", pady=(8, 0))

        layout_frame = ttk.LabelFrame(flash_tab, text="フラッシュ配置", padding=10)
        layout_frame.pack(fill="x")
        self.layout_entry = ttk.Entry(
            layout_frame, textvariable=self.layout_path_text, state="readonly"
        )
        self.layout_entry.grid(row=0, column=0, sticky="ew", padx=(0, 8))
        ttk.Button(layout_frame, text="配置JSONを開く", command=self.choose_layout).grid(
            row=0, column=2
        )
        ttk.Button(
            layout_frame,
            text="F/Wパッケージを開く",
            style="Primary.TButton",
            command=self.choose_release_module,
        ).grid(
            row=0, column=1, padx=(0, 8)
        )
        ttk.Label(
            layout_frame, textvariable=self.layout_status_text, style="Muted.TLabel"
        ).grid(row=1, column=0, columnspan=3, sticky="w", pady=(7, 0))
        layout_frame.columnconfigure(0, weight=1)

        bulk_frame = ttk.Frame(flash_tab, padding=(0, 10, 0, 0))
        bulk_frame.pack(fill="x")
        self.bulk_drop_label = tk.Label(
            bulk_frame,
            text=".inasfw F/Wパッケージ、または複数のBINをここへD&D\n"
            "manifestまたはファイル名から書込み先を自動設定します",
            bg="#edf4ff",
            fg=COLORS["blue"],
            relief="solid",
            borderwidth=1,
            padx=16,
            pady=10,
            cursor="hand2",
        )
        self.bulk_drop_label.pack(side="left", fill="x", expand=True)
        self.bulk_drop_label.bind("<Button-1>", lambda _event: self.choose_multiple_files())
        if self.drag_and_drop_available and DND_FILES is not None:
            self.bulk_drop_label.drop_target_register(DND_FILES)
            self.bulk_drop_label.dnd_bind("<<Drop>>", self.handle_bulk_drop)
        ttk.Button(
            bulk_frame, text="BINをまとめて選択", command=self.choose_multiple_files
        ).pack(side="right", padx=(10, 0))

        self.region_frame = ttk.LabelFrame(
            flash_tab, text="書込み領域とBINファイル", padding=8
        )
        self.region_frame.pack(fill="both", expand=True, pady=10)

        actions = ttk.Frame(flash_tab)
        actions.pack(fill="x")
        ttk.Checkbutton(
            actions,
            text="書込み前にフラッシュ全体を消去",
            variable=self.erase_before_write,
        ).pack(side="left")
        ttk.Label(
            actions, textvariable=self.selection_summary_text, style="Muted.TLabel"
        ).pack(side="left", padx=18)
        ttk.Button(actions, text="選択解除", command=self.clear_selection).pack(
            side="right", padx=5
        )
        self.verify_button = ttk.Button(
            actions, text="検証", command=self.verify_selected
        )
        self.verify_button.pack(side="right", padx=5)
        self.flash_button = ttk.Button(
            actions,
            text="⚡ 書込み開始",
            style="Primary.TButton",
            command=self.flash_selected,
        )
        self.flash_button.pack(side="right", padx=5)

        log_frame = ttk.LabelFrame(flash_tab, text="ログ", padding=8)
        log_frame.pack(fill="both", expand=True, pady=(10, 0))
        self.log_text = tk.Text(
            log_frame,
            height=10,
            bg=COLORS["log"],
            fg="#d4e3f6",
            insertbackground="#ffffff",
            font=("Cascadia Mono", 9),
            relief="flat",
            state="disabled",
        )
        scrollbar = ttk.Scrollbar(log_frame, command=self.log_text.yview)
        self.log_text.configure(yscrollcommand=scrollbar.set)
        self.log_text.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        if not self.drag_and_drop_available:
            self.log(
                "tkinterdnd2がないためD&Dは無効です。pip install -r requirements.txt "
                "後に再起動してください。クリックによる選択は使用できます。"
            )

        self.build_console_tab(console_tab)
        self.build_diagnostic_tab(diagnostic_tab)

    def create_scrollable_tab(
        self,
        notebook: ttk.Notebook,
        title: str,
        *,
        padding: int,
    ) -> ttk.Frame:
        container = ttk.Frame(notebook)
        notebook.add(container, text=title)
        canvas = tk.Canvas(
            container,
            background=COLORS["surface"],
            highlightthickness=0,
            borderwidth=0,
        )
        scrollbar = ttk.Scrollbar(
            container,
            orient="vertical",
            command=canvas.yview,
        )
        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        content = ttk.Frame(canvas, padding=padding)
        content_window = canvas.create_window(
            (0, 0),
            window=content,
            anchor="nw",
        )
        content.bind(
            "<Configure>",
            lambda _event, target=canvas: target.configure(
                scrollregion=target.bbox("all")
            ),
        )
        canvas.bind(
            "<Configure>",
            lambda event, target=canvas, item=content_window: target.itemconfigure(
                item,
                width=event.width,
            ),
        )
        self.tab_scroll_canvases[str(container)] = canvas
        return content

    def scroll_active_tab(self, event: tk.Event) -> str | None:
        if self.tabs is None:
            return None
        widget = getattr(event, "widget", None)
        if isinstance(widget, (tk.Text, ttk.Treeview, ttk.Combobox)):
            return None
        canvas = self.tab_scroll_canvases.get(self.tabs.select())
        if canvas is None:
            return None
        if getattr(event, "num", None) == 4:
            direction = -1
        elif getattr(event, "num", None) == 5:
            direction = 1
        else:
            delta = int(getattr(event, "delta", 0))
            if delta == 0:
                return None
            direction = -1 if delta > 0 else 1
        canvas.yview_scroll(direction * 3, "units")
        return "break"

    def load_diagnostic_profiles(self) -> list[DiagnosticProfile]:
        search_paths = [self.application_dir / "profiles"]
        client_devices_dir = self.application_dir.parents[1]
        search_paths.extend(
            path / "shipping"
            for path in client_devices_dir.glob("*-device")
            if path.is_dir()
        )
        try:
            return discover_profiles(search_paths)
        except DiagnosticProfileError as exc:
            messagebox.showerror("診断プロファイルエラー", str(exc), parent=self.root)
            return []

    def build_console_tab(self, parent: ttk.Frame) -> None:
        controls = ttk.LabelFrame(parent, text="USB Debug COM", padding=10)
        controls.pack(fill="x")
        ttk.Label(
            controls,
            text="上部の「接続」で選択したCOMポートを使用します。",
            style="Muted.TLabel",
        ).grid(row=0, column=0, columnspan=5, sticky="w", pady=(0, 8))
        ttk.Label(controls, text="通信速度").grid(row=1, column=0, padx=(0, 6))
        ttk.Combobox(
            controls,
            textvariable=self.console_baud_text,
            values=("4800", "9600", "57600", "115200", "230400"),
            width=12,
        ).grid(row=1, column=1, padx=6)
        self.console_connect_button = ttk.Button(
            controls, text="コンソール接続", command=self.toggle_console
        )
        self.console_connect_button.grid(row=1, column=2, padx=8)
        ttk.Label(
            controls,
            textvariable=self.console_status_text,
            style="Muted.TLabel",
        ).grid(row=1, column=3, sticky="w", padx=8)
        ttk.Button(controls, text="ログを消去", command=self.clear_console_log).grid(
            row=1, column=4, sticky="e"
        )
        controls.columnconfigure(3, weight=1)

        terminal_frame = ttk.LabelFrame(parent, text="コンソールログ", padding=8)
        terminal_frame.pack(fill="both", expand=True, pady=10)
        self.console_text = tk.Text(
            terminal_frame,
            bg=COLORS["log"],
            fg="#d4e3f6",
            insertbackground="#ffffff",
            font=("Cascadia Mono", 10),
            relief="flat",
            wrap="word",
            state="disabled",
        )
        console_scrollbar = ttk.Scrollbar(
            terminal_frame, command=self.console_text.yview
        )
        self.console_text.configure(yscrollcommand=console_scrollbar.set)
        self.console_text.pack(side="left", fill="both", expand=True)
        console_scrollbar.pack(side="right", fill="y")

        send_frame = ttk.LabelFrame(parent, text="コマンド送信", padding=10)
        send_frame.pack(fill="x")
        self.console_command_entry = ttk.Entry(
            send_frame, textvariable=self.console_command_text
        )
        self.console_command_entry.grid(
            row=0, column=0, columnspan=3, sticky="ew", padx=(0, 8)
        )
        self.console_command_entry.bind("<Return>", lambda _event: self.send_console())
        self.console_send_button = ttk.Button(
            send_frame,
            text="送信",
            style="Primary.TButton",
            command=self.send_console,
        )
        self.console_send_button.grid(row=0, column=3)
        ttk.Checkbutton(
            send_frame,
            text="16進バイト列",
            variable=self.console_hex_mode,
            command=self.update_console_mode_hint,
        ).grid(row=1, column=0, sticky="w", pady=(8, 0))
        ttk.Checkbutton(
            send_frame,
            text="末尾にCRLF",
            variable=self.console_append_newline,
        ).grid(row=1, column=1, sticky="w", pady=(8, 0))
        self.console_hint = ttk.Label(
            send_frame,
            text="例: scan  （Enterでも送信）",
            style="Muted.TLabel",
        )
        self.console_hint.grid(
            row=1, column=2, columnspan=2, sticky="e", pady=(8, 0)
        )
        send_frame.columnconfigure(0, weight=1)
        send_frame.columnconfigure(2, weight=1)

    def build_diagnostic_tab(self, parent: ttk.Frame) -> None:
        selector = ttk.LabelFrame(parent, text="F/W種別", padding=10)
        selector.pack(fill="x")
        profile_names = [profile.display_name for profile in self.diagnostic_profiles]
        self.diagnostic_profile_combo = ttk.Combobox(
            selector,
            textvariable=self.diagnostic_profile_text,
            values=profile_names,
            state="readonly",
            width=45,
        )
        self.diagnostic_profile_combo.pack(side="left", padx=(0, 8))
        self.diagnostic_profile_combo.bind(
            "<<ComboboxSelected>>", lambda _event: self.select_diagnostic_profile()
        )
        ttk.Button(selector, text="診断結果をリセット", command=self.reset_diagnostics).pack(
            side="right"
        )
        ttk.Label(
            selector,
            textvariable=self.diagnostic_summary_text,
            style="Muted.TLabel",
        ).pack(side="left", padx=10)

        content = ttk.Frame(parent)
        content.pack(fill="both", expand=True, pady=(10, 0))
        content.columnconfigure(0, weight=1)
        content.columnconfigure(1, weight=1)
        content.rowconfigure(0, weight=1)

        status_frame = ttk.LabelFrame(content, text="現在のステータス", padding=8)
        status_frame.grid(row=0, column=0, sticky="nsew", padx=(0, 5))
        self.diagnostic_status_tree = ttk.Treeview(
            status_frame,
            columns=("label", "value"),
            show="headings",
            height=12,
        )
        self.diagnostic_status_tree.heading("label", text="項目")
        self.diagnostic_status_tree.heading("value", text="状態・値")
        self.diagnostic_status_tree.column("label", width=180)
        self.diagnostic_status_tree.column("value", width=220)
        self.diagnostic_status_tree.tag_configure("ok", foreground=COLORS["success"])
        self.diagnostic_status_tree.tag_configure(
            "warning", foreground=COLORS["warning"]
        )
        self.diagnostic_status_tree.tag_configure("error", foreground=COLORS["danger"])
        self.diagnostic_status_tree.pack(fill="both", expand=True)

        device_frame = ttk.LabelFrame(
            content, text="認識されたRS485デバイス", padding=8
        )
        device_frame.grid(row=0, column=1, sticky="nsew", padx=(5, 0))
        self.diagnostic_device_tree = ttk.Treeview(
            device_frame,
            columns=("device",),
            show="headings",
            height=12,
        )
        self.diagnostic_device_tree.heading("device", text="デバイス")
        self.diagnostic_device_tree.column("device", width=400)
        self.diagnostic_device_tree.pack(fill="both", expand=True)

        error_frame = ttk.LabelFrame(parent, text="エラー・要確認ログ", padding=8)
        error_frame.pack(fill="both", expand=True, pady=(10, 0))
        self.diagnostic_error_text = tk.Text(
            error_frame,
            height=8,
            bg="#fff8f6",
            fg=COLORS["danger"],
            font=("Cascadia Mono", 9),
            relief="flat",
            state="disabled",
        )
        self.diagnostic_error_text.pack(fill="both", expand=True)

        if profile_names:
            self.diagnostic_profile_combo.current(0)
            self.select_diagnostic_profile()

    def load_default_layout(self) -> None:
        ota_layout = self.application_dir / "configs" / "xiao_esp32s3_ota.json"
        if ota_layout.is_file():
            self.load_layout(ota_layout)

    def choose_release_module(self) -> None:
        path = filedialog.askopenfilename(
            title="INAS F/Wパッケージを選択",
            filetypes=[
                ("INAS firmware package", "*.inasfw"),
                ("Legacy release module ZIP", "*.zip"),
                ("All files", "*.*"),
            ],
        )
        if path:
            self.open_release_module(Path(path))

    def open_release_module(self, path: Path) -> None:
        module: LoadedReleaseModule | None = None
        try:
            module = load_release_module(path)
            profile = (
                DiagnosticProfile.load(module.diagnostic_profile_path)
                if module.diagnostic_profile_path is not None
                else None
            )
        except (ReleaseModuleError, DiagnosticProfileError, OSError) as exc:
            messagebox.showerror(
                "Release moduleエラー",
                str(exc),
                parent=self.root,
            )
            if module is not None:
                module.close()
            self.log(f"Release moduleを読み込めません: {exc}")
            return

        assert module is not None
        previous_module = self.loaded_release_module
        self.loaded_release_module = module
        self.layout = module.layout
        self.layout_path_text.set(str(module.source_archive))
        self.layout_status_text.set(
            f"Release module: {module.display_name} "
            f"{module.firmware_version} • {module.target}"
        )
        self.rebuild_region_rows()
        for row in self.region_rows:
            image_path = module.files_by_region.get(row.region.region_id)
            if image_path is None:
                continue
            row.assign_file(image_path)
            row.enabled.set(row.region.default_enabled)
        self.update_summary()

        if profile is not None:
            profiles_by_id = {
                item.profile_id: item for item in self.diagnostic_profiles
            }
            profiles_by_id[profile.profile_id] = profile
            self.diagnostic_profiles = sorted(
                profiles_by_id.values(),
                key=lambda item: item.display_name,
            )
            self.diagnostic_profile_combo["values"] = [
                item.display_name for item in self.diagnostic_profiles
            ]
        if module.diagnostic_profile_id:
            self.select_diagnostic_profile_by_id(module.diagnostic_profile_id)

        if previous_module is not None:
            previous_module.close()
        self.log(
            f"Release moduleを読み込みました: {module.display_name} "
            f"{module.firmware_version}"
        )
        self.log(f"Release module SHA-256: {module.archive_sha256}")

    def choose_layout(self) -> None:
        path = filedialog.askopenfilename(
            title="フラッシュ配置JSONを選択",
            initialdir=self.application_dir / "configs",
            filetypes=[("Flash layout", "*.json"), ("All files", "*.*")],
        )
        if path:
            self.load_layout(Path(path))

    def load_layout(self, path: Path) -> None:
        try:
            layout = FlashLayout.load(path)
        except LayoutError as exc:
            messagebox.showerror("配置ファイルエラー", str(exc), parent=self.root)
            self.log(f"配置ファイルエラー: {exc}")
            return
        self.layout = layout
        self.layout_path_text.set(str(layout.source_path))
        self.layout_status_text.set(
            f"読込み済み: {layout.name} • chip={layout.chip} • {len(layout.regions)}領域"
        )
        self.rebuild_region_rows()
        self.log(f"配置を読み込みました: {layout.name}")

    def rebuild_region_rows(self) -> None:
        for child in self.region_frame.winfo_children():
            child.destroy()
        self.region_rows.clear()
        headers = (
            "有効",
            "書込み領域",
            "アドレス",
            "最大サイズ",
            "ここへ置くBIN（推奨名）",
            "状態",
        )
        for column, text in enumerate(headers):
            ttk.Label(self.region_frame, text=text, style="Title.TLabel").grid(
                row=0, column=column, sticky="w", padx=8, pady=(2, 6)
            )
        self.region_frame.columnconfigure(4, weight=1)
        if self.layout is None:
            return
        for index, region in enumerate(self.layout.regions, start=1):
            self.region_rows.append(RegionRow(self, self.region_frame, region, index))
        self.update_summary()

    def refresh_ports(self) -> None:
        self.ports = list_serial_ports()
        values = [port.display_name for port in self.ports]
        self.port_combo["values"] = values
        if values:
            current_device = self.selected_port()
            selected_index = 0
            if current_device:
                for index, port in enumerate(self.ports):
                    if port.device == current_device:
                        selected_index = index
                        break
            self.port_combo.current(selected_index)
            self.connection_status_text.set(f"{len(values)}ポート検出")
        else:
            self.port_text.set("")
            self.connection_status_text.set("ポートなし")
        self.log(f"シリアルポートを更新: {len(values)}件")

    def choose_multiple_files(self) -> None:
        paths = filedialog.askopenfilenames(
            title="書き込むBINをまとめて選択",
            filetypes=[("Binary images", "*.bin"), ("All files", "*.*")],
        )
        if paths:
            self.auto_assign_files([Path(path) for path in paths])

    def handle_bulk_drop(self, event: tk.Event) -> None:
        paths = [Path(path) for path in self.root.tk.splitlist(event.data)]
        release_modules = [
            path
            for path in paths
            if path.suffix.casefold() in {".inasfw", ".zip"}
        ]
        if len(release_modules) > 1:
            messagebox.showwarning(
                "Release moduleを1つ選択してください",
                "同時に読み込めるF/Wパッケージは1つです。",
                parent=self.root,
            )
            return
        if release_modules:
            self.open_release_module(release_modules[0])
        binary_paths = [
            path for path in paths if path.suffix.casefold() == ".bin"
        ]
        if binary_paths:
            self.auto_assign_files(binary_paths)

    def auto_assign_files(self, paths: list[Path]) -> None:
        if self.layout is None:
            messagebox.showwarning(
                "配置が未選択です",
                "先にFlash layout JSONを選択してください。",
                parent=self.root,
            )
            return

        assigned: list[str] = []
        unresolved: list[str] = []
        for path in paths:
            matching = self.layout.matching_regions(path.name)
            if not matching:
                unresolved.append(path.name)
                continue
            for region in matching:
                row = next(
                    (item for item in self.region_rows if item.region.region_id == region.region_id),
                    None,
                )
                if row is not None:
                    row.assign_file(path)
                    assigned.append(f"{path.name} → {region.label}")

        if assigned:
            self.log("BINを自動配置しました:")
            for item in assigned:
                self.log(f"  {item}")
        if unresolved:
            messagebox.showwarning(
                "自動配置できないファイル",
                "配置JSONの推奨ファイル名と一致しませんでした。\n\n"
                + "\n".join(unresolved)
                + "\n\n対象の領域行へ個別にD&Dしてください。",
                parent=self.root,
            )
            self.log("自動配置できませんでした: " + ", ".join(unresolved))
        self.update_summary()

    def selected_port(self) -> str:
        display = self.port_text.get()
        for port in self.ports:
            if port.display_name == display:
                return port.device
        return display.split(" — ", 1)[0].strip()

    def selected_baud(self) -> int:
        try:
            return int(self.baud_text.get())
        except ValueError as exc:
            raise ValueError("書込み速度が不正です") from exc

    def selected_files(self) -> list[FlashSelection]:
        return [
            selection
            for row in self.region_rows
            if (selection := row.selection()) is not None
        ]

    def validate_operation(self, require_files: bool = True) -> tuple[str, int]:
        if self.layout is None:
            raise ValueError("フラッシュ配置を選択してください")
        port = self.selected_port()
        if not port:
            raise ValueError("書込みポートを選択してください")
        baud = self.selected_baud()
        if require_files:
            selections = self.selected_files()
            if not selections:
                raise ValueError("書き込むBINファイルを1つ以上選択してください")
            missing_required = [
                row.region.label
                for row in self.region_rows
                if row.enabled.get() and row.region.required and row.file_path is None
            ]
            if missing_required:
                raise ValueError("必須ファイルが未設定です: " + ", ".join(missing_required))
            for selection in selections:
                selection.validate()
        return port, baud

    def connect_device(self) -> None:
        self.disconnect_console()
        try:
            port, baud = self.validate_operation(require_files=False)
            assert self.layout is not None
            command = self.esptool.build_chip_id_command(self.layout.chip, port, baud)
        except (ValueError, LayoutError) as exc:
            messagebox.showwarning("接続確認", str(exc), parent=self.root)
            return
        self.run_command(command, "接続確認")

    def flash_selected(self) -> None:
        self.disconnect_console()
        try:
            port, baud = self.validate_operation()
            assert self.layout is not None
            selections = self.selected_files()
            sensitive = [item.region.label for item in selections if item.region.sensitive]
            erase = self.erase_before_write.get()
            warning_parts = [
                f"{len(selections)}領域を {port} に書き込みます。",
                "選択した領域の既存内容は上書きされます。",
            ]
            if sensitive:
                warning_parts.append("機密領域を含みます: " + ", ".join(sensitive))
            if erase:
                warning_parts.append(
                    "「全体消去」が有効です。NVS、設定、全F/Wを含むフラッシュ全体が消去されます。"
                )
            if not messagebox.askyesno(
                "書込み確認", "\n\n".join(warning_parts), parent=self.root
            ):
                return
            if erase:
                erase_command = self.esptool.build_write_command(
                    self.layout, port, baud, selections, erase_all=True
                )
                self.run_sequence(
                    [
                        ("フラッシュ全体消去", erase_command),
                        (
                            "F/W書込み",
                            self.esptool.build_write_command(
                                self.layout, port, baud, selections, erase_all=False
                            ),
                        ),
                    ]
                )
            else:
                self.run_command(
                    self.esptool.build_write_command(
                        self.layout, port, baud, selections, erase_all=False
                    ),
                    "F/W書込み",
                )
        except (ValueError, LayoutError) as exc:
            messagebox.showwarning("書込みできません", str(exc), parent=self.root)

    def verify_selected(self) -> None:
        self.disconnect_console()
        try:
            port, baud = self.validate_operation()
            assert self.layout is not None
            command = self.esptool.build_verify_command(
                self.layout, port, baud, self.selected_files()
            )
        except (ValueError, LayoutError) as exc:
            messagebox.showwarning("検証できません", str(exc), parent=self.root)
            return
        self.run_command(command, "書込み検証")

    def run_sequence(self, operations: list[tuple[str, list[str]]]) -> None:
        if self.busy:
            return
        self.set_busy(True)

        def worker() -> None:
            for operation_name, command in operations:
                self.events.put(("log", f"--- {operation_name} ---"))
                result = self.esptool.run(
                    command, lambda line: self.events.put(("log", line))
                )
                if result.returncode != 0:
                    self.events.put(
                        ("done", (False, operation_name, result.returncode))
                    )
                    return
            self.events.put(("done", (True, operations[-1][0], 0)))

        threading.Thread(target=worker, daemon=True).start()

    def run_command(self, command: list[str], operation_name: str) -> None:
        self.run_sequence([(operation_name, command)])

    def process_events(self) -> None:
        try:
            while True:
                event_type, payload = self.events.get_nowait()
                if event_type == "log":
                    self.log(str(payload))
                elif event_type == "done":
                    success, operation, returncode = payload
                    self.set_busy(False)
                    if success:
                        self.connection_status_text.set(f"{operation} 完了")
                        self.log(f"{operation}が完了しました。")
                    else:
                        self.connection_status_text.set(f"{operation} 失敗")
                        self.log(f"{operation}に失敗しました。終了コード={returncode}")
                elif event_type == "console_data":
                    console_data = str(payload)
                    self.console_history = (self.console_history + console_data)[-1_000_000:]
                    self.append_console(console_data)
                    if (
                        self.diagnostic_engine is not None
                        and self.diagnostic_engine.feed(console_data)
                    ):
                        self.refresh_diagnostics()
                elif event_type == "console_state":
                    connected, detail = payload
                    self.console_status_text.set(str(detail))
                    self.console_connect_button.configure(
                        text="切断" if connected else "コンソール接続"
                    )
                    self.append_console(
                        f"\n--- {'接続' if connected else '切断'}: {detail} ---\n"
                    )
        except queue.Empty:
            pass
        self.root.after(100, self.process_events)

    def set_busy(self, busy: bool) -> None:
        self.busy = busy
        state = "disabled" if busy else "normal"
        self.flash_button.configure(state=state)
        self.verify_button.configure(state=state)
        self.connect_button.configure(state=state)
        if busy:
            self.connection_status_text.set("処理中…")

    def clear_selection(self) -> None:
        for row in self.region_rows:
            row.enabled.set(False)
        self.update_summary()

    def toggle_console(self) -> None:
        if self.console.connected:
            self.disconnect_console()
            return
        port = self.selected_port()
        if not port:
            messagebox.showwarning(
                "コンソール接続",
                "上部の接続欄でCOMポートを選択してください。",
                parent=self.root,
            )
            return
        try:
            baud = int(self.console_baud_text.get())
            if baud <= 0:
                raise ValueError("通信速度は正の整数で指定してください")
            self.console.connect(port, baud)
        except (ValueError, RuntimeError, OSError) as exc:
            messagebox.showerror(
                "コンソール接続エラー",
                f"{exc}\n\nTera Termなどが同じCOMポートを開いていないか確認してください。",
                parent=self.root,
            )

    def disconnect_console(self) -> None:
        if self.console.connected:
            self.console.disconnect()

    def send_console(self) -> None:
        value = self.console_command_text.get()
        if not value:
            return
        try:
            payload = encode_console_command(
                value,
                hex_mode=self.console_hex_mode.get(),
                append_newline=self.console_append_newline.get(),
            )
            self.console.write(payload)
        except (ValueError, RuntimeError, OSError) as exc:
            messagebox.showerror("送信エラー", str(exc), parent=self.root)
            return

        if self.console_hex_mode.get():
            shown = " ".join(f"{byte:02X}" for byte in payload)
            self.append_console(f"\nTX HEX> {shown}\n")
        else:
            self.append_console(f"\nTX> {value}\n")
        self.console_command_text.set("")

    def update_console_mode_hint(self) -> None:
        if self.console_hex_mode.get():
            self.console_hint.configure(text="例: 01 03 00 00 00 07 04 08")
        else:
            self.console_hint.configure(text="例: scan  （Enterでも送信）")

    def append_console(self, text: str) -> None:
        self.console_text.configure(state="normal")
        self.console_text.insert("end", text)
        self.console_text.see("end")
        self.console_text.configure(state="disabled")

    def clear_console_log(self) -> None:
        self.console_history = ""
        self.console_text.configure(state="normal")
        self.console_text.delete("1.0", "end")
        self.console_text.configure(state="disabled")
        self.reset_diagnostics()

    def select_diagnostic_profile(self) -> None:
        display_name = self.diagnostic_profile_text.get()
        profile = next(
            (
                item
                for item in self.diagnostic_profiles
                if item.display_name == display_name
            ),
            None,
        )
        if profile is None:
            return
        self.diagnostic_engine = DiagnosticEngine(profile)
        if self.console_history:
            self.diagnostic_engine.feed(self.console_history + "\n")
        self.console_baud_text.set(str(profile.console_baud))
        self.diagnostic_summary_text.set(
            f"{profile.display_name} • ログ速度 {profile.console_baud}bps"
        )
        self.refresh_diagnostics()

    def select_diagnostic_profile_by_id(self, profile_id: str) -> None:
        for index, profile in enumerate(self.diagnostic_profiles):
            if profile.profile_id != profile_id:
                continue
            self.diagnostic_profile_combo.current(index)
            self.select_diagnostic_profile()
            return

    def reset_diagnostics(self) -> None:
        if self.diagnostic_engine is not None:
            self.diagnostic_engine.reset()
        self.refresh_diagnostics()

    def refresh_diagnostics(self) -> None:
        for item in self.diagnostic_status_tree.get_children():
            self.diagnostic_status_tree.delete(item)
        for item in self.diagnostic_device_tree.get_children():
            self.diagnostic_device_tree.delete(item)
        self.diagnostic_error_text.configure(state="normal")
        self.diagnostic_error_text.delete("1.0", "end")

        engine = self.diagnostic_engine
        if engine is None:
            self.diagnostic_error_text.configure(state="disabled")
            return
        for field_id, status in engine.statuses.items():
            self.diagnostic_status_tree.insert(
                "",
                "end",
                iid=field_id,
                values=(status.label, status.value),
                tags=(status.severity,),
            )
        for identity, display in engine.devices.items():
            self.diagnostic_device_tree.insert(
                "", "end", iid=identity, values=(display,)
            )
        for severity, message in engine.errors:
            self.diagnostic_error_text.insert("end", f"[{severity.upper()}] {message}\n")
        self.diagnostic_error_text.configure(state="disabled")

        error_count = len(engine.errors)
        self.diagnostic_summary_text.set(
            f"{engine.profile.display_name} • 状態 {len(engine.statuses)}件 • "
            f"RS485 {len(engine.devices)}台 • エラー {error_count}件"
        )

    def close_window(self) -> None:
        self.disconnect_console()
        if self.loaded_release_module is not None:
            self.loaded_release_module.close()
            self.loaded_release_module = None
        self.root.destroy()

    def update_summary(self) -> None:
        selected = self.selected_files()
        total_size = sum(item.file_path.stat().st_size for item in selected)
        self.selection_summary_text.set(
            f"書込み対象 {len(selected)}件 • {self.format_size(total_size)}"
        )

    def log(self, message: str) -> None:
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.log_text.configure(state="normal")
        self.log_text.insert("end", f"[{timestamp}] {message}\n")
        self.log_text.see("end")
        self.log_text.configure(state="disabled")

    @staticmethod
    def format_size(size: int | None) -> str:
        if size is None:
            return "—"
        if size >= 1024 * 1024:
            return f"{size / (1024 * 1024):.2f} MB"
        if size >= 1024:
            return f"{size / 1024:.1f} KB"
        return f"{size} B"
