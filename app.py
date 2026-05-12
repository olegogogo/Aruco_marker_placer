#!/usr/bin/env python3
import json
import math
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import List, Optional

import cv2
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from PIL import Image, ImageTk


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
        self.root.geometry("1400x900")

        self.background_path: Optional[Path] = None
        self.background_bgr = None
        self.background_rgb = None
        self.tk_image = None
        self.scale = 1.0

        self.markers: List[Marker] = []

        self._build_ui()

    def _build_ui(self):
        main = ttk.Frame(self.root)
        main.pack(fill=tk.BOTH, expand=True)

        left = ttk.Frame(main, width=350)
        left.pack(side=tk.LEFT, fill=tk.Y, padx=8, pady=8)

        right = ttk.Frame(main)
        right.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True, padx=8, pady=8)

        ttk.Label(left, text="Фон (чертеж/изображение)", font=("TkDefaultFont", 10, "bold")).pack(anchor="w")
        ttk.Button(left, text="Загрузить фон", command=self.load_background).pack(fill=tk.X, pady=4)

        ttk.Separator(left).pack(fill=tk.X, pady=8)

        ttk.Label(left, text="Параметры маркера", font=("TkDefaultFont", 10, "bold")).pack(anchor="w")

        self.dict_var = tk.StringVar(value="DICT_6X6_250")
        ttk.Label(left, text="Словарь").pack(anchor="w")
        self.dict_box = ttk.Combobox(left, textvariable=self.dict_var, values=sorted(ARUCO_DICTS.keys()), state="readonly")
        self.dict_box.pack(fill=tk.X, pady=2)

        self.id_var = tk.IntVar(value=0)
        ttk.Label(left, text="ID").pack(anchor="w")
        ttk.Spinbox(left, from_=0, to=2000, textvariable=self.id_var).pack(fill=tk.X, pady=2)

        self.size_px_var = tk.IntVar(value=120)
        ttk.Label(left, text="Размер на изображении (px)").pack(anchor="w")
        ttk.Spinbox(left, from_=20, to=1200, textvariable=self.size_px_var).pack(fill=tk.X, pady=2)

        self.size_mm_var = tk.DoubleVar(value=130.0)
        ttk.Label(left, text="Физический размер (mm)").pack(anchor="w")
        ttk.Entry(left, textvariable=self.size_mm_var).pack(fill=tk.X, pady=2)

        self.rotation_var = tk.DoubleVar(value=0.0)
        ttk.Label(left, text="Поворот (deg)").pack(anchor="w")
        ttk.Entry(left, textvariable=self.rotation_var).pack(fill=tk.X, pady=2)

        ttk.Label(left, text="Клик по изображению: добавить маркер", foreground="#555").pack(anchor="w", pady=6)

        ttk.Button(left, text="Удалить выбранный", command=self.delete_selected).pack(fill=tk.X, pady=4)
        ttk.Button(left, text="Очистить все", command=self.clear_markers).pack(fill=tk.X, pady=2)

        ttk.Separator(left).pack(fill=tk.X, pady=8)

        ttk.Button(left, text="Сохранить YAML + Preview", command=self.export_layout).pack(fill=tk.X, pady=3)
        ttk.Button(left, text="Загрузить YAML", command=self.import_layout).pack(fill=tk.X, pady=3)

        ttk.Label(left, text="Список маркеров", font=("TkDefaultFont", 10, "bold")).pack(anchor="w", pady=(10, 0))
        cols = ("idx", "dict", "id", "x", "y", "px", "mm", "rot")
        self.tree = ttk.Treeview(left, columns=cols, show="headings", height=18)
        for c in cols:
            self.tree.heading(c, text=c)
            self.tree.column(c, width=48 if c in ("idx", "id") else 70, anchor=tk.CENTER)
        self.tree.pack(fill=tk.BOTH, expand=True, pady=4)

        self.canvas = tk.Canvas(right, bg="#1f1f1f", highlightthickness=0)
        self.canvas.pack(fill=tk.BOTH, expand=True)
        self.canvas.bind("<Button-1>", self.on_canvas_click)
        self.canvas.bind("<Configure>", lambda _e: self.redraw())

    def load_background(self):
        path = filedialog.askopenfilename(filetypes=[("Images", "*.png *.jpg *.jpeg *.bmp *.tif *.tiff")])
        if not path:
            return
        bgr = cv2.imread(path, cv2.IMREAD_COLOR)
        if bgr is None:
            messagebox.showerror("Ошибка", "Не удалось открыть изображение")
            return
        self.background_path = Path(path)
        self.background_bgr = bgr
        self.background_rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
        self.redraw()

    def on_canvas_click(self, event):
        if self.background_rgb is None:
            return
        img_x, img_y = self.canvas_to_image(event.x, event.y)
        if img_x is None:
            return

        m = Marker(
            marker_id=int(self.id_var.get()),
            dictionary=self.dict_var.get(),
            cx_px=float(img_x),
            cy_px=float(img_y),
            size_px=int(self.size_px_var.get()),
            size_mm=float(self.size_mm_var.get()),
            rotation_deg=float(self.rotation_var.get()),
        )
        self.markers.append(m)
        self.id_var.set(self.id_var.get() + 1)
        self.refresh_tree()
        self.redraw()

    def canvas_to_image(self, cx, cy):
        if self.background_rgb is None:
            return None, None
        h, w = self.background_rgb.shape[:2]
        cw = max(1, self.canvas.winfo_width())
        ch = max(1, self.canvas.winfo_height())

        self.scale = min(cw / w, ch / h)
        sw, sh = int(w * self.scale), int(h * self.scale)
        ox = (cw - sw) // 2
        oy = (ch - sh) // 2

        if cx < ox or cy < oy or cx >= ox + sw or cy >= oy + sh:
            return None, None

        img_x = (cx - ox) / self.scale
        img_y = (cy - oy) / self.scale
        return img_x, img_y

    def image_to_canvas(self, ix, iy):
        h, w = self.background_rgb.shape[:2]
        cw = max(1, self.canvas.winfo_width())
        ch = max(1, self.canvas.winfo_height())

        self.scale = min(cw / w, ch / h)
        sw, sh = int(w * self.scale), int(h * self.scale)
        ox = (cw - sw) // 2
        oy = (ch - sh) // 2

        return ox + ix * self.scale, oy + iy * self.scale

    def render_marker(self, marker: Marker, side_px: int):
        dictionary = cv2.aruco.getPredefinedDictionary(ARUCO_DICTS[marker.dictionary])
        img = cv2.aruco.generateImageMarker(dictionary, marker.marker_id, side_px)
        rgb = cv2.cvtColor(img, cv2.COLOR_GRAY2RGB)

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
            marker_rgb = self.render_marker(m, side)
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

            roi = marker_rgb[my0:my1, mx0:mx1]
            out[cy0:cy1, cx0:cx1] = roi

        return out

    def redraw(self):
        self.canvas.delete("all")
        if self.background_rgb is None:
            return

        preview = self.compose_preview()
        h, w = preview.shape[:2]
        cw = max(1, self.canvas.winfo_width())
        ch = max(1, self.canvas.winfo_height())

        scale = min(cw / w, ch / h)
        sw, sh = int(w * scale), int(h * scale)
        resized = cv2.resize(preview, (sw, sh), interpolation=cv2.INTER_AREA)

        pil = Image.fromarray(resized)
        self.tk_image = ImageTk.PhotoImage(pil)

        ox = (cw - sw) // 2
        oy = (ch - sh) // 2
        self.canvas.create_image(ox, oy, anchor=tk.NW, image=self.tk_image)

        for i, m in enumerate(self.markers):
            x, y = self.image_to_canvas(m.cx_px, m.cy_px)
            r = (m.size_px * scale) / 2
            self.canvas.create_rectangle(x - r, y - r, x + r, y + r, outline="#00d7ff", width=2)
            self.canvas.create_text(x, y - r - 10, text=f"#{i} id={m.marker_id}", fill="#00d7ff", font=("TkDefaultFont", 9, "bold"))

    def refresh_tree(self):
        for item in self.tree.get_children():
            self.tree.delete(item)
        for i, m in enumerate(self.markers):
            self.tree.insert(
                "",
                tk.END,
                values=(
                    i,
                    m.dictionary,
                    m.marker_id,
                    round(m.cx_px, 1),
                    round(m.cy_px, 1),
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
        self.refresh_tree()
        self.redraw()

    def clear_markers(self):
        self.markers.clear()
        self.refresh_tree()
        self.redraw()

    def export_layout(self):
        if self.background_rgb is None:
            messagebox.showwarning("Внимание", "Сначала загрузите фон")
            return

        save_path = filedialog.asksaveasfilename(defaultextension=".yaml", filetypes=[("YAML", "*.yaml *.yml")])
        if not save_path:
            return

        payload = {
            "version": 1,
            "background_image": str(self.background_path) if self.background_path else None,
            "image_size_px": {
                "width": int(self.background_rgb.shape[1]),
                "height": int(self.background_rgb.shape[0]),
            },
            "markers": [asdict(m) for m in self.markers],
        }

        yaml_text = self.to_simple_yaml(payload)
        out_yaml = Path(save_path)
        out_yaml.write_text(yaml_text, encoding="utf-8")

        preview = self.compose_preview()
        if preview is not None:
            png_path = out_yaml.with_suffix(".preview.png")
            cv2.imwrite(str(png_path), cv2.cvtColor(preview, cv2.COLOR_RGB2BGR))

        messagebox.showinfo("Готово", f"Сохранено:\n{out_yaml}\n{out_yaml.with_suffix('.preview.png')}")

    def import_layout(self):
        path = filedialog.askopenfilename(filetypes=[("YAML", "*.yaml *.yml"), ("JSON", "*.json")])
        if not path:
            return

        txt = Path(path).read_text(encoding="utf-8")
        data = self.parse_yaml_or_json(txt)

        bg = data.get("background_image")
        if bg and Path(bg).exists():
            self.background_path = Path(bg)
            bgr = cv2.imread(bg, cv2.IMREAD_COLOR)
            if bgr is not None:
                self.background_bgr = bgr
                self.background_rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)

        self.markers = []
        for raw in data.get("markers", []):
            self.markers.append(
                Marker(
                    marker_id=int(raw["marker_id"]),
                    dictionary=str(raw["dictionary"]),
                    cx_px=float(raw["cx_px"]),
                    cy_px=float(raw["cy_px"]),
                    size_px=int(raw["size_px"]),
                    size_mm=float(raw.get("size_mm", 0.0)),
                    rotation_deg=float(raw.get("rotation_deg", 0.0)),
                )
            )

        self.refresh_tree()
        self.redraw()

    @staticmethod
    def to_simple_yaml(data, indent=0):
        # Compact serializer to avoid external pyyaml dependency.
        sp = "  " * indent
        if isinstance(data, dict):
            lines = []
            for k, v in data.items():
                if isinstance(v, (dict, list)):
                    lines.append(f"{sp}{k}:")
                    lines.append(ArucoLayoutApp.to_simple_yaml(v, indent + 1))
                else:
                    lines.append(f"{sp}{k}: {ArucoLayoutApp.yaml_scalar(v)}")
            return "\n".join(lines)
        if isinstance(data, list):
            lines = []
            for item in data:
                if isinstance(item, (dict, list)):
                    lines.append(f"{sp}-")
                    lines.append(ArucoLayoutApp.to_simple_yaml(item, indent + 1))
                else:
                    lines.append(f"{sp}- {ArucoLayoutApp.yaml_scalar(item)}")
            return "\n".join(lines)
        return f"{sp}{ArucoLayoutApp.yaml_scalar(data)}"

    @staticmethod
    def yaml_scalar(v):
        if v is None:
            return "null"
        if isinstance(v, bool):
            return "true" if v else "false"
        if isinstance(v, (int, float)):
            return str(v)
        s = str(v)
        s = s.replace("\\", "\\\\").replace('"', '\\"')
        return f'"{s}"'

    @staticmethod
    def parse_yaml_or_json(text: str):
        # For supported export format we can parse via json fallback:
        # Try json first, then very small yaml subset parser.
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass

        # Minimal YAML parser for the exact structure we export.
        lines = [ln.rstrip() for ln in text.splitlines() if ln.strip() and not ln.strip().startswith("#")]
        root = {}
        i = 0

        def parse_scalar(s):
            s = s.strip()
            if s == "null":
                return None
            if s in ("true", "false"):
                return s == "true"
            if s.startswith('"') and s.endswith('"'):
                return s[1:-1].replace('\\"', '"').replace("\\\\", "\\")
            try:
                if "." in s:
                    return float(s)
                return int(s)
            except ValueError:
                return s

        markers = []
        current = None
        in_markers = False
        for ln in lines:
            st = ln.strip()
            if st.startswith("markers:"):
                in_markers = True
                continue
            if not in_markers:
                if ":" in st:
                    k, v = st.split(":", 1)
                    k = k.strip()
                    v = v.strip()
                    if v == "":
                        root[k] = {}
                    else:
                        root[k] = parse_scalar(v)
                continue

            if st == "-":
                if current:
                    markers.append(current)
                current = {}
                continue

            if ":" in st and current is not None:
                k, v = st.split(":", 1)
                current[k.strip()] = parse_scalar(v)

        if current:
            markers.append(current)

        root["markers"] = markers
        return root


def main():
    root = tk.Tk()
    app = ArucoLayoutApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
