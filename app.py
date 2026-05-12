#!/usr/bin/env python3
import base64
import json
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
from typing import List, Optional

import cv2
import tkinter as tk
from PIL import Image, ImageTk
from tkinter import filedialog, messagebox, ttk


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

        self.markers: List[Marker] = []
        self._build_ui()

    def _build_ui(self):
        main = ttk.Frame(self.root)
        main.pack(fill=tk.BOTH, expand=True)

        left = ttk.Frame(main, width=380)
        left.pack(side=tk.LEFT, fill=tk.Y, padx=8, pady=8)

        right = ttk.Frame(main)
        right.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True, padx=8, pady=8)

        ttk.Label(left, text="Фон (чертеж/изображение)", font=("TkDefaultFont", 10, "bold")).pack(anchor="w")
        ttk.Button(left, text="Загрузить фон", command=self.load_background).pack(fill=tk.X, pady=4)

        ttk.Separator(left).pack(fill=tk.X, pady=8)

        ttk.Label(left, text="Параметры схемы (JSON)", font=("TkDefaultFont", 10, "bold")).pack(anchor="w")
        self.size_x_var = tk.DoubleVar(value=0.9)
        self.size_y_var = tk.DoubleVar(value=0.9)
        self.ppm_var = tk.DoubleVar(value=2500.0)
        self.inverted_var = tk.BooleanVar(value=True)

        ttk.Label(left, text="sizeX (m)").pack(anchor="w")
        ttk.Entry(left, textvariable=self.size_x_var).pack(fill=tk.X, pady=2)

        ttk.Label(left, text="sizeY (m)").pack(anchor="w")
        ttk.Entry(left, textvariable=self.size_y_var).pack(fill=tk.X, pady=2)

        ttk.Label(left, text="pixelCountPerMeter").pack(anchor="w")
        ttk.Entry(left, textvariable=self.ppm_var).pack(fill=tk.X, pady=2)

        ttk.Checkbutton(left, text="colorInverted", variable=self.inverted_var).pack(anchor="w", pady=4)

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
        ttk.Spinbox(left, from_=20, to=2000, textvariable=self.size_px_var).pack(fill=tk.X, pady=2)

        self.size_mm_var = tk.DoubleVar(value=220.0)
        ttk.Label(left, text="Реальный размер (mm)").pack(anchor="w")
        ttk.Entry(left, textvariable=self.size_mm_var).pack(fill=tk.X, pady=2)

        self.rotation_var = tk.DoubleVar(value=0.0)
        ttk.Label(left, text="Yaw / поворот (deg)").pack(anchor="w")
        ttk.Entry(left, textvariable=self.rotation_var).pack(fill=tk.X, pady=2)

        ttk.Label(left, text="Клик по изображению: добавить маркер", foreground="#555").pack(anchor="w", pady=6)

        ttk.Button(left, text="Удалить выбранный", command=self.delete_selected).pack(fill=tk.X, pady=3)
        ttk.Button(left, text="Очистить все", command=self.clear_markers).pack(fill=tk.X, pady=2)

        ttk.Separator(left).pack(fill=tk.X, pady=8)

        ttk.Button(left, text="Сохранить проект в папку", command=self.export_project_folder).pack(fill=tk.X, pady=3)
        ttk.Button(left, text="Импорт JSON схемы", command=self.import_layout).pack(fill=tk.X, pady=3)

        ttk.Label(left, text="Список маркеров", font=("TkDefaultFont", 10, "bold")).pack(anchor="w", pady=(10, 0))
        cols = ("idx", "dict", "id", "x_m", "y_m", "px", "mm", "yaw")
        self.tree = ttk.Treeview(left, columns=cols, show="headings", height=18)
        for c in cols:
            self.tree.heading(c, text=c)
            self.tree.column(c, width=52 if c in ("idx", "id") else 66, anchor=tk.CENTER)
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

        scale = min(cw / w, ch / h)
        sw, sh = int(w * scale), int(h * scale)
        resized = cv2.resize(preview, (sw, sh), interpolation=cv2.INTER_AREA)

        self.tk_image = ImageTk.PhotoImage(Image.fromarray(resized))
        ox = (cw - sw) // 2
        oy = (ch - sh) // 2
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
        self.refresh_tree()
        self.redraw()

    def clear_markers(self):
        self.markers.clear()
        self.refresh_tree()
        self.redraw()

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

        folder = filedialog.askdirectory(title="Выберите папку проекта")
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
        path = filedialog.askopenfilename(filetypes=[("JSON", "*.json")])
        if not path:
            return

        data = json.loads(Path(path).read_text(encoding="utf-8"))
        self.size_x_var.set(float(data.get("sizeX", self.size_x_var.get())))
        self.size_y_var.set(float(data.get("sizeY", self.size_y_var.get())))
        self.ppm_var.set(float(data.get("pixelCountPerMeter", self.ppm_var.get())))
        self.inverted_var.set(bool(data.get("colorInverted", self.inverted_var.get())))

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

        self.refresh_tree()
        self.redraw()


def main():
    root = tk.Tk()
    ArucoLayoutApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
