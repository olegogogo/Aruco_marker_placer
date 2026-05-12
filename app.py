#!/usr/bin/env python3
import base64
import json
import math
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
        self._build_ui()

    def _build_ui(self):
        style = ttk.Style()
        style.configure("MarkerTree.Treeview", rowheight=28)

        main = ttk.Panedwindow(self.root, orient=tk.HORIZONTAL)
        main.pack(fill=tk.BOTH, expand=True)

        left_wrap = ttk.Frame(main, width=380)
        left_wrap.pack_propagate(False)

        left_canvas = tk.Canvas(left_wrap, highlightthickness=0)
        left_scroll = ttk.Scrollbar(left_wrap, orient=tk.VERTICAL, command=left_canvas.yview)
        left_canvas.configure(yscrollcommand=left_scroll.set)
        left_canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(8, 0), pady=8)
        left_scroll.pack(side=tk.RIGHT, fill=tk.Y)

        left = ttk.Frame(left_canvas)
        left_window = left_canvas.create_window((0, 0), window=left, anchor="nw")

        def _sync_left_scroll(_event=None):
            left_canvas.configure(scrollregion=left_canvas.bbox("all"))

        def _sync_left_width(event):
            left_canvas.itemconfigure(left_window, width=event.width)

        left.bind("<Configure>", _sync_left_scroll)
        left_canvas.bind("<Configure>", _sync_left_width)

        def _on_mousewheel(event):
            left_canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

        left_canvas.bind("<MouseWheel>", _on_mousewheel)
        left_canvas.bind("<Button-4>", lambda _e: left_canvas.yview_scroll(-1, "units"))
        left_canvas.bind("<Button-5>", lambda _e: left_canvas.yview_scroll(1, "units"))

        right = ttk.Frame(main)
        main.add(left_wrap, weight=0)
        main.add(right, weight=1)
        main.sashpos(0, 430)

        ttk.Label(left, text="Фон (чертеж/изображение)", font=("TkDefaultFont", 10, "bold")).pack(anchor="w")
        ttk.Button(left, text="Загрузить фон", command=self.load_background).pack(fill=tk.X, pady=4)
        ttk.Button(left, text="Загрузить DXF", command=self.load_dxf).pack(fill=tk.X, pady=2)
        ttk.Button(left, text="Калибровать ppm по DXF", command=self.calibrate_ppm_from_dxf).pack(fill=tk.X, pady=2)
        self.dxf_info_var = tk.StringVar(value="DXF: не загружен")
        ttk.Label(left, textvariable=self.dxf_info_var, foreground="#555").pack(anchor="w", pady=2)

        ttk.Separator(left).pack(fill=tk.X, pady=8)

        ttk.Label(left, text="Параметры схемы (JSON)", font=("TkDefaultFont", 10, "bold")).pack(anchor="w")
        self.size_x_var = tk.DoubleVar(value=0.9)
        self.size_y_var = tk.DoubleVar(value=0.9)
        self.ppm_var = tk.DoubleVar(value=2500.0)
        self.inverted_var = tk.BooleanVar(value=True)
        self.auto_size_var = tk.BooleanVar(value=True)
        self.auto_marker_px_var = tk.BooleanVar(value=True)

        ttk.Label(left, text="sizeX (m)").pack(anchor="w")
        self.size_x_entry = ttk.Entry(left, textvariable=self.size_x_var)
        self.size_x_entry.pack(fill=tk.X, pady=2)

        ttk.Label(left, text="sizeY (m)").pack(anchor="w")
        self.size_y_entry = ttk.Entry(left, textvariable=self.size_y_var)
        self.size_y_entry.pack(fill=tk.X, pady=2)

        ttk.Label(left, text="pixelCountPerMeter").pack(anchor="w")
        ttk.Entry(left, textvariable=self.ppm_var).pack(fill=tk.X, pady=2)

        ttk.Checkbutton(left, text="colorInverted", variable=self.inverted_var).pack(anchor="w", pady=4)
        ttk.Checkbutton(
            left,
            text="Авторасчет sizeX/sizeY",
            variable=self.auto_size_var,
            command=self.on_auto_size_toggle,
        ).pack(anchor="w", pady=2)

        ttk.Separator(left).pack(fill=tk.X, pady=8)

        ttk.Label(left, text="Параметры маркера", font=("TkDefaultFont", 10, "bold")).pack(anchor="w")

        self.dict_var = tk.StringVar(value="DICT_4X4_50")
        ttk.Label(left, text="Словарь").pack(anchor="w")
        self.dict_box = ttk.Combobox(left, textvariable=self.dict_var, values=sorted(ARUCO_DICTS.keys()), state="readonly")
        self.dict_box.pack(fill=tk.X, pady=2)

        self.id_var = tk.IntVar(value=0)
        ttk.Label(left, text="ID").pack(anchor="w")
        ttk.Spinbox(left, from_=0, to=2000, textvariable=self.id_var).pack(fill=tk.X, pady=2)

        self.size_px_var = tk.IntVar(value=120)
        ttk.Label(left, text="Размер на фоне (px)").pack(anchor="w")
        self.size_px_spin = ttk.Spinbox(left, from_=20, to=2000, textvariable=self.size_px_var)
        self.size_px_spin.pack(fill=tk.X, pady=2)

        self.size_mm_var = tk.DoubleVar(value=220.0)
        ttk.Label(left, text="Реальный размер (mm)").pack(anchor="w")
        ttk.Entry(left, textvariable=self.size_mm_var).pack(fill=tk.X, pady=2)
        ttk.Checkbutton(
            left,
            text="Авторасчет размера в px",
            variable=self.auto_marker_px_var,
            command=self.on_auto_marker_px_toggle,
        ).pack(anchor="w", pady=2)

        self.rotation_var = tk.DoubleVar(value=0.0)
        ttk.Label(left, text="Yaw / поворот (deg)").pack(anchor="w")
        ttk.Entry(left, textvariable=self.rotation_var).pack(fill=tk.X, pady=2)

        ttk.Label(left, text="Клик по изображению: добавить маркер", foreground="#555").pack(anchor="w", pady=6)
        ttk.Label(left, text="Или введите координаты (m) и нажмите кнопку", foreground="#555").pack(anchor="w")

        coord_row = ttk.Frame(left)
        coord_row.pack(fill=tk.X, pady=4)
        self.coord_x_m_var = tk.DoubleVar(value=0.0)
        self.coord_y_m_var = tk.DoubleVar(value=0.0)
        ttk.Label(coord_row, text="x").pack(side=tk.LEFT)
        ttk.Entry(coord_row, textvariable=self.coord_x_m_var, width=10).pack(side=tk.LEFT, padx=(4, 10))
        ttk.Label(coord_row, text="y").pack(side=tk.LEFT)
        ttk.Entry(coord_row, textvariable=self.coord_y_m_var, width=10).pack(side=tk.LEFT, padx=4)
        ttk.Button(left, text="Добавить маркер по координатам", command=self.add_marker_from_inputs).pack(fill=tk.X, pady=3)
        ttk.Button(left, text="Обновить выбранный маркер", command=self.update_selected_marker).pack(fill=tk.X, pady=2)

        ttk.Button(left, text="Удалить выбранный", command=self.delete_selected).pack(fill=tk.X, pady=3)
        ttk.Button(left, text="Очистить все", command=self.clear_markers).pack(fill=tk.X, pady=2)

        ttk.Separator(left).pack(fill=tk.X, pady=8)

        ttk.Button(left, text="Сохранить проект в папку", command=self.export_project_folder).pack(fill=tk.X, pady=3)
        ttk.Button(left, text="Импорт JSON схемы", command=self.import_layout).pack(fill=tk.X, pady=3)

        ttk.Label(left, text="Список маркеров", font=("TkDefaultFont", 10, "bold")).pack(anchor="w", pady=(10, 0))
        cols = ("idx", "dict", "id", "x_m", "y_m", "px", "mm", "yaw")
        self.tree = ttk.Treeview(left, columns=cols, show="headings", height=18, style="MarkerTree.Treeview")
        for c in cols:
            self.tree.heading(c, text=c)
            self.tree.column(c, width=58 if c in ("idx", "id") else 84, anchor=tk.CENTER)
        self.tree.pack(fill=tk.BOTH, expand=True, pady=4)
        self.tree.bind("<<TreeviewSelect>>", lambda _e: self.load_selected_into_form())

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
        self.ppm_var.trace_add("write", lambda *_: self.update_scheme_size_fields())
        self.size_mm_var.trace_add("write", lambda *_: self.update_size_px_from_mm())
        self.on_auto_size_toggle()
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
        self.update_scheme_size_fields()
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
        except Exception as exc:
            messagebox.showerror("Ошибка DXF", f"Не удалось прочитать DXF:\n{exc}")
            return
        self.calibrate_ppm_from_dxf()

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
        if self.dxf_size_x_m is None or self.dxf_size_y_m is None:
            messagebox.showwarning("Внимание", "Сначала загрузите DXF")
            return
        h, w = self.background_rgb.shape[:2]
        ppm_x = w / max(1e-9, self.dxf_size_x_m)
        ppm_y = h / max(1e-9, self.dxf_size_y_m)
        self.ppm_var.set(min(ppm_x, ppm_y))
        self.update_size_px_from_mm()
        self.update_scheme_size_fields()

    def on_canvas_click(self, event):
        if self.background_rgb is None:
            return
        img_x, img_y = self.canvas_to_image(event.x, event.y)
        if img_x is None:
            return

        self.add_marker_by_px(float(img_x), float(img_y))

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
        x_m, y_m = self.px_to_m(cx_px, cy_px)
        self.coord_x_m_var.set(x_m)
        self.coord_y_m_var.set(y_m)
        self.id_var.set(self.id_var.get() + 1)
        self.update_scheme_size_fields()

    def add_marker_from_inputs(self):
        if self.background_rgb is None:
            messagebox.showwarning("Внимание", "Сначала загрузите фон")
            return
        x_m = float(self.coord_x_m_var.get())
        y_m = float(self.coord_y_m_var.get())
        cx_px, cy_px = self.m_to_px(x_m, y_m)
        self.add_marker_by_px(cx_px, cy_px)

    def load_selected_into_form(self):
        sel = self.tree.selection()
        if not sel:
            return
        idx = self.tree.index(sel[0])
        if idx < 0 or idx >= len(self.markers):
            return
        m = self.markers[idx]
        x_m, y_m = self.px_to_m(m.cx_px, m.cy_px)
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

    def update_selected_marker(self):
        sel = self.tree.selection()
        if not sel:
            messagebox.showwarning("Внимание", "Выберите маркер в списке")
            return
        idx = self.tree.index(sel[0])
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
        if self.background_rgb is None:
            return
        if not self.auto_size_var.get():
            self.refresh_tree()
            self.redraw()
            return
        ppm = float(self.ppm_var.get())
        if ppm <= 0:
            return
        h, w = self.background_rgb.shape[:2]
        bg_size_x_m = w / ppm
        bg_size_y_m = h / ppm

        markers_payload = []
        for m in self.markers:
            x_m, y_m = self.px_to_m(m.cx_px, m.cy_px)
            size_m = float(m.size_mm) / 1000.0
            half = size_m / 2.0
            markers_payload.append((x_m - half, x_m + half, y_m - half, y_m + half))

        if markers_payload:
            min_x = min(v[0] for v in markers_payload)
            max_x = max(v[1] for v in markers_payload)
            min_y = min(v[2] for v in markers_payload)
            max_y = max(v[3] for v in markers_payload)
            marker_size_x_m = max_x - min_x
            marker_size_y_m = max_y - min_y
        else:
            marker_size_x_m = 0.0
            marker_size_y_m = 0.0

        size_x_m = max(bg_size_x_m, marker_size_x_m)
        size_y_m = max(bg_size_y_m, marker_size_y_m)

        # Round up to centimeters (0.01 m).
        size_x_m = math.ceil(size_x_m * 100.0) / 100.0
        size_y_m = math.ceil(size_y_m * 100.0) / 100.0
        self.size_x_var.set(size_x_m)
        self.size_y_var.set(size_y_m)
        self.update_size_px_from_mm()
        self.refresh_tree()
        self.redraw()

    def on_auto_size_toggle(self):
        state = "disabled" if self.auto_size_var.get() else "normal"
        self.size_x_entry.configure(state=state)
        self.size_y_entry.configure(state=state)
        self.update_scheme_size_fields()

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

    def delete_selected(self):
        sel = self.tree.selection()
        if not sel:
            return
        idx = self.tree.index(sel[0])
        self.markers.pop(idx)
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

        for m in self.markers:
            side = max(80, int(m.size_px))
            marker_rgb = self.render_marker_rgb(m, side)
            marker_bgr = cv2.cvtColor(marker_rgb, cv2.COLOR_RGB2BGR)

            size_mm_tag = self.format_mm_tag(m.size_mm)
            stem = f"id{m.marker_id}_{size_mm_tag}mm"

            png_path = out_dir / f"{stem}.png"
            cv2.imwrite(str(png_path), marker_bgr)

            svg_path = out_dir / f"{stem}.svg"
            self.save_svg_with_embedded_png(marker_rgb, svg_path, m.size_mm)

        preview = self.compose_preview()
        if preview is not None:
            cv2.imwrite(str(out_dir / "layout.preview.png"), cv2.cvtColor(preview, cv2.COLOR_RGB2BGR))

        messagebox.showinfo("Готово", f"Проект сохранен в:\n{out_dir}")

    @staticmethod
    def format_mm_tag(size_mm: float):
        txt = f"{size_mm:.3f}".rstrip("0").rstrip(".")
        return txt.replace(".", "_")

    @staticmethod
    def save_svg_with_embedded_png(marker_rgb, svg_path: Path, size_mm: float):
        img = Image.fromarray(marker_rgb)
        buf = BytesIO()
        img.save(buf, format="PNG")
        b64 = base64.b64encode(buf.getvalue()).decode("ascii")

        w_px, h_px = marker_rgb.shape[1], marker_rgb.shape[0]
        size_mm_txt = f"{size_mm:.3f}".rstrip("0").rstrip(".")
        svg = (
            f"<svg xmlns=\"http://www.w3.org/2000/svg\" width=\"{size_mm_txt}mm\" height=\"{size_mm_txt}mm\" "
            f"viewBox=\"0 0 {w_px} {h_px}\">\n"
            f"  <image href=\"data:image/png;base64,{b64}\" x=\"0\" y=\"0\" width=\"{w_px}\" height=\"{h_px}\"/>\n"
            f"</svg>\n"
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
        else:
            # If a background is already loaded, align metric scale to imported scheme size
            # so imported marker coordinates land on visible canvas area.
            h, w = self.background_rgb.shape[:2]
            sx = max(1e-6, imported_size_x)
            sy = max(1e-6, imported_size_y)
            ppm_x = w / sx
            ppm_y = h / sy
            self.ppm_var.set(min(ppm_x, ppm_y))

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


def main():
    root = tk.Tk()
    ArucoLayoutApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
