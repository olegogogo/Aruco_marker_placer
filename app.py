#!/usr/bin/env python3
import json
import math
import base64
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
from typing import List, Optional

import cv2
import numpy as np
import tkinter as tk
from PIL import Image, ImageTk
from tkinter import filedialog, messagebox, ttk

try:
    import ezdxf
except Exception:
    ezdxf = None


ARUCO_DICTS = {
    "DICT_4X4_50": cv2.aruco.DICT_4X4_50,
    "DICT_4X4_100": cv2.aruco.DICT_4X4_100,
    "DICT_4X4_250": cv2.aruco.DICT_4X4_250,
    "DICT_4X4_1000": cv2.aruco.DICT_4X4_1000,
    "DICT_5X5_50": cv2.aruco.DICT_5X5_50,
    "DICT_5X5_100": cv2.aruco.DICT_5X5_100,
    "DICT_5X5_250": cv2.aruco.DICT_5X5_250,
    "DICT_5X5_1000": cv2.aruco.DICT_5X5_1000,
    "DICT_6X6_50": cv2.aruco.DICT_6X6_50,
    "DICT_6X6_100": cv2.aruco.DICT_6X6_100,
    "DICT_6X6_250": cv2.aruco.DICT_6X6_250,
    "DICT_6X6_1000": cv2.aruco.DICT_6X6_1000,
    "DICT_7X7_50": cv2.aruco.DICT_7X7_50,
    "DICT_7X7_100": cv2.aruco.DICT_7X7_100,
    "DICT_7X7_250": cv2.aruco.DICT_7X7_250,
    "DICT_7X7_1000": cv2.aruco.DICT_7X7_1000,
    "DICT_ARUCO_ORIGINAL": cv2.aruco.DICT_ARUCO_ORIGINAL,
}

DICT_TO_SCHEME_TYPE = {
    "DICT_4X4_50": "Aruco_4x4_50",
    "DICT_4X4_100": "Aruco_4x4_100",
    "DICT_4X4_250": "Aruco_4x4_250",
    "DICT_4X4_1000": "Aruco_4x4_1000",
    "DICT_5X5_50": "Aruco_5x5_50",
    "DICT_5X5_100": "Aruco_5x5_100",
    "DICT_5X5_250": "Aruco_5x5_250",
    "DICT_5X5_1000": "Aruco_5x5_1000",
    "DICT_6X6_50": "Aruco_6x6_50",
    "DICT_6X6_100": "Aruco_6x6_100",
    "DICT_6X6_250": "Aruco_6x6_250",
    "DICT_6X6_1000": "Aruco_6x6_1000",
    "DICT_7X7_50": "Aruco_7x7_50",
    "DICT_7X7_100": "Aruco_7x7_100",
    "DICT_7X7_250": "Aruco_7x7_250",
    "DICT_7X7_1000": "Aruco_7x7_1000",
    "DICT_ARUCO_ORIGINAL": "Aruco_original",
}
SCHEME_TYPE_TO_DICT = {v: k for k, v in DICT_TO_SCHEME_TYPE.items()}


@dataclass
class Marker:
    marker_id: int
    dictionary: str
    cx_px: float
    cy_px: float
    size_px: int
    size_mm: float
    rotation_deg: float = 0.0


class ArucoLayoutApp:
    EXPORT_PPM_MIN = 3000
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("Aruco Marker Placer")
        self.root.geometry("1450x920")

        self.background_path: Optional[Path] = None
        self.background_rgb = None
        self.tk_image = None
        self.scale = 1.0
        self.zoom = 1.0
        self.pan_x = 0.0
        self.pan_y = 0.0
        self._pan_last = None
        self.dxf_path: Optional[Path] = None
        self.dxf_size_x_m: Optional[float] = None
        self.dxf_size_y_m: Optional[float] = None

        self.markers: List[Marker] = []
        self._form_sync_in_progress = False
        self.selected_marker_index: Optional[int] = None
        self._build_ui()

    def _build_ui(self):
        style = ttk.Style()
        style.configure("MarkerTree.Treeview", rowheight=28)

        self.main_pane = ttk.Panedwindow(self.root, orient=tk.HORIZONTAL)
        self.main_pane.pack(fill=tk.BOTH, expand=True)

        self.left_wrap = ttk.Frame(self.main_pane, width=560)
        self.left_wrap.pack_propagate(False)

        self.left_canvas = tk.Canvas(self.left_wrap, highlightthickness=0)
        left_scroll = ttk.Scrollbar(self.left_wrap, orient=tk.VERTICAL, command=self.left_canvas.yview)
        self.left_canvas.configure(yscrollcommand=left_scroll.set)
        self.left_canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(8, 0), pady=8)
        left_scroll.pack(side=tk.RIGHT, fill=tk.Y)

        left = ttk.Frame(self.left_canvas)
        self.param_frame = left
        left_window = self.left_canvas.create_window((0, 0), window=left, anchor="nw")

        def _sync_left_scroll(_event=None):
            self.left_canvas.configure(scrollregion=self.left_canvas.bbox("all"))

        def _sync_left_width(event):
            self.left_canvas.itemconfigure(left_window, width=event.width)

        left.bind("<Configure>", _sync_left_scroll)
        self.left_canvas.bind("<Configure>", _sync_left_width)

        self.left_canvas.bind("<MouseWheel>", self.on_param_wheel)
        self.left_canvas.bind("<Button-4>", lambda _e: self.on_param_wheel_linux(-1))
        self.left_canvas.bind("<Button-5>", lambda _e: self.on_param_wheel_linux(1))

        right = ttk.Frame(self.main_pane)
        self.main_pane.add(self.left_wrap, weight=1)
        self.main_pane.add(right, weight=4)
        self._init_left_panel_width()

        ttk.Label(left, text="Фон (чертеж/изображение)", font=("TkDefaultFont", 10, "bold")).pack(anchor="w")
        ttk.Button(left, text="Загрузить фон", command=self.load_background).pack(fill=tk.X, pady=4)
        ttk.Button(left, text="Загрузить DXF", command=self.load_dxf).pack(fill=tk.X, pady=2)

        ttk.Label(left, text="Параметры схемы (JSON)", font=("TkDefaultFont", 10, "bold")).pack(anchor="w")
        self.size_x_var = tk.DoubleVar(value=0.9)
        self.size_y_var = tk.DoubleVar(value=0.9)
        self.ppm_var = tk.DoubleVar(value=2500.0)
        self.inverted_var = tk.BooleanVar(value=True)
        self.auto_marker_px_var = tk.BooleanVar(value=True)

        ttk.Label(left, text="sizeX (m)").pack(anchor="w")
        self.size_x_entry = ttk.Entry(left, textvariable=self.size_x_var)
        self.size_x_entry.pack(fill=tk.X, pady=2)

        ttk.Label(left, text="sizeY (m)").pack(anchor="w")
        self.size_y_entry = ttk.Entry(left, textvariable=self.size_y_var)
        self.size_y_entry.pack(fill=tk.X, pady=2)

        ttk.Label(left, text="pixelCountPerMeter").pack(anchor="w")
        self.ppm_entry = ttk.Entry(left, textvariable=self.ppm_var)
        self.ppm_entry.pack(fill=tk.X, pady=2)

        ttk.Checkbutton(left, text="colorInverted", variable=self.inverted_var).pack(anchor="w", pady=4)
        ttk.Button(left, text="Калибровать pixelPerMeter", command=self.calibrate_ppm_from_dxf).pack(fill=tk.X, pady=2)
        self.dxf_info_var = tk.StringVar(value="DXF: не загружен")
        ttk.Label(left, textvariable=self.dxf_info_var, foreground="#555").pack(anchor="w", pady=2)

        ttk.Separator(left).pack(fill=tk.X, pady=8)

        ttk.Label(left, text="Параметры маркера", font=("TkDefaultFont", 10, "bold")).pack(anchor="w")

        self.dict_var = tk.StringVar(value="DICT_4X4_50")
        ttk.Label(left, text="Словарь").pack(anchor="w")
        self.dict_box = ttk.Combobox(left, textvariable=self.dict_var, values=sorted(ARUCO_DICTS.keys()), state="readonly")
        self.dict_box.pack(fill=tk.X, pady=2)

        self.id_var = tk.IntVar(value=0)
        ttk.Label(left, text="ID").pack(anchor="w")
        self.id_spin = ttk.Spinbox(left, from_=0, to=2000, textvariable=self.id_var)
        self.id_spin.pack(fill=tk.X, pady=2)

        self.size_px_var = tk.IntVar(value=120)
        ttk.Label(left, text="Размер на фоне (px)").pack(anchor="w")
        self.size_px_spin = ttk.Spinbox(left, from_=20, to=2000, textvariable=self.size_px_var)
        self.size_px_spin.pack(fill=tk.X, pady=2)

        self.size_mm_var = tk.DoubleVar(value=220.0)
        ttk.Label(left, text="Реальный размер (mm)").pack(anchor="w")
        self.size_mm_entry = ttk.Entry(left, textvariable=self.size_mm_var)
        self.size_mm_entry.pack(fill=tk.X, pady=2)
        ttk.Checkbutton(
            left,
            text="Авторасчет размера в px",
            variable=self.auto_marker_px_var,
            command=self.on_auto_marker_px_toggle,
        ).pack(anchor="w", pady=2)

        self.rotation_var = tk.DoubleVar(value=0.0)
        ttk.Label(left, text="Yaw / поворот (deg)").pack(anchor="w")
        self.rotation_entry = ttk.Entry(left, textvariable=self.rotation_var)
        self.rotation_entry.pack(fill=tk.X, pady=2)

        self.place_with_mouse_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(
            left,
            text="Разместить маркер мышкой (1 клик)",
            variable=self.place_with_mouse_var,
            command=self.on_place_mode_toggle,
        ).pack(fill=tk.X, pady=4)

        ttk.Label(left, text="Клик по изображению: добавить маркер", foreground="#555").pack(anchor="w", pady=6)
        ttk.Label(left, text="Или введите координаты (m) и нажмите Enter", foreground="#555").pack(anchor="w")

        coord_row = ttk.Frame(left)
        coord_row.pack(fill=tk.X, pady=4)
        self.coord_x_m_var = tk.DoubleVar(value=0.0)
        self.coord_y_m_var = tk.DoubleVar(value=0.0)
        ttk.Label(coord_row, text="x").pack(side=tk.LEFT)
        self.coord_x_entry = ttk.Entry(coord_row, textvariable=self.coord_x_m_var, width=10)
        self.coord_x_entry.pack(side=tk.LEFT, padx=(4, 10))
        ttk.Label(coord_row, text="y").pack(side=tk.LEFT)
        self.coord_y_entry = ttk.Entry(coord_row, textvariable=self.coord_y_m_var, width=10)
        self.coord_y_entry.pack(side=tk.LEFT, padx=4)
        ttk.Button(left, text="Удалить выбранный", command=self.delete_selected).pack(fill=tk.X, pady=3)
        ttk.Button(left, text="Очистить все", command=self.clear_markers).pack(fill=tk.X, pady=2)

        ttk.Separator(left).pack(fill=tk.X, pady=8)

        ttk.Button(left, text="Сохранить проект в папку", command=self.export_project_folder).pack(fill=tk.X, pady=3)
        ttk.Button(left, text="Импорт JSON схемы", command=self.import_layout).pack(fill=tk.X, pady=3)

        ttk.Label(left, text="Список маркеров", font=("TkDefaultFont", 10, "bold")).pack(anchor="w", pady=(10, 0))
        cols = ("idx", "dict", "id", "x_m", "y_m", "px", "mm", "yaw")
        self.tree = ttk.Treeview(left, columns=cols, show="headings", height=18, style="MarkerTree.Treeview", selectmode="extended")
        for c in cols:
            self.tree.heading(c, text=c)
            self.tree.column(c, width=58 if c in ("idx", "id") else 84, anchor=tk.CENTER)
        self.tree.pack(fill=tk.BOTH, expand=True, pady=4)
        self.tree.bind("<<TreeviewSelect>>", self.on_tree_select)
        self.tree.bind("<MouseWheel>", self.on_tree_wheel)
        self.tree.bind("<Button-4>", lambda _e: self.on_tree_wheel_linux(-1))
        self.tree.bind("<Button-5>", lambda _e: self.on_tree_wheel_linux(1))
        ttk.Label(left, text="Выделите несколько строк для комплексного экспорта", foreground="#555").pack(anchor="w", pady=(0, 6))

        self.canvas = tk.Canvas(right, bg="#1f1f1f", highlightthickness=0)
        self.canvas.pack(fill=tk.BOTH, expand=True, padx=8, pady=8)
        self.canvas.bind("<Button-1>", self.on_canvas_click)
        self.canvas.bind("<Configure>", lambda _e: self.redraw())
        self.canvas.bind("<MouseWheel>", self.on_canvas_wheel)
        self.canvas.bind("<Button-4>", lambda e: self.on_canvas_wheel_linux(e, +1))
        self.canvas.bind("<Button-5>", lambda e: self.on_canvas_wheel_linux(e, -1))
        self.canvas.bind("<ButtonPress-2>", self.on_pan_start)
        self.canvas.bind("<B2-Motion>", self.on_pan_move)
        self.canvas.bind("<ButtonRelease-2>", self.on_pan_end)
        self.bind_form_commit_keys()
        self.bind_no_wheel_value_change()
        self.on_auto_marker_px_toggle()

    def load_background(self):
        path = self.askopenfilename_big(filetypes=[("Images", "*.png *.jpg *.jpeg *.bmp *.tif *.tiff")])
        if not path:
            return
        bgr = cv2.imread(path, cv2.IMREAD_COLOR)
        if bgr is None:
            messagebox.showerror("Ошибка", "Не удалось открыть изображение")
            return
        self.background_path = Path(path)
        self.background_rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
        self.update_size_px_from_mm()
        self.refresh_tree()
        self.redraw()

    def load_dxf(self):
        if ezdxf is None:
            messagebox.showerror("Ошибка", "Для DXF нужен пакет ezdxf. Установите: pip install ezdxf")
            return
        path = self.askopenfilename_big(filetypes=[("DXF", "*.dxf")])
        if not path:
            return
        try:
            doc = ezdxf.readfile(path)
            msp = doc.modelspace()
            min_x, min_y, max_x, max_y = self.get_dxf_extents(doc, msp)
            sx = float(max_x - min_x)
            sy = float(max_y - min_y)
            if sx <= 0 or sy <= 0:
                raise ValueError("Не удалось определить габариты DXF")
            factor = self.dxf_units_to_m(doc)
            self.dxf_size_x_m = sx * factor
            self.dxf_size_y_m = sy * factor
            self.dxf_path = Path(path)
            self.dxf_info_var.set(f"DXF: {self.dxf_size_x_m:.3f}m x {self.dxf_size_y_m:.3f}m")
            self.size_x_var.set(round(self.dxf_size_x_m, 3))
            self.size_y_var.set(round(self.dxf_size_y_m, 3))
        except Exception as exc:
            messagebox.showerror("Ошибка DXF", f"Не удалось прочитать DXF:\n{exc}")
            return

    @staticmethod
    def dxf_units_to_m(doc):
        # INSUNITS code map (AutoCAD). Fallback to millimeters.
        code = int(doc.header.get("$INSUNITS", 4))
        unit_to_m = {
            0: 0.001,   # unitless -> assume mm
            1: 0.0254,  # inches
            2: 0.3048,  # feet
            4: 0.001,   # mm
            5: 0.01,    # cm
            6: 1.0,     # m
            14: 0.1,    # decimeters
        }
        return unit_to_m.get(code, 0.001)

    @staticmethod
    def get_dxf_extents(doc, msp):
        # 1) Newer ezdxf: addon bbox
        try:
            from ezdxf import bbox as ezbbox

            bb = ezbbox.extents(msp)
            if bb is not None:
                return float(bb.extmin.x), float(bb.extmin.y), float(bb.extmax.x), float(bb.extmax.y)
        except Exception:
            pass

        # 2) Header extents fallback
        try:
            extmin = doc.header.get("$EXTMIN")
            extmax = doc.header.get("$EXTMAX")
            if extmin is not None and extmax is not None:
                min_x, min_y = float(extmin[0]), float(extmin[1])
                max_x, max_y = float(extmax[0]), float(extmax[1])
                if max_x > min_x and max_y > min_y:
                    return min_x, min_y, max_x, max_y
        except Exception:
            pass

        # 3) Manual scan for common entity types
        min_x = float("inf")
        min_y = float("inf")
        max_x = float("-inf")
        max_y = float("-inf")

        def upd(x, y):
            nonlocal min_x, min_y, max_x, max_y
            min_x = min(min_x, x)
            min_y = min(min_y, y)
            max_x = max(max_x, x)
            max_y = max(max_y, y)

        for e in msp:
            t = e.dxftype()
            try:
                if t == "LINE":
                    p1, p2 = e.dxf.start, e.dxf.end
                    upd(float(p1.x), float(p1.y))
                    upd(float(p2.x), float(p2.y))
                elif t in ("LWPOLYLINE", "POLYLINE"):
                    for p in e.get_points("xy"):
                        upd(float(p[0]), float(p[1]))
                elif t in ("CIRCLE",):
                    c = e.dxf.center
                    r = float(e.dxf.radius)
                    upd(float(c.x - r), float(c.y - r))
                    upd(float(c.x + r), float(c.y + r))
                elif t in ("ARC",):
                    # conservative bbox: whole circle by arc radius
                    c = e.dxf.center
                    r = float(e.dxf.radius)
                    upd(float(c.x - r), float(c.y - r))
                    upd(float(c.x + r), float(c.y + r))
                elif t in ("POINT", "INSERT"):
                    p = e.dxf.insert
                    upd(float(p.x), float(p.y))
            except Exception:
                continue

        if not math.isfinite(min_x) or not math.isfinite(min_y) or not math.isfinite(max_x) or not math.isfinite(max_y):
            raise ValueError("DXF не содержит поддерживаемых примитивов для вычисления габарита")
        return min_x, min_y, max_x, max_y

    def calibrate_ppm_from_dxf(self):
        if self.background_rgb is None:
            messagebox.showwarning("Внимание", "Сначала загрузите фон")
            return
        size_x_m = float(self.size_x_var.get())
        size_y_m = float(self.size_y_var.get())
        if size_x_m <= 0 or size_y_m <= 0:
            messagebox.showwarning("Внимание", "sizeX и sizeY должны быть больше 0")
            return
        h, w = self.background_rgb.shape[:2]
        ppm_x = w / max(1e-9, size_x_m)
        ppm_y = h / max(1e-9, size_y_m)
        ppm = math.sqrt(max(1e-12, ppm_x * ppm_y))
        self.ppm_var.set(ppm)
        ratio_img = w / max(1e-9, h)
        ratio_target = size_x_m / max(1e-9, size_y_m)
        ratio_err = abs(ratio_img - ratio_target) / max(ratio_target, 1e-9)
        if ratio_err > 0.03:
            messagebox.showwarning(
                "Предупреждение калибровки",
                (
                    "Пропорции фона и sizeX/sizeY отличаются более чем на 3%.\n"
                    "Использован сбалансированный ppm (геометрическое среднее),\n"
                    "но по одной оси будет остаточная ошибка масштаба."
                ),
            )
        self.update_size_px_from_mm()
        self.refresh_tree()
        self.redraw()

    def on_canvas_click(self, event):
        if self.background_rgb is None:
            return
        if not self.place_with_mouse_var.get():
            return
        img_x, img_y = self.canvas_to_image(event.x, event.y)
        if img_x is None:
            return

        self.add_marker_by_px(float(img_x), float(img_y))
        self.place_with_mouse_var.set(False)

    def add_marker_by_px(self, cx_px: float, cy_px: float):
        marker = Marker(
            marker_id=int(self.id_var.get()),
            dictionary=self.dict_var.get(),
            cx_px=cx_px,
            cy_px=cy_px,
            size_px=int(self.size_px_var.get()),
            size_mm=float(self.size_mm_var.get()),
            rotation_deg=float(self.rotation_var.get()),
        )
        self.markers.append(marker)
        new_idx = len(self.markers) - 1
        x_m, y_m = self.px_to_m(cx_px, cy_px)
        self.coord_x_m_var.set(x_m)
        self.coord_y_m_var.set(y_m)
        self.select_marker_index(new_idx)
        self.update_scheme_size_fields()

    def add_marker_from_inputs(self):
        if self.background_rgb is None:
            messagebox.showwarning("Внимание", "Сначала загрузите фон")
            return
        x_m = float(self.coord_x_m_var.get())
        y_m = float(self.coord_y_m_var.get())
        cx_px, cy_px = self.m_to_px(x_m, y_m)
        self.add_marker_by_px(cx_px, cy_px)

    def on_place_mode_toggle(self):
        if self.place_with_mouse_var.get():
            self.id_var.set(self.next_marker_id())

    def next_marker_id(self):
        if not self.markers:
            return int(self.id_var.get())
        return max(m.marker_id for m in self.markers) + 1

    def load_selected_into_form(self):
        sel = self.tree.selection()
        if len(sel) != 1:
            return
        idx = self.selected_marker_index
        if idx is None:
            return
        if idx < 0 or idx >= len(self.markers):
            return
        m = self.markers[idx]
        x_m, y_m = self.px_to_m(m.cx_px, m.cy_px)
        self._form_sync_in_progress = True
        self.dict_var.set(m.dictionary)
        self.id_var.set(int(m.marker_id))
        self.size_mm_var.set(float(m.size_mm))
        self.rotation_var.set(float(m.rotation_deg))
        self.coord_x_m_var.set(float(x_m))
        self.coord_y_m_var.set(float(y_m))
        if not self.auto_marker_px_var.get():
            self.size_px_var.set(int(m.size_px))
        else:
            self.update_size_px_from_mm()
        self._form_sync_in_progress = False

    def update_selected_marker(self):
        if len(self.tree.selection()) != 1:
            return
        idx = self.selected_marker_index
        if idx is None:
            return
        if idx < 0 or idx >= len(self.markers):
            return
        if self.background_rgb is None:
            messagebox.showwarning("Внимание", "Сначала загрузите фон")
            return

        x_m = float(self.coord_x_m_var.get())
        y_m = float(self.coord_y_m_var.get())
        cx_px, cy_px = self.m_to_px(x_m, y_m)

        m = self.markers[idx]
        m.dictionary = self.dict_var.get()
        m.marker_id = int(self.id_var.get())
        m.cx_px = float(cx_px)
        m.cy_px = float(cy_px)
        m.size_mm = float(self.size_mm_var.get())
        m.rotation_deg = float(self.rotation_var.get())
        m.size_px = int(self.size_px_var.get())
        self.update_scheme_size_fields()

    def bind_form_commit_keys(self):
        widgets = [
            self.size_x_entry,
            self.size_y_entry,
            self.ppm_entry,
            self.id_spin,
            self.size_px_spin,
            self.size_mm_entry,
            self.rotation_entry,
            self.coord_x_entry,
            self.coord_y_entry,
        ]
        for w in widgets:
            w.bind("<Return>", self.apply_form_changes)
            w.bind("<KP_Enter>", self.apply_form_changes)
        self.dict_box.bind("<<ComboboxSelected>>", self.apply_form_changes)

    def apply_form_changes(self, _event=None):
        if self._form_sync_in_progress:
            return
        self.update_size_px_from_mm()
        self.update_selected_marker()
        self.update_scheme_size_fields()

    def select_marker_index(self, idx: int):
        self.selected_marker_index = idx
        children = self.tree.get_children()
        if idx < 0 or idx >= len(children):
            return
        item = children[idx]
        self.tree.selection_set(item)
        self.tree.focus(item)
        self.tree.see(item)
        self.load_selected_into_form()

    def on_tree_select(self, _event=None):
        sel = self.tree.selection()
        if not sel:
            self.selected_marker_index = None
            return
        if len(sel) != 1:
            # Multi-select is for complex export; keep current editor state untouched.
            return
        idx = self.tree.index(sel[0])
        if idx < 0 or idx >= len(self.markers):
            self.selected_marker_index = None
            return
        self.selected_marker_index = idx
        self.load_selected_into_form()

    def canvas_to_image(self, cx, cy):
        if self.background_rgb is None:
            return None, None
        h, w = self.background_rgb.shape[:2]
        cw = max(1, self.canvas.winfo_width())
        ch = max(1, self.canvas.winfo_height())

        fit = min(cw / w, ch / h)
        self.scale = fit * self.zoom
        sw, sh = int(w * self.scale), int(h * self.scale)
        ox = (cw - sw) / 2.0 + self.pan_x
        oy = (ch - sh) / 2.0 + self.pan_y

        if cx < ox or cy < oy or cx >= ox + sw or cy >= oy + sh:
            return None, None

        img_x = (cx - ox) / self.scale
        img_y = (cy - oy) / self.scale
        return img_x, img_y

    def image_to_canvas(self, ix, iy):
        h, w = self.background_rgb.shape[:2]
        cw = max(1, self.canvas.winfo_width())
        ch = max(1, self.canvas.winfo_height())

        fit = min(cw / w, ch / h)
        self.scale = fit * self.zoom
        sw, sh = int(w * self.scale), int(h * self.scale)
        ox = (cw - sw) / 2.0 + self.pan_x
        oy = (ch - sh) / 2.0 + self.pan_y

        return ox + ix * self.scale, oy + iy * self.scale

    def on_canvas_wheel_linux(self, event, direction):
        class E:
            pass
        e = E()
        e.x = event.x
        e.y = event.y
        e.delta = 120 if direction > 0 else -120
        self.on_canvas_wheel(e)

    def on_canvas_wheel(self, event):
        if self.background_rgb is None:
            return
        old_zoom = self.zoom
        factor = 1.1 if event.delta > 0 else 0.9
        new_zoom = max(0.2, min(10.0, old_zoom * factor))
        if abs(new_zoom - old_zoom) < 1e-9:
            return
        ix, iy = self.canvas_to_image(event.x, event.y)
        self.zoom = new_zoom
        if ix is not None:
            cx2, cy2 = self.image_to_canvas(ix, iy)
            self.pan_x += (event.x - cx2)
            self.pan_y += (event.y - cy2)
        self.redraw()

    def is_descendant(self, widget, parent):
        while widget is not None:
            if widget == parent:
                return True
            widget = widget.master
        return False

    def on_param_wheel(self, event):
        self.left_canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")
        return "break"

    def on_param_wheel_linux(self, direction):
        self.left_canvas.yview_scroll(direction, "units")
        return "break"

    def on_tree_wheel(self, event):
        self.tree.yview_scroll(int(-1 * (event.delta / 120)), "units")
        return "break"

    def on_tree_wheel_linux(self, direction):
        self.tree.yview_scroll(direction, "units")
        return "break"

    def bind_no_wheel_value_change(self):
        widgets = [
            self.size_x_entry,
            self.size_y_entry,
            self.ppm_entry,
            self.id_spin,
            self.size_px_spin,
            self.size_mm_entry,
            self.rotation_entry,
            self.coord_x_entry,
            self.coord_y_entry,
            self.dict_box,
        ]
        for w in widgets:
            w.bind("<MouseWheel>", self.on_param_wheel)
            w.bind("<Button-4>", lambda _e: self.on_param_wheel_linux(-1))
            w.bind("<Button-5>", lambda _e: self.on_param_wheel_linux(1))

    def on_pan_start(self, event):
        self._pan_last = (event.x, event.y)

    def on_pan_move(self, event):
        if self._pan_last is None:
            return
        dx = event.x - self._pan_last[0]
        dy = event.y - self._pan_last[1]
        self._pan_last = (event.x, event.y)
        self.pan_x += dx
        self.pan_y += dy
        self.redraw()

    def on_pan_end(self, _event):
        self._pan_last = None

    def px_to_m(self, cx_px: float, cy_px: float):
        if self.background_rgb is None:
            return 0.0, 0.0
        ppm = float(self.ppm_var.get())
        if ppm <= 0:
            ppm = 1.0
        h, w = self.background_rgb.shape[:2]
        x_m = (cx_px - (w / 2.0)) / ppm
        y_m = ((h / 2.0) - cy_px) / ppm
        return x_m, y_m

    def m_to_px(self, x_m: float, y_m: float):
        if self.background_rgb is None:
            return 0.0, 0.0
        ppm = float(self.ppm_var.get())
        if ppm <= 0:
            ppm = 1.0
        h, w = self.background_rgb.shape[:2]
        cx_px = (w / 2.0) + x_m * ppm
        cy_px = (h / 2.0) - y_m * ppm
        return cx_px, cy_px

    def update_scheme_size_fields(self):
        # Legacy hook: now sizeX/sizeY are always manual.
        self.update_size_px_from_mm()
        self.refresh_tree()
        self.redraw()

    def on_auto_marker_px_toggle(self):
        state = "disabled" if self.auto_marker_px_var.get() else "normal"
        self.size_px_spin.configure(state=state)
        self.update_size_px_from_mm()

    def update_size_px_from_mm(self):
        if not self.auto_marker_px_var.get():
            return
        ppm = float(self.ppm_var.get())
        size_mm = float(self.size_mm_var.get())
        if ppm <= 0 or size_mm <= 0:
            return
        size_px = max(20, int(round((size_mm / 1000.0) * ppm)))
        self.size_px_var.set(size_px)

    def render_marker_rgb(self, marker: Marker, side_px: int):
        dictionary = cv2.aruco.getPredefinedDictionary(ARUCO_DICTS[marker.dictionary])
        marker_img = cv2.aruco.generateImageMarker(dictionary, marker.marker_id, side_px)
        rgb = cv2.cvtColor(marker_img, cv2.COLOR_GRAY2RGB)

        if self.inverted_var.get():
            rgb = 255 - rgb

        if abs(marker.rotation_deg) > 1e-6:
            c = side_px / 2.0
            M = cv2.getRotationMatrix2D((c, c), marker.rotation_deg, 1.0)
            rgb = cv2.warpAffine(rgb, M, (side_px, side_px), flags=cv2.INTER_NEAREST, borderValue=(255, 255, 255))
        return rgb

    def compose_preview(self):
        if self.background_rgb is None:
            return None
        out = self.background_rgb.copy()
        h, w = out.shape[:2]

        for m in self.markers:
            side = max(20, int(m.size_px))
            marker_rgb = self.render_marker_rgb(m, side)
            x0 = int(round(m.cx_px - side / 2))
            y0 = int(round(m.cy_px - side / 2))
            x1 = x0 + side
            y1 = y0 + side

            if x1 <= 0 or y1 <= 0 or x0 >= w or y0 >= h:
                continue

            cx0 = max(0, x0)
            cy0 = max(0, y0)
            cx1 = min(w, x1)
            cy1 = min(h, y1)

            mx0 = cx0 - x0
            my0 = cy0 - y0
            mx1 = mx0 + (cx1 - cx0)
            my1 = my0 + (cy1 - cy0)

            out[cy0:cy1, cx0:cx1] = marker_rgb[my0:my1, mx0:mx1]

        return out

    def redraw(self):
        self.canvas.delete("all")
        if self.background_rgb is None:
            return

        preview = self.compose_preview()
        h, w = preview.shape[:2]
        cw = max(1, self.canvas.winfo_width())
        ch = max(1, self.canvas.winfo_height())

        scale = min(cw / w, ch / h) * self.zoom
        sw, sh = int(w * scale), int(h * scale)
        sw = max(1, sw)
        sh = max(1, sh)
        resized = cv2.resize(preview, (sw, sh), interpolation=cv2.INTER_AREA)

        self.tk_image = ImageTk.PhotoImage(Image.fromarray(resized))
        ox = int((cw - sw) / 2 + self.pan_x)
        oy = int((ch - sh) / 2 + self.pan_y)
        self.canvas.create_image(ox, oy, anchor=tk.NW, image=self.tk_image)

        for i, m in enumerate(self.markers):
            x, y = self.image_to_canvas(m.cx_px, m.cy_px)
            r = (m.size_px * scale) / 2
            x_m, y_m = self.px_to_m(m.cx_px, m.cy_px)
            self.canvas.create_rectangle(x - r, y - r, x + r, y + r, outline="#00d7ff", width=2)
            self.canvas.create_text(
                x,
                y - r - 10,
                text=f"#{i} id={m.marker_id} ({x_m:.3f},{y_m:.3f})m",
                fill="#00d7ff",
                font=("TkDefaultFont", 9, "bold"),
            )

    def refresh_tree(self):
        prev = self.selected_marker_index
        for item in self.tree.get_children():
            self.tree.delete(item)
        for i, m in enumerate(self.markers):
            x_m, y_m = self.px_to_m(m.cx_px, m.cy_px)
            self.tree.insert(
                "",
                tk.END,
                values=(
                    i,
                    m.dictionary,
                    m.marker_id,
                    round(x_m, 4),
                    round(y_m, 4),
                    m.size_px,
                    round(m.size_mm, 2),
                    round(m.rotation_deg, 2),
                ),
            )
        if prev is not None and 0 <= prev < len(self.markers):
            self.select_marker_index(prev)
        elif self.markers:
            self.select_marker_index(0)
        else:
            self.selected_marker_index = None

    def delete_selected(self):
        idx = self.selected_marker_index
        if idx is None:
            return
        if idx < 0 or idx >= len(self.markers):
            return
        self.markers.pop(idx)
        if not self.markers:
            self.selected_marker_index = None
        elif idx >= len(self.markers):
            self.selected_marker_index = len(self.markers) - 1
        else:
            self.selected_marker_index = idx
        self.update_scheme_size_fields()

    def clear_markers(self):
        self.markers.clear()
        self.update_scheme_size_fields()

    def scheme_payload(self):
        markers = []
        for m in self.markers:
            x_m, y_m = self.px_to_m(m.cx_px, m.cy_px)
            markers.append(
                {
                    "id": int(m.marker_id),
                    "type": DICT_TO_SCHEME_TYPE.get(m.dictionary, "Aruco_4x4_50"),
                    "x": float(x_m),
                    "y": float(y_m),
                    "size": float(m.size_mm) / 1000.0,
                    "yaw": float(m.rotation_deg),
                }
            )

        return {
            "sizeX": float(self.size_x_var.get()),
            "sizeY": float(self.size_y_var.get()),
            "pixelCountPerMeter": float(self.ppm_var.get()),
            "colorInverted": bool(self.inverted_var.get()),
            "markers": markers,
        }

    def export_project_folder(self):
        if self.background_rgb is None:
            messagebox.showwarning("Внимание", "Сначала загрузите фон")
            return

        folder = self.askdirectory_big(title="Выберите папку проекта")
        if not folder:
            return

        out_dir = Path(folder)
        out_dir.mkdir(parents=True, exist_ok=True)

        payload = self.scheme_payload()
        json_path = out_dir / "scheme.json"
        json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

        selected = set(self.get_selected_marker_indices())
        group_markers = [self.markers[i] for i in sorted(selected) if 0 <= i < len(self.markers)]

        if len(group_markers) >= 2:
            self.save_complex_marker_group(group_markers, out_dir)

        for i, m in enumerate(self.markers):
            if i in selected and len(group_markers) >= 2:
                continue
            size_m = float(m.size_mm) / 1000.0
            ppm_export = max(self.EXPORT_PPM_MIN, int(round(float(self.ppm_var.get()))))
            side = max(200, int(round(size_m * ppm_export)))
            marker_rgb = self.render_marker_rgb(m, side)
            marker_bgr = cv2.cvtColor(marker_rgb, cv2.COLOR_RGB2BGR)

            size_mm_tag = self.format_mm_tag(m.size_mm)
            stem = f"id{m.marker_id}_{size_mm_tag}mm"

            png_path = out_dir / f"{stem}.png"
            dpi = max(150.0, ppm_export * 0.0254)
            Image.fromarray(cv2.cvtColor(marker_bgr, cv2.COLOR_BGR2RGB)).save(png_path, dpi=(dpi, dpi))

            svg_path = out_dir / f"{stem}.svg"
            self.save_single_marker_svg(m, svg_path)

        preview = self.compose_preview()
        if preview is not None:
            cv2.imwrite(str(out_dir / "layout.preview.png"), cv2.cvtColor(preview, cv2.COLOR_RGB2BGR))

        messagebox.showinfo("Готово", f"Проект сохранен в:\n{out_dir}")

    def get_selected_marker_indices(self):
        indices = []
        for item in self.tree.selection():
            try:
                indices.append(self.tree.index(item))
            except Exception:
                continue
        return indices

    def save_complex_marker_group(self, markers: List[Marker], out_dir: Path):
        # Export in metric space so marker sizes and gaps are preserved.
        ppm_export = max(self.EXPORT_PPM_MIN, int(round(float(self.ppm_var.get()))))
        # Required polarity: black when colorInverted=true, white when false.
        bg_v = 0 if self.inverted_var.get() else 255
        border_m = 0.01  # 1 cm padding around complex marker

        metric = []
        for m in markers:
            x_m, y_m = self.px_to_m(m.cx_px, m.cy_px)
            size_m = float(m.size_mm) / 1000.0
            half = size_m / 2.0
            metric.append((m, x_m, y_m, size_m, x_m - half, x_m + half, y_m - half, y_m + half))

        min_x = min(v[4] for v in metric)
        max_x = max(v[5] for v in metric)
        min_y = min(v[6] for v in metric)
        max_y = max(v[7] for v in metric)

        w_m = max_x - min_x
        h_m = max_y - min_y
        w_px = max(1, int(math.ceil(w_m * ppm_export)))
        h_px = max(1, int(math.ceil(h_m * ppm_export)))

        canvas = np.full((h_px, w_px, 3), bg_v, dtype=np.uint8)
        for m, x_m, y_m, size_m, *_ in metric:
            side = max(20, int(round(size_m * ppm_export)))
            marker_rgb = self.render_marker_rgb(m, side)
            cx = (x_m - min_x) * ppm_export
            cy = (max_y - y_m) * ppm_export
            x0 = int(round(cx - side / 2))
            y0 = int(round(cy - side / 2))
            x1 = x0 + side
            y1 = y0 + side

            cx0 = max(0, x0)
            cy0 = max(0, y0)
            cx1 = min(w_px, x1)
            cy1 = min(h_px, y1)
            if cx1 <= cx0 or cy1 <= cy0:
                continue
            mx0 = cx0 - x0
            my0 = cy0 - y0
            mx1 = mx0 + (cx1 - cx0)
            my1 = my0 + (cy1 - cy0)
            canvas[cy0:cy1, cx0:cx1] = marker_rgb[my0:my1, mx0:mx1]

        pad_px = max(1, int(round(border_m * ppm_export)))
        canvas = np.pad(canvas, ((pad_px, pad_px), (pad_px, pad_px), (0, 0)), mode="constant", constant_values=bg_v)
        w_m_out = w_m + 2.0 * border_m
        h_m_out = h_m + 2.0 * border_m

        stem = "complex_marker"
        png_path = out_dir / f"{stem}.png"
        dpi = max(150.0, ppm_export * 0.0254)
        Image.fromarray(canvas).save(png_path, dpi=(dpi, dpi))

        svg_path = out_dir / f"{stem}.svg"
        self.save_embedded_png_svg(canvas, svg_path, w_m_out, h_m_out)

    @staticmethod
    def format_mm_tag(size_mm: float):
        txt = f"{size_mm:.3f}".rstrip("0").rstrip(".")
        return txt.replace(".", "_")

    def get_marker_module_matrix(self, marker: Marker):
        dictionary = cv2.aruco.getPredefinedDictionary(ARUCO_DICTS[marker.dictionary])
        marker_size = int(dictionary.markerSize)
        modules_total = marker_size + 2
        side = modules_total * 16
        img = cv2.aruco.generateImageMarker(dictionary, marker.marker_id, side)
        module = side // modules_total
        mat = np.zeros((modules_total, modules_total), dtype=np.uint8)
        for r in range(modules_total):
            for c in range(modules_total):
                block = img[r * module:(r + 1) * module, c * module:(c + 1) * module]
                mat[r, c] = 1 if int(block.mean()) < 128 else 0
        if self.inverted_var.get():
            mat = 1 - mat
        return mat

    @staticmethod
    def _fmt_mm(v_m: float):
        return f"{v_m * 1000.0:.6f}"

    def save_single_marker_svg(self, marker: Marker, svg_path: Path):
        size_m = float(marker.size_mm) / 1000.0
        mat = self.get_marker_module_matrix(marker)
        modules = mat.shape[0]
        border_bit = int(mat[0, 0])  # 1 => black border, 0 => white border
        bg = "black" if border_bit == 1 else "white"
        fg = "white" if border_bit == 1 else "black"
        wmm = self._fmt_mm(size_m)
        hmm = self._fmt_mm(size_m)
        lines = [
            f'<svg xmlns="http://www.w3.org/2000/svg" width="{wmm}mm" height="{hmm}mm" viewBox="0 0 {modules} {modules}" shape-rendering="crispEdges">',
            f'  <rect x="0" y="0" width="{modules}" height="{modules}" fill="{bg}"/>',
        ]
        for r in range(modules):
            for c in range(modules):
                if int(mat[r, c]) != border_bit:
                    lines.append(f'  <rect x="{c}" y="{r}" width="1" height="1" fill="{fg}"/>')
        lines.append("</svg>")
        svg_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    def save_embedded_png_svg(self, image_rgb, svg_path: Path, width_m: float, height_m: float):
        img = Image.fromarray(image_rgb)
        buf = BytesIO()
        img.save(buf, format="PNG")
        b64 = base64.b64encode(buf.getvalue()).decode("ascii")
        w_px, h_px = image_rgb.shape[1], image_rgb.shape[0]
        wmm = self._fmt_mm(width_m)
        hmm = self._fmt_mm(height_m)
        svg = (
            f'<svg xmlns="http://www.w3.org/2000/svg" width="{wmm}mm" height="{hmm}mm" viewBox="0 0 {w_px} {h_px}">\n'
            f'  <image href="data:image/png;base64,{b64}" x="0" y="0" width="{w_px}" height="{h_px}" image-rendering="pixelated"/>\n'
            f'</svg>\n'
        )
        svg_path.write_text(svg, encoding="utf-8")

    def import_layout(self):
        path = self.askopenfilename_big(filetypes=[("JSON", "*.json")])
        if not path:
            return

        data = json.loads(Path(path).read_text(encoding="utf-8"))
        imported_size_x = float(data.get("sizeX", self.size_x_var.get()))
        imported_size_y = float(data.get("sizeY", self.size_y_var.get()))
        imported_ppm = float(data.get("pixelCountPerMeter", self.ppm_var.get()))
        self.size_x_var.set(imported_size_x)
        self.size_y_var.set(imported_size_y)
        self.ppm_var.set(imported_ppm)
        self.inverted_var.set(bool(data.get("colorInverted", self.inverted_var.get())))

        # Ensure we have a drawable surface even if user imports JSON before loading any image.
        if self.background_rgb is None:
            ppm = max(1.0, float(self.ppm_var.get()))
            w_px = max(200, int(round(float(self.size_x_var.get()) * ppm)))
            h_px = max(200, int(round(float(self.size_y_var.get()) * ppm)))
            self.background_rgb = np.full((h_px, w_px, 3), 255, dtype=np.uint8)
            self.background_path = None
        # If a background is already loaded, keep current calibration/ppm.
        # Import should not silently re-calibrate scale.

        self.markers.clear()
        for raw in data.get("markers", []):
            dictionary = SCHEME_TYPE_TO_DICT.get(str(raw.get("type", "Aruco_4x4_50")), "DICT_4X4_50")
            x_m = float(raw.get("x", 0.0))
            y_m = float(raw.get("y", 0.0))
            cx_px, cy_px = self.m_to_px(x_m, y_m)
            size_m = float(raw.get("size", 0.1))
            size_mm = size_m * 1000.0
            size_px = max(20, int(round(size_m * float(self.ppm_var.get()))))

            self.markers.append(
                Marker(
                    marker_id=int(raw.get("id", 0)),
                    dictionary=dictionary,
                    cx_px=float(cx_px),
                    cy_px=float(cy_px),
                    size_px=size_px,
                    size_mm=size_mm,
                    rotation_deg=float(raw.get("yaw", 0.0)),
                )
            )

        self.update_scheme_size_fields()

    def askopenfilename_big(self, **kwargs):
        scale = float(self.root.tk.call("tk", "scaling"))
        try:
            self.root.tk.call("tk", "scaling", scale * 1.8)
            return filedialog.askopenfilename(parent=self.root, **kwargs)
        finally:
            self.root.tk.call("tk", "scaling", scale)

    def askdirectory_big(self, **kwargs):
        scale = float(self.root.tk.call("tk", "scaling"))
        try:
            self.root.tk.call("tk", "scaling", scale * 1.8)
            return filedialog.askdirectory(parent=self.root, **kwargs)
        finally:
            self.root.tk.call("tk", "scaling", scale)

    def _init_left_panel_width(self):
        def apply():
            total_w = max(1, self.main_pane.winfo_width())
            desired = 560
            # Keep right pane visible even on smaller screens.
            pos = min(desired, max(420, total_w - 520))
            try:
                self.main_pane.sashpos(0, pos)
            except Exception:
                pass

        # Apply a few times during initial layout pass (WM can override early values).
        self.root.after(10, apply)
        self.root.after(80, apply)
        self.root.after(200, apply)


def main():
    root = tk.Tk()
    ArucoLayoutApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
