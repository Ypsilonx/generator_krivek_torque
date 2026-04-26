#!/usr/bin/env python3
"""
Torque Curve Generator GUI - grafické rozhraní s matplotlib vizualizací.

Deleguje veškeré výpočty na torque_engine. Přidává inline graf momentové
křivky s barevně odlišenými fázemi a milníkovými čarami.
"""

import os
import threading
import tkinter as tk
from tkinter import messagebox, ttk
from typing import List, Optional, Tuple

import torque_engine as engine

try:
    from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
    from matplotlib.figure import Figure
    _MATPLOTLIB = True
except ImportError:
    _MATPLOTLIB = False

OUTPUT_FOLDER = "output"

_RAMP_LABELS = {
    "hybrid":      "Hybridní – rychlý + stabilní (doporučeno)",
    "exponential": "Exponenciální – velmi rychlý náběh",
    "scurve":      "S-křivka – nejhladší, bez overshootu",
    "linear":      "Lineární – klasický přístup",
}

# Tmavá paleta pro matplotlib
_C_BG    = "#1a1a2e"
_C_AXES  = "#16213e"
_C_GRID  = "#2d2d5c"
_C_TEXT  = "#bdc3c7"
_C_CURVE = "#3498db"
_C_TARGET= "#ecf0f1"
_C_RAMP  = "#f39c12"
_C_WORK  = "#27ae60"
_C_BLOCK = "#e74c3c"
_C_M90   = "#f1c40f"
_C_M50   = "#95a5a6"


class TorqueCurveGeneratorGUI:
    """GUI aplikace pro generování momentových křivek se směrovým mapováním a vizualizací."""

    def __init__(self):
        os.makedirs(OUTPUT_FOLDER, exist_ok=True)

        self.root = tk.Tk()
        self.root.title("Torque Curve Generator – LH/RH Motor Support")
        self.root.geometry("1600x900")
        self.root.minsize(1200, 640)
        self.root.configure(bg="#f0f0f0")

        # --- stavové proměnné ---
        self.target_torque      = tk.DoubleVar(value=0.0)
        self.working_rotations  = tk.DoubleVar(value=0.0)
        self.working_degrees    = tk.DoubleVar(value=0.0)
        self.range_type         = tk.StringVar(value="rotations")
        self.ramp_type          = tk.StringVar(value="hybrid")
        self.ramp_degrees       = tk.DoubleVar(value=50.0)
        self.end_with_block     = tk.BooleanVar(value=False)
        self.block_torque       = tk.DoubleVar(value=40.0)
        self.motor_type         = tk.StringVar(value="LH")
        self.rotation_direction = tk.StringVar(value="CCW")
        self.filename           = tk.StringVar(value="")
        self.comment            = tk.StringVar(value="")
        self.auto_update_filename = tk.BooleanVar(value=True)

        # raw data (před direction mapping) pro vizualizaci
        self._last_raw_data: Optional[List[Tuple[float, float]]] = None
        # ID pendingového after() volání pro debouncing live preview
        self._chart_after_id: Optional[str] = None
        # Import mód – importovaná data a metadata
        self._imported_data: Optional[List[Tuple[float, float]]] = None
        self._imported_filename: str = ""
        self._outlier_indices: List[int] = []
        self._active_tab: int = 0  # 0 = Parametry, 1 = Import XLSX

        self._setup_gui()
        self._setup_auto_update_callbacks()
        self._generate_auto_filename()

    # -----------------------------------------------------------------------
    # Sestavení GUI
    # -----------------------------------------------------------------------

    def _setup_gui(self):
        """Sestaví celé GUI – titulní lišta + dvoupanelový layout s záložkami pro zdroj dat."""
        self._create_title_bar()

        content = tk.Frame(self.root, bg="#f0f0f0")
        content.pack(fill=tk.BOTH, expand=True, padx=14, pady=8)

        # Levý sloupec – scrollovatelný panel (pevná šířka 400 px)
        left_outer = tk.Frame(content, bg="#f0f0f0", width=430)
        left_outer.pack(side=tk.LEFT, fill=tk.Y)
        left_outer.pack_propagate(False)

        left_canvas = tk.Canvas(left_outer, bg="#f0f0f0", highlightthickness=0, width=413)
        left_scroll = tk.Scrollbar(left_outer, orient="vertical", command=left_canvas.yview)
        left_canvas.configure(yscrollcommand=left_scroll.set)
        left_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        left_canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        # Vnitřní frame – do něj jde veškerý obsah levého panelu
        left = tk.Frame(left_canvas, bg="#f0f0f0")
        left_canvas_window = left_canvas.create_window((0, 0), window=left, anchor="nw")

        def _on_left_configure(event):
            left_canvas.configure(scrollregion=left_canvas.bbox("all"))

        def _on_canvas_resize(event):
            left_canvas.itemconfig(left_canvas_window, width=event.width)

        left.bind("<Configure>", _on_left_configure)
        left_canvas.bind("<Configure>", _on_canvas_resize)

        # Scroll kolečkem myši nad levým panelem
        def _on_mousewheel(event):
            left_canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

        left_canvas.bind("<Enter>", lambda _e: left_canvas.bind_all("<MouseWheel>", _on_mousewheel))
        left_canvas.bind("<Leave>", lambda _e: left_canvas.unbind_all("<MouseWheel>"))

        # Pravý sloupec – graf + výsledky
        right = tk.Frame(content, bg="#f0f0f0")
        right.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(12, 0))

        # Záložky pro výběr zdroje dat
        self._notebook = ttk.Notebook(left)
        self._notebook.pack(fill=tk.X, pady=(0, 4))

        tab_gen = tk.Frame(self._notebook, bg="#f0f0f0")
        tab_imp = tk.Frame(self._notebook, bg="#f0f0f0")
        self._notebook.add(tab_gen, text="  Parametry  ")
        self._notebook.add(tab_imp, text="  Import XLSX  ")
        self._notebook.bind("<<NotebookTabChanged>>", self._on_tab_changed)

        self._create_torque_section(tab_gen)
        self._create_import_section(tab_imp)

        # Sdílené sekce – platí pro oba módy
        self._create_ramp_section(left)
        self._create_motor_section(left)
        self._create_file_section(left)
        self._create_buttons(left)

        self._create_chart_panel(right)
        self._create_results_panel(right)

    def _create_title_bar(self):
        bar = tk.Frame(self.root, bg="#2c3e50", height=52)
        bar.pack(fill=tk.X)
        bar.pack_propagate(False)
        tk.Label(bar, text="TORQUE CURVE GENERATOR",
                 font=("Arial", 14, "bold"), fg="white", bg="#2c3e50").pack(expand=True)
        tk.Label(bar, text="LH/RH Motor Support  •  PID Optimized  •  Matplotlib Visualization",
                 font=("Arial", 8), fg="#bdc3c7", bg="#2c3e50").pack()

    def _create_torque_section(self, parent):
        """Sekce s momentovými parametry a nastavením bloku."""
        frame = tk.LabelFrame(parent, text="Momentové parametry",
                              font=("Arial", 9, "bold"), bg="#f0f0f0", fg="#2c3e50")
        frame.pack(fill=tk.X, pady=(0, 6))

        tk.Label(frame, text="Cílový moment [Nm]:", bg="#f0f0f0").grid(
            row=0, column=0, sticky="w", padx=8, pady=4)
        tk.Entry(frame, textvariable=self.target_torque, width=10).grid(
            row=0, column=1, padx=4, pady=4)

        tk.Label(frame, text="Typ rozsahu:", bg="#f0f0f0").grid(
            row=1, column=0, sticky="w", padx=8, pady=4)
        rf = tk.Frame(frame, bg="#f0f0f0")
        rf.grid(row=1, column=1, sticky="w", padx=4, pady=4)
        tk.Radiobutton(rf, text="Otáčky", variable=self.range_type, value="rotations",
                       bg="#f0f0f0", command=self._on_range_type_change).pack(side=tk.LEFT)
        tk.Radiobutton(rf, text="Stupně", variable=self.range_type, value="degrees",
                       bg="#f0f0f0", command=self._on_range_type_change).pack(side=tk.LEFT, padx=(8, 0))

        self._range_label = tk.Label(frame, text="Počet otáček:", bg="#f0f0f0")
        self._range_label.grid(row=2, column=0, sticky="w", padx=8, pady=4)
        self._range_entry = tk.Entry(frame, textvariable=self.working_rotations, width=10)
        self._range_entry.grid(row=2, column=1, padx=4, pady=4)

    def _create_import_section(self, parent):
        """Záložka pro import reálných dat momentové křivky z Excel souboru."""
        from tkinter import filedialog  # noqa: PLC0415 – odložený import, tkinter je vždy k dispozici

        # --- Výběr souboru ---
        file_frame = tk.LabelFrame(parent, text="Excel soubor (.xlsx)",
                                   font=("Arial", 9, "bold"), bg="#f0f0f0", fg="#2c3e50")
        file_frame.pack(fill=tk.X, padx=4, pady=(6, 4))

        path_row = tk.Frame(file_frame, bg="#f0f0f0")
        path_row.pack(fill=tk.X, padx=8, pady=(6, 2))

        self._xlsx_path = tk.StringVar(value="")
        tk.Entry(path_row, textvariable=self._xlsx_path, state="readonly",
                 font=("Consolas", 8), relief="sunken").pack(side=tk.LEFT, fill=tk.X, expand=True)
        tk.Button(path_row, text="Procházet…", font=("Arial", 8),
                  bg="#3498db", fg="white",
                  command=self._browse_xlsx).pack(side=tk.LEFT, padx=(4, 0))

        self._import_stats = tk.Label(
            file_frame, text="Soubor není načten.",
            font=("Consolas", 8), bg="#f0f0f0", fg="#7f8c8d",
            justify=tk.LEFT, anchor="w",
        )
        self._import_stats.pack(fill=tk.X, padx=8, pady=(2, 6))

        # --- Validace ---
        val_frame = tk.LabelFrame(parent, text="Validace a anomálie",
                                  font=("Arial", 9, "bold"), bg="#f0f0f0", fg="#2c3e50")
        val_frame.pack(fill=tk.X, padx=4, pady=(0, 4))

        self._validation_text = tk.Text(
            val_frame, height=5, font=("Consolas", 8),
            bg="#2c3e50", fg="#ecf0f1", state=tk.DISABLED,
            insertbackground="white", relief="flat",
        )
        self._validation_text.pack(fill=tk.X, padx=6, pady=4)

        self._btn_remove_outliers = tk.Button(
            val_frame, text="Odebrat odlehlé hodnoty",
            command=self._remove_outliers,
            bg="#e67e22", fg="white", font=("Arial", 8),
            state="disabled",
        )
        self._btn_remove_outliers.pack(anchor="w", padx=6, pady=(0, 6))

    def _browse_xlsx(self):
        """Otevře dialog pro výběr .xlsx souboru a spustí jeho načtení."""
        from tkinter import filedialog  # noqa: PLC0415
        path = filedialog.askopenfilename(
            title="Vyberte Excel soubor s momentovými daty",
            filetypes=[("Excel soubory", "*.xlsx"), ("Všechny soubory", "*.*")],
        )
        if path:
            self._xlsx_path.set(path)
            self._load_xlsx_file(path)

    def _load_xlsx_file(self, filepath: str):
        """Spustí načtení xlsx v separátním vlákně (UI zůstane responzivní)."""
        self._set_validation_text("Načítám soubor…\n")
        self._import_stats.config(text="Zpracovávám…", fg="#7f8c8d")
        threading.Thread(
            target=self._load_xlsx_thread, args=(filepath,), daemon=True
        ).start()

    def _load_xlsx_thread(self, filepath: str):
        """Provede načtení a validaci xlsx (běží v threadu)."""
        try:
            data, issues = engine.load_xlsx(filepath)
            self.root.after(0, lambda: self._on_xlsx_loaded(filepath, data, issues))
        except Exception as exc:  # noqa: BLE001
            msg = str(exc)
            self.root.after(0, lambda: self._on_xlsx_error(msg))

    def _on_xlsx_loaded(
        self, filepath: str,
        data: List[Tuple[float, float]],
        issues: List[dict],
    ):
        """Zpracuje výsledky načtení xlsx ve hlavním vlákně."""
        self._imported_data = data
        self._imported_filename = os.path.splitext(os.path.basename(filepath))[0]

        # Najdeme outlier_indices z issues (pokud existují)
        self._outlier_indices = []
        for issue in issues:
            if "outlier_indices" in issue:
                self._outlier_indices = issue["outlier_indices"]
                break

        self._btn_remove_outliers.config(
            state="normal" if self._outlier_indices else "disabled"
        )

        # Statistiky souboru
        torques_v = [t for t, _ in data]
        angles_v  = [a for _, a in data]
        self._import_stats.config(
            text=(
                f"Bodů: {len(data):,}   "
                f"Úhly: {angles_v[0]:.0f}° – {angles_v[-1]:.0f}°"
                f"  ({angles_v[-1] / 360:.1f} ot.)\n"
                f"Moment: {min(torques_v):.2f} – {max(torques_v):.2f} Nm"
                f"  (prům. {sum(torques_v)/len(torques_v):.2f} Nm)"
            ),
            fg="#27ae60",
        )

        # Výsledky validace s ikonami
        level_icon = {"info": "✓ ", "warning": "⚠ ", "error": "✗ "}
        self._validation_text.config(state=tk.NORMAL)
        self._validation_text.delete(1.0, tk.END)
        for issue in issues:
            icon = level_icon.get(issue["level"], "  ")
            self._validation_text.insert(tk.END, f"{icon}{issue['message']}\n")
        self._validation_text.config(state=tk.DISABLED)

        # Auto-název souboru
        if self.auto_update_filename.get():
            self._generate_auto_filename()

        self._schedule_chart_refresh()

    def _on_xlsx_error(self, message: str):
        """Zobrazí chybu načtení xlsx ve hlavním vlákně."""
        self._imported_data = None
        self._import_stats.config(text="Chyba při načítání souboru.", fg="#e74c3c")
        self._set_validation_text(f"✗ CHYBA: {message}\n")
        self._btn_remove_outliers.config(state="disabled")

    def _remove_outliers(self):
        """Odebere odlehlé hodnoty momentu z importovaných dat a obnoví graf."""
        if not self._imported_data or not self._outlier_indices:
            return
        idx_set = set(self._outlier_indices)
        count = len(idx_set)
        self._imported_data = [
            pt for i, pt in enumerate(self._imported_data) if i not in idx_set
        ]
        self._outlier_indices = []
        self._btn_remove_outliers.config(state="disabled")

        # Aktualizace statistik
        torques_v = [t for t, _ in self._imported_data]
        angles_v  = [a for _, a in self._imported_data]
        self._import_stats.config(
            text=(
                f"Bodů: {len(self._imported_data):,}   "
                f"Úhly: {angles_v[0]:.0f}° – {angles_v[-1]:.0f}°\n"
                f"Moment: {min(torques_v):.2f} – {max(torques_v):.2f} Nm"
                f"  (prům. {sum(torques_v)/len(torques_v):.2f} Nm)"
            ),
            fg="#27ae60",
        )
        self._validation_text.config(state=tk.NORMAL)
        self._validation_text.insert(tk.END, f"✓ Odebráno {count} odlehlých hodnot\n")
        self._validation_text.config(state=tk.DISABLED)

        self._schedule_chart_refresh()

    def _set_validation_text(self, text: str):
        """Nahradí obsah validačního panelu (thread-safe)."""
        def _do():
            self._validation_text.config(state=tk.NORMAL)
            self._validation_text.delete(1.0, tk.END)
            self._validation_text.insert(tk.END, text)
            self._validation_text.config(state=tk.DISABLED)
        self.root.after(0, _do)

    def _on_tab_changed(self, _event=None):
        """Přepne aktivní záložku a obnoví graf a auto-název."""
        self._active_tab = self._notebook.index(self._notebook.select())
        if self.auto_update_filename.get():
            self._generate_auto_filename()
        self._schedule_chart_refresh()

    def _create_ramp_section(self, parent):
        """Sekce s nastavením náběhu."""
        frame = tk.LabelFrame(parent, text="Náběh PID",
                              font=("Arial", 9, "bold"), bg="#f0f0f0", fg="#2c3e50")
        frame.pack(fill=tk.X, pady=(0, 6))

        tk.Label(frame, text="Typ náběhu:", bg="#f0f0f0").grid(
            row=0, column=0, sticky="w", padx=8, pady=4)
        combo = ttk.Combobox(frame, textvariable=self.ramp_type, width=14,
                             state="readonly", values=list(_RAMP_LABELS.keys()))
        combo.grid(row=0, column=1, padx=4, pady=4)

        self._ramp_desc = tk.Label(frame, text=_RAMP_LABELS["hybrid"],
                                   font=("Arial", 7), fg="#7f8c8d", bg="#f0f0f0", wraplength=350)
        self._ramp_desc.grid(row=1, column=0, columnspan=3, sticky="w", padx=8)
        combo.bind("<<ComboboxSelected>>",
                   lambda _e: self._ramp_desc.config(text=_RAMP_LABELS.get(self.ramp_type.get(), "")))

        tk.Label(frame, text="Stabilizace do [°]:", bg="#f0f0f0").grid(
            row=2, column=0, sticky="w", padx=8, pady=4)
        tk.Entry(frame, textvariable=self.ramp_degrees, width=10).grid(
            row=2, column=1, padx=4, pady=4)

        # Blok na konci křivky – sdílené pro oba módy (Parametry i Import)
        sep = tk.Frame(frame, bg="#c8c8c8", height=1)
        sep.grid(row=3, column=0, columnspan=3, sticky="ew", padx=8, pady=(6, 2))
        bf = tk.Frame(frame, bg="#f0f0f0")
        bf.grid(row=4, column=0, columnspan=3, sticky="w", padx=8, pady=(2, 6))
        tk.Checkbutton(bf, text="Ukončit blokem", variable=self.end_with_block,
                       bg="#f0f0f0", command=self._on_block_change).pack(side=tk.LEFT)
        self._block_entry = tk.Entry(bf, textvariable=self.block_torque, width=8, state="disabled")
        self._block_entry.pack(side=tk.LEFT, padx=(8, 0))
        tk.Label(bf, text="Nm", bg="#f0f0f0").pack(side=tk.LEFT, padx=(2, 0))

    def _create_motor_section(self, parent):
        """Sekce s konfigurací motoru a směru otáčení."""
        frame = tk.LabelFrame(parent, text="Konfigurace motoru",
                              font=("Arial", 9, "bold"), bg="#f0f0f0", fg="#2c3e50")
        frame.pack(fill=tk.X, pady=(0, 6))

        tk.Label(frame, text="Typ motoru:", bg="#f0f0f0").grid(
            row=0, column=0, sticky="w", padx=8, pady=4)
        mf = tk.Frame(frame, bg="#f0f0f0")
        mf.grid(row=0, column=1, sticky="w", padx=4)
        tk.Radiobutton(mf, text="LH", variable=self.motor_type, value="LH",
                       bg="#f0f0f0", fg="#e74c3c", font=("Arial", 9, "bold")).pack(side=tk.LEFT)
        tk.Radiobutton(mf, text="RH", variable=self.motor_type, value="RH",
                       bg="#f0f0f0", fg="#3498db", font=("Arial", 9, "bold")).pack(side=tk.LEFT, padx=(12, 0))

        tk.Label(frame, text="Směr otáčení:", bg="#f0f0f0").grid(
            row=1, column=0, sticky="w", padx=8, pady=4)
        df = tk.Frame(frame, bg="#f0f0f0")
        df.grid(row=1, column=1, sticky="w", padx=4)
        tk.Radiobutton(df, text="CCW", variable=self.rotation_direction, value="CCW",
                       bg="#f0f0f0", fg="#27ae60").pack(side=tk.LEFT)
        tk.Radiobutton(df, text="CW", variable=self.rotation_direction, value="CW",
                       bg="#f0f0f0", fg="#f39c12").pack(side=tk.LEFT, padx=(12, 0))

        info = tk.Frame(frame, bg="#ecf0f1", relief="ridge", bd=1)
        info.grid(row=2, column=0, columnspan=2, sticky="ew", padx=8, pady=4)
        self._mapping_label = tk.Label(info, text="", font=("Arial", 8),
                                       bg="#ecf0f1", fg="#2c3e50")
        self._mapping_label.pack(anchor="w", padx=5, pady=3)
        self._update_mapping_info()
        self.motor_type.trace("w", lambda *_: self._update_mapping_info())
        self.rotation_direction.trace("w", lambda *_: self._update_mapping_info())

    def _create_file_section(self, parent):
        """Sekce s nastavením výstupního souboru."""
        frame = tk.LabelFrame(parent, text="Výstupní soubor",
                              font=("Arial", 9, "bold"), bg="#f0f0f0", fg="#2c3e50")
        frame.pack(fill=tk.X, pady=(0, 6))

        tk.Checkbutton(frame, text="Auto-aktualizace názvu",
                       variable=self.auto_update_filename, bg="#f0f0f0",
                       command=self._on_auto_update_change).grid(
            row=0, column=0, columnspan=2, sticky="w", padx=8, pady=4)

        tk.Label(frame, text="Základní název:", bg="#f0f0f0").grid(
            row=1, column=0, sticky="w", padx=8)
        self._filename_entry = tk.Entry(frame, textvariable=self.filename,
                                        width=36, state="readonly")
        self._filename_entry.grid(row=2, column=0, columnspan=2, padx=8, pady=2, sticky="ew")

        tk.Label(frame, text="Komentář:", bg="#f0f0f0").grid(
            row=3, column=0, sticky="w", padx=8, pady=(6, 2))
        ce = tk.Entry(frame, textvariable=self.comment, width=36)
        ce.grid(row=4, column=0, columnspan=2, padx=8, pady=2, sticky="ew")
        ce.bind("<KeyRelease>", lambda _e: self._update_filename_if_auto())

        tk.Label(frame, text="Finální název:", bg="#f0f0f0",
                 font=("Arial", 8, "bold")).grid(row=5, column=0, sticky="w", padx=8, pady=(8, 2))
        self._final_name_label = tk.Label(frame, text="", bg="#ecf0f1", fg="#2c3e50",
                                          font=("Consolas", 8), relief="sunken", anchor="w")
        self._final_name_label.grid(row=6, column=0, columnspan=2, padx=8, pady=2, sticky="ew")
        frame.columnconfigure(0, weight=1)

    def _create_buttons(self, parent):
        """Ovládací tlačítka."""
        frame = tk.Frame(parent, bg="#f0f0f0")
        frame.pack(fill=tk.X, pady=8)

        tk.Button(frame, text="Uložit CSV", command=self._save_csv,
                  bg="#27ae60", fg="white", font=("Arial", 11, "bold"), height=2
                  ).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 4))
        tk.Button(frame, text="Otevřít složku", command=self._open_output_folder,
                  bg="#3498db", fg="white", font=("Arial", 9)
                  ).pack(side=tk.LEFT, padx=4)
        tk.Button(frame, text="Reset", command=self._reset_form,
                  bg="#95a5a6", fg="white", font=("Arial", 9)
                  ).pack(side=tk.LEFT, padx=(4, 0))

    # -----------------------------------------------------------------------
    # Matplotlib vizualizace
    # -----------------------------------------------------------------------

    def _create_chart_panel(self, parent):
        """Vytvoří matplotlib graf vložený do Tkinter."""
        chart_frame = tk.LabelFrame(parent, text="Vizualizace momentové křivky",
                                    font=("Arial", 9, "bold"), bg="#f0f0f0", fg="#2c3e50")
        chart_frame.pack(fill=tk.BOTH, expand=True, pady=(0, 6))

        if not _MATPLOTLIB:
            tk.Label(chart_frame,
                     text="matplotlib není k dispozici.\nNainstalujte: pip install matplotlib",
                     bg="#f0f0f0", fg="#e74c3c", font=("Arial", 10)).pack(expand=True)
            self._canvas = None
            return

        self._fig = Figure(figsize=(8.8, 5.6), dpi=92)
        self._fig.patch.set_facecolor(_C_BG)
        self._ax = self._fig.add_subplot(111)
        self._fig.subplots_adjust(left=0.09, right=0.97, top=0.88, bottom=0.12)

        self._canvas = FigureCanvasTkAgg(self._fig, master=chart_frame)
        self._canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True, padx=4, pady=4)
        self._draw_empty_chart()

    def _draw_empty_chart(self):
        """Nakreslí prázdný graf s návodem."""
        if self._canvas is None:
            return
        ax = self._ax
        ax.clear()
        ax.set_facecolor(_C_AXES)
        ax.set_xlabel("Úhel [°]", color=_C_TEXT, fontsize=9)
        ax.set_ylabel("Moment [Nm]", color=_C_TEXT, fontsize=9)
        ax.set_title("Generujte křivku pro zobrazení grafu", color=_C_GRID, fontsize=10)
        ax.tick_params(colors=_C_TEXT, labelsize=8)
        for spine in ax.spines.values():
            spine.set_color(_C_GRID)
        ax.grid(True, alpha=0.25, color=_C_GRID)
        self._canvas.draw()

    def _update_chart(
        self,
        raw_data: List[Tuple[float, float]],
        ramp_degrees: float,
        target_torque: float,
        end_with_block: bool,
        motor_type: str,
        direction: str,
        import_mode: bool = False,
    ):
        """Překreslí graf s nově vygenerovanými daty.

        Zobrazuje kladné (raw) hodnoty pro čitelnost; směr je uveden v titulku.
        Fáze jsou barevně odlišeny, milníky označeny přerušovanými čarami.

        Args:
            raw_data: Data před direction mapping (vždy kladné)
            ramp_degrees: Délka náběhové fáze [°]
            target_torque: Cílový moment [Nm]
            end_with_block: Zda sekvence obsahuje blok
            motor_type: "LH" nebo "RH"
            direction: "CCW" nebo "CW"
        """
        if self._canvas is None:
            return

        ax = self._ax
        ax.clear()
        ax.set_facecolor(_C_AXES)

        angles  = [pt[1] for pt in raw_data]
        torques = [pt[0] for pt in raw_data]

        ramp_end_idx    = min(int(ramp_degrees), len(raw_data) - 1)
        block_start_idx = len(raw_data) - 3 if end_with_block else len(raw_data)

        # --- Barevná pozadí fází (výrazná, čitelná) ---
        if import_mode:
            y_max = max((abs(t) for t in torques), default=1.0) * 1.18
        else:
            y_max = (
                target_torque * 1.18
                if not end_with_block
                else max(target_torque, self.block_torque.get()) * 1.18
            )

        if ramp_end_idx > 0:
            ax.axvspan(0, angles[ramp_end_idx], alpha=0.30, color=_C_RAMP, zorder=0)
            # Silný levý rámeček náběhové fáze
            ax.axvline(x=0, color=_C_RAMP, linewidth=1.5, alpha=0.7, zorder=1)
            ax.axvline(x=angles[ramp_end_idx], color=_C_RAMP,
                       linewidth=1.5, linestyle="--", alpha=0.8, zorder=1)

        work_end_idx = min(block_start_idx, len(angles) - 1)
        if ramp_end_idx < block_start_idx:
            ax.axvspan(angles[ramp_end_idx], angles[work_end_idx],
                       alpha=0.12, color=_C_WORK, zorder=0)

        if end_with_block and block_start_idx < len(angles):
            # Blok: výrazné červené pozadí + silná svislá čára začátku
            ax.axvspan(angles[block_start_idx], angles[-1],
                       alpha=0.55, color=_C_BLOCK, zorder=0)
            ax.axvline(x=angles[block_start_idx], color=_C_BLOCK,
                       linewidth=2.0, alpha=0.9, zorder=1)

        # --- Vodorovné referenční čáry (pouze v parametrickém módu) ---
        if not import_mode:
            ax.axhline(y=target_torque, color=_C_TARGET,
                       linestyle="--", alpha=0.50, linewidth=1.2,
                       label=f"Cíl {target_torque:.1f} Nm")
            ax.axhline(y=target_torque * 0.9, color=_C_M90,
                       linestyle=":", alpha=0.65, linewidth=1,
                       label=f"90 % = {target_torque * 0.9:.1f} Nm")
            ax.axhline(y=target_torque * 0.5, color=_C_M50,
                       linestyle=":", alpha=0.50, linewidth=1,
                       label=f"50 % = {target_torque * 0.5:.1f} Nm")

        # --- Samotná křivka ---
        ax.plot(angles, torques, color=_C_CURVE, linewidth=2.5,
                label="Momentová křivka", zorder=3)

        # --- Anotace fází (nahoře, mimo křivku) ---
        y_label = y_max * 0.93
        if ramp_end_idx > 5:
            ax.text(ramp_degrees / 2, y_label, "NÁBĚH",
                    color=_C_RAMP, fontsize=8, ha="center", fontweight="bold",
                    bbox=dict(boxstyle="round,pad=0.2", fc=_C_BG, alpha=0.6, ec=_C_RAMP))
        if (block_start_idx - ramp_end_idx) > 10:
            mid_x = (angles[ramp_end_idx] + angles[work_end_idx]) / 2
            ax.text(mid_x, y_label, "PRACOVNÍ FÁZE",
                    color=_C_WORK, fontsize=8, ha="center", fontweight="bold",
                    bbox=dict(boxstyle="round,pad=0.2", fc=_C_BG, alpha=0.6, ec=_C_WORK))
        if end_with_block and block_start_idx < len(angles):
            mid_blk = (angles[block_start_idx] + angles[-1]) / 2
            ax.text(mid_blk, y_label, "BLOK",
                    color=_C_BLOCK, fontsize=8, ha="center", fontweight="bold",
                    bbox=dict(boxstyle="round,pad=0.2", fc=_C_BG, alpha=0.7, ec=_C_BLOCK))

        # --- Styl os a titulku ---
        sign = "+" if (motor_type == "LH") == (direction == "CCW") else "−"
        ax.set_xlabel("Úhel [°]", color=_C_TEXT, fontsize=9)
        ax.set_ylabel("Moment [Nm]", color=_C_TEXT, fontsize=9)
        if import_mode:
            fname = getattr(self, "_imported_filename", "")
            short_fname = (fname[:22] + "…") if len(fname) > 22 else fname
            ax.set_title(
                f"{motor_type} {direction}  ({sign})  ·  {self.ramp_type.get()}  ·  "
                f"Import: {short_fname}  /  {angles[-1]:.0f}°",
                color=_C_TARGET, fontsize=9, fontweight="bold",
            )
        else:
            ax.set_title(
                f"{motor_type} {direction}  ({sign})  ·  {self.ramp_type.get()}  ·  "
                f"{target_torque:.1f} Nm  /  {angles[-1]:.0f}°",
                color=_C_TARGET, fontsize=9, fontweight="bold",
            )
        ax.set_ylim(bottom=0, top=y_max)
        ax.tick_params(colors=_C_TEXT, labelsize=8)
        for spine in ax.spines.values():
            spine.set_color(_C_GRID)
        ax.grid(True, alpha=0.22, color=_C_GRID)

        ax.legend(fontsize=7, facecolor=_C_BG, edgecolor=_C_GRID,
                  labelcolor=_C_TARGET, loc="lower right")
        self._canvas.draw()

    # -----------------------------------------------------------------------
    # Oblast výsledků
    # -----------------------------------------------------------------------

    def _create_results_panel(self, parent):
        """Textová oblast s výsledky generování."""
        frame = tk.LabelFrame(parent, text="Analýza a výsledky",
                              font=("Arial", 9, "bold"), bg="#f0f0f0", fg="#2c3e50")
        frame.pack(fill=tk.X)

        self._results_text = tk.Text(frame, height=7, font=("Consolas", 8),
                                     bg="#2c3e50", fg="#ecf0f1", insertbackground="white")
        sb = tk.Scrollbar(frame, orient="vertical", command=self._results_text.yview)
        self._results_text.configure(yscrollcommand=sb.set)
        self._results_text.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=6, pady=4)
        sb.pack(side=tk.RIGHT, fill=tk.Y, pady=4)

        self._results_text.insert(
            tk.END,
            "Graf se aktualizuje živě při zadávání.\n"
            "Klikněte 'Uložit CSV' pro export souboru.\n\n"
            "• PID optimalizováno\n"
            "• LH/RH směrové mapování\n"
            "• CSV formát (;)\n"
            "• Live Matplotlib vizualizace",
        )
        self._results_text.config(state=tk.DISABLED)

    # -----------------------------------------------------------------------
    # Uložení CSV
    # -----------------------------------------------------------------------

    def _save_csv(self):
        """Validuje vstup a uloží CSV v separátním vlákně. Graf je aktualizován live."""
        if self._active_tab == 1:
            # Import mód – ověříme, že jsou data načtena
            if not self._imported_data:
                messagebox.showerror(
                    "Žádná data", "Nejprve načtěte Excel soubor na záložce 'Import XLSX'."
                )
                return
            threading.Thread(
                target=self._save_csv_import_thread, daemon=True
            ).start()
            return

        try:
            target = self._safe_get(self.target_torque)
            if target <= 0:
                raise ValueError("Cílový moment musí být větší než 0")

            if self.range_type.get() == "rotations":
                working_deg = self._safe_get(self.working_rotations) * 360
                range_desc  = f"{self._safe_get(self.working_rotations):.2g} otáček"
            else:
                working_deg = self._safe_get(self.working_degrees)
                range_desc  = f"{working_deg:.0f}°"

            if working_deg <= 0:
                raise ValueError("Pracovní rozsah musí být větší než 0")

            threading.Thread(
                target=self._save_csv_thread,
                args=(working_deg, range_desc),
                daemon=True,
            ).start()

        except ValueError as exc:
            messagebox.showerror("Neplatné hodnoty", str(exc))

    # zachováno pro zpětnou kompatibilitu
    def _generate_curve(self):
        """Alias pro _save_csv (zpětná kompatibilita)."""
        self._save_csv()

    def _save_csv_thread(self, working_degrees: float, range_desc: str):
        """Ukládá CSV do souboru, aktualizuje výsledkový panel (běží v threadu)."""
        return self._generate_curve_thread(working_degrees, range_desc)

    def _save_csv_import_thread(self):
        """Generuje CSV z importovaných dat + náběhu (běží v threadu)."""
        try:
            self._set_results("Generuji křivku z importovaných dat…\n")

            ramp_deg = self.ramp_degrees.get()
            ramp     = self.ramp_type.get()
            e_block  = self.end_with_block.get()
            b_torque = self.block_torque.get()
            motor    = self.motor_type.get()
            direc    = self.rotation_direction.get()

            raw_data = engine.generate_curve_from_data(
                self._imported_data, ramp, ramp_deg, e_block, b_torque
            )
            self._last_raw_data = raw_data

            mapped_data = engine.apply_direction_mapping(raw_data, motor, direc)

            final_name = self._get_final_filename() or f"import_{self._imported_filename}"
            csv_path = engine.save_csv(
                mapped_data, os.path.join(OUTPUT_FOLDER, f"{final_name}.csv")
            )

            first_torque = abs(self._imported_data[0][0])
            self.root.after(
                0,
                lambda: self._update_chart(
                    raw_data, ramp_deg, first_torque, e_block, motor, direc, import_mode=True
                ),
            )
            self.root.after(
                0, lambda: self._show_results_import(csv_path, mapped_data)
            )

        except Exception as exc:  # noqa: BLE001
            self.root.after(
                0, lambda: messagebox.showerror("Chyba při generování", str(exc))
            )

    def _show_results_import(self, csv_path: str, data: List[Tuple[float, float]]):
        """Zobrazí výsledky generování z import módu."""
        self._results_text.config(state=tk.NORMAL)
        self._results_text.delete(1.0, tk.END)

        t = self._results_text
        t.insert(tk.END, "IMPORT + GENEROVÁNÍ DOKONČENO\n" + "=" * 30 + "\n\n")

        motor = self.motor_type.get()
        direc = self.rotation_direction.get()
        sign  = "+" if (motor == "LH") == (direc == "CCW") else "−"

        torques_abs = [abs(pt[0]) for pt in data]
        t.insert(tk.END, f"Motor:  {motor} {direc}  ({sign} orientace)\n")
        t.insert(tk.END, f"Zdroj:  {self._imported_filename}\n")
        t.insert(tk.END, f"Moment: {min(torques_abs):.2f} – {max(torques_abs):.2f} Nm\n")
        t.insert(tk.END, f"Náběh:  {self.ramp_type.get()} / {self.ramp_degrees.get():.0f}°\n")
        if self.end_with_block.get():
            t.insert(tk.END, f"Blok:   {self.block_torque.get():.0f} Nm\n")

        t.insert(tk.END, f"\nSoubor: {os.path.basename(csv_path)}\n")
        t.insert(tk.END, f"Bodů: {len(data)}  |  Rozsah: 0 → {abs(data[-1][1]):.0f}°\n")

        self._results_text.config(state=tk.DISABLED)

    def _generate_curve_thread(self, working_degrees: float, range_desc: str):
        """Generuje křivku, ukládá CSV, aktualizuje UI (běží v threadu)."""
        try:
            self._set_results("Generuji momentovou křivku…\n")

            ramp_deg = self.ramp_degrees.get()
            target   = self.target_torque.get()
            ramp     = self.ramp_type.get()
            e_block  = self.end_with_block.get()
            b_torque = self.block_torque.get()
            motor    = self.motor_type.get()
            direc    = self.rotation_direction.get()

            # Výpočet – raw data (kladné hodnoty, pro vizualizaci i analýzu)
            raw_data = engine.generate_curve(
                target, working_degrees, ramp, ramp_deg, e_block, b_torque
            )
            self._last_raw_data = raw_data

            # Směrové mapování pro CSV výstup
            mapped_data = engine.apply_direction_mapping(raw_data, motor, direc)

            # Analýza (z raw dat, absolutní hodnoty)
            analysis = engine.analyze_curve(raw_data, target)

            # Název souboru
            final_name = self._get_final_filename()
            if not final_name:
                self.root.after(0, self._generate_auto_filename)
                final_name = self._get_final_filename() or "torque_output"

            # Uložení (mapped data → CSV)
            csv_path = engine.save_csv(
                mapped_data, os.path.join(OUTPUT_FOLDER, f"{final_name}.csv")
            )

            # Aktualizace UI ve hlavním vlákně
            self.root.after(
                0,
                lambda: self._update_chart(raw_data, ramp_deg, target, e_block, motor, direc),
            )
            self.root.after(
                0,
                lambda: self._show_results(csv_path, mapped_data, analysis, range_desc),
            )

        except Exception as exc:  # noqa: BLE001
            self.root.after(
                0, lambda: messagebox.showerror("Chyba při generování", str(exc))
            )

    # -----------------------------------------------------------------------
    # Výsledky
    # -----------------------------------------------------------------------

    def _set_results(self, text: str):
        """Nahradí obsah výsledkové oblasti (thread-safe přes after)."""
        def _do():
            self._results_text.config(state=tk.NORMAL)
            self._results_text.delete(1.0, tk.END)
            self._results_text.insert(tk.END, text)
            self._results_text.config(state=tk.DISABLED)
        self.root.after(0, _do)

    def _show_results(
        self,
        csv_path: str,
        data: List[Tuple[float, float]],
        analysis: dict,
        range_desc: str,
    ):
        """Zobrazí kompletní výsledky v textové oblasti."""
        self._results_text.config(state=tk.NORMAL)
        self._results_text.delete(1.0, tk.END)

        t = self._results_text
        t.insert(tk.END, "GENEROVÁNÍ DOKONČENO\n" + "=" * 26 + "\n\n")

        motor = self.motor_type.get()
        direc = self.rotation_direction.get()
        sign  = "+" if (motor == "LH") == (direc == "CCW") else "−"

        t.insert(tk.END, f"Motor:  {motor} {direc}  ({sign} orientace)\n")
        t.insert(tk.END, f"Moment: {self.target_torque.get():.1f} Nm\n")
        t.insert(tk.END, f"Rozsah: {range_desc}\n")
        t.insert(tk.END, f"Náběh:  {self.ramp_type.get()} / {self.ramp_degrees.get():.0f}°\n")
        if self.end_with_block.get():
            t.insert(tk.END, f"Blok:   {self.block_torque.get():.0f} Nm\n")

        t.insert(tk.END, "\nAnalýza náběhu:\n")
        for milestone, angle in analysis.items():
            if milestone != "stability":
                t.insert(tk.END, f"  {milestone} cíle: {angle}\n")
        t.insert(tk.END, f"  Stabilita: {analysis['stability']}\n")

        t.insert(tk.END, f"\nSoubor: {os.path.basename(csv_path)}\n")
        t.insert(tk.END, f"Bodů: {len(data)}  |  Rozsah: 0 → {abs(data[-1][1]):.0f}°\n")

        self._results_text.config(state=tk.DISABLED)

    # -----------------------------------------------------------------------
    # Pomocné metody GUI
    # -----------------------------------------------------------------------

    def _on_range_type_change(self):
        if self.range_type.get() == "rotations":
            self._range_label.config(text="Počet otáček:")
            self._range_entry.config(textvariable=self.working_rotations)
        else:
            self._range_label.config(text="Úhel [°]:")
            self._range_entry.config(textvariable=self.working_degrees)

    def _on_block_change(self):
        self._block_entry.config(state="normal" if self.end_with_block.get() else "disabled")

    def _update_mapping_info(self):
        motor    = self.motor_type.get()
        direc    = self.rotation_direction.get()
        positive = (motor == "LH") == (direc == "CCW")
        sign     = "+" if positive else "−"
        color    = "#27ae60" if positive else "#e74c3c"
        self._mapping_label.config(
            text=f"{motor} {direc}: {sign} hodnoty (moment i úhel)", fg=color
        )

    def _schedule_chart_refresh(self):
        """Odloží překreslení grafu o 120 ms – debouncing při rychlém psaní."""
        if self._chart_after_id is not None:
            self.root.after_cancel(self._chart_after_id)
        self._chart_after_id = self.root.after(120, self._refresh_chart_live)

    def _refresh_chart_live(self):
        """Zkusí vygenerovat preview křivky z aktuálních parametrů a překreslit graf.

        Selže-li validace (neúplný vstup), graf se nepřekreslí.
        """
        self._chart_after_id = None

        if self._active_tab == 1:
            self._refresh_chart_import()
            return

        target   = self._safe_get(self.target_torque)
        ramp_deg = self._safe_get(self.ramp_degrees, 0.0)
        b_torque = self._safe_get(self.block_torque, 0.0)

        if self.range_type.get() == "rotations":
            working_deg = self._safe_get(self.working_rotations) * 360
        else:
            working_deg = self._safe_get(self.working_degrees)

        # Nezobrazujeme graf pro neplatné hodnoty
        if target <= 0 or working_deg <= 0:
            return

        try:
            raw_data = engine.generate_curve(
                target, working_deg, self.ramp_type.get(),
                ramp_deg, self.end_with_block.get(), b_torque,
            )
            self._last_raw_data = raw_data
            motor = self.motor_type.get()
            direc = self.rotation_direction.get()
            self._update_chart(raw_data, ramp_deg, target,
                               self.end_with_block.get(), motor, direc)
        except Exception:
            pass  # Neúplný vstup – nekreslíme

    def _refresh_chart_import(self):
        """Obnoví live preview grafu pro import mód."""
        if not self._imported_data:
            return
        ramp_deg = self._safe_get(self.ramp_degrees, 0.0)
        b_torque = self._safe_get(self.block_torque, 0.0)
        try:
            raw_data = engine.generate_curve_from_data(
                self._imported_data, self.ramp_type.get(),
                ramp_deg, self.end_with_block.get(), b_torque,
            )
            self._last_raw_data = raw_data
            motor = self.motor_type.get()
            direc = self.rotation_direction.get()
            first_torque = abs(self._imported_data[0][0])
            self._update_chart(
                raw_data, ramp_deg, first_torque,
                self.end_with_block.get(), motor, direc, import_mode=True,
            )
        except Exception:
            pass  # Neúplný vstup – nekreslíme

    def _generate_auto_filename(self):
        if self._active_tab == 1:
            # Import mód – název vychází z xlsx souboru
            if self._imported_filename:
                motor      = self.motor_type.get()
                direc      = self.rotation_direction.get()
                ramp       = self.ramp_type.get()
                block_part = (
                    f"_blok{self._safe_get(self.block_torque):.0f}"
                    if self.end_with_block.get() else ""
                )
                self.filename.set(
                    f"import_{motor}_{direc}_{ramp}_{self._imported_filename}{block_part}"
                )
            self._update_filename_preview()
            return

        torque     = self._safe_get(self.target_torque)
        motor      = self.motor_type.get()
        direc      = self.rotation_direction.get()
        ramp       = self.ramp_type.get()
        range_part = (
            f"{self._safe_get(self.working_rotations):.0f}rot"
            if self.range_type.get() == "rotations"
            else f"{self._safe_get(self.working_degrees):.0f}deg"
        )
        block_part = f"_blok{self._safe_get(self.block_torque):.0f}" if self.end_with_block.get() else ""
        self.filename.set(
            f"torque_{motor}_{direc}_{ramp}_{torque:.0f}Nm_{range_part}{block_part}"
        )
        self._update_filename_preview()

    def _update_filename_preview(self):
        name = self._get_final_filename()
        self._final_name_label.config(text=f"{name}.csv" if name else "[prázdný název]")

    def _get_final_filename(self) -> str:
        base    = self.filename.get().strip()
        comment = self.comment.get().strip()
        return f"{base}_{comment}" if comment else base

    def _safe_get(self, var: tk.Variable, default: float = 0.0) -> float:
        """Bezpečně načte float hodnotu z tk.Variable.

        Vrací `default` pokud je pole prázdné nebo obsahuje neúplný vstup
        (např. při přepisování čísla uživatelem).

        Args:
            var: Tkinter proměnná (DoubleVar)
            default: Výchozí hodnota při chybě parsování

        Returns:
            Načtená hodnota nebo default
        """
        try:
            return float(var.get())
        except (tk.TclError, ValueError):
            return default

    def _setup_auto_update_callbacks(self):
        def cb(*_args):
            self._update_filename_if_auto()
            self._schedule_chart_refresh()

        for var in (
            self.target_torque, self.working_rotations, self.working_degrees,
            self.range_type, self.ramp_type, self.ramp_degrees,
            self.end_with_block, self.block_torque,
            self.motor_type, self.rotation_direction, self.comment,
        ):
            var.trace("w", cb)

    def _update_filename_if_auto(self):
        if self.auto_update_filename.get():
            self._generate_auto_filename()
        else:
            self._update_filename_preview()

    def _on_auto_update_change(self):
        if self.auto_update_filename.get():
            self._filename_entry.config(state="readonly")
            self._generate_auto_filename()
        else:
            self._filename_entry.config(state="normal")

    def _open_output_folder(self):
        try:
            if os.name == "nt":
                # Absolutní cesta zamezí path injection při neobvyklých znacích
                os.startfile(os.path.abspath(OUTPUT_FOLDER))
            else:
                import subprocess
                subprocess.run(
                    ["xdg-open", os.path.abspath(OUTPUT_FOLDER)], check=False
                )
        except Exception as exc:
            messagebox.showerror("Chyba", f"Nelze otevřít složku: {exc}")

    def _reset_form(self):
        self.target_torque.set(15.0)
        self.working_rotations.set(5.0)
        self.working_degrees.set(1800.0)
        self.range_type.set("rotations")
        self.ramp_type.set("hybrid")
        self.ramp_degrees.set(45.0)
        self.end_with_block.set(False)
        self.block_torque.set(60.0)
        self.motor_type.set("LH")
        self.rotation_direction.set("CCW")
        self.filename.set("")
        self.comment.set("")
        self.auto_update_filename.set(True)

        self._on_range_type_change()
        self._on_block_change()
        self._on_auto_update_change()
        self._update_mapping_info()
        self._generate_auto_filename()
        self._draw_empty_chart()
        self._schedule_chart_refresh()

        self._results_text.config(state=tk.NORMAL)
        self._results_text.delete(1.0, tk.END)
        self._results_text.insert(tk.END, "Formulář resetován.\nNastavte nové parametry.")
        self._results_text.config(state=tk.DISABLED)

    def run(self):
        """Spustí hlavní smyčku GUI."""
        self.root.mainloop()


if __name__ == "__main__":
    TorqueCurveGeneratorGUI().run()

