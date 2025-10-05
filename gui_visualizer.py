# visualizer.py
# Vista animada del enlace A ↔ B con dos carriles (superior A→B, inferior B→A).
# Reacciona a los prints del protocolo:
#   "A → medio:"   -> inicia A→B
#   "medio → B:"   -> finaliza A→B
#   "B → medio:"   -> inicia B→A
#   "medio → A:"   -> finaliza B→A
#
# Además detecta ACK si la línea contiene "[ACK" y pinta DATA/ACK con colores distintos.
# Soporta simultaneidad y colas por carril.

import tkinter as tk
from tkinter import ttk
import re
from collections import deque

class LinkVisualizer(tk.Toplevel):
    # --- Regex para detectar eventos en el log ---
    RE_A_TO_MED = re.compile(r"^\s*A\s*→\s*medio\s*:", re.I)
    RE_MED_TO_B = re.compile(r"^\s*medio\s*→\s*B\s*:", re.I)
    RE_B_TO_MED = re.compile(r"^\s*B\s*→\s*medio\s*:", re.I)
    RE_MED_TO_A = re.compile(r"^\s*medio\s*→\s*A\s*:", re.I)
    RE_IS_ACK   = re.compile(r"\[ACK\b", re.I)

    # Colores
    COLOR_DATA = "#2E6FE7"  # azul
    COLOR_ACK  = "#2BB673"  # verde
    COLOR_LINK = "#999999"
    COLOR_BOX  = "#EAF2FF"
    COLOR_OUT  = "#4A77F0"

    def __init__(self, master=None, title="Enlace — Animación A ↔ B (bidireccional)"):
        super().__init__(master)
        self.title(title)
        self.geometry("900x460")
        self.resizable(True, False)

        # Estado global
        self.paused = False

        # Estado por carril (A2B y B2A)
        self.state = {
            "A2B": {
                "in_flight": False,
                "dot_id": None,
                "color": self.COLOR_DATA,
                "x": None, "x_end": None, "y": None,
                "after_id": None,
                "queue": deque()  # elementos: "DATA" | "ACK"
            },
            "B2A": {
                "in_flight": False,
                "dot_id": None,
                "color": self.COLOR_DATA,
                "x": None, "x_end": None, "y": None,
                "after_id": None,
                "queue": deque()
            },
        }

        # Parámetros animación
        self.step_px = 9
        self.delay_ms = 22
        self.dot_radius = 8

        self._build_ui()
        self._layout_coords()
        self._draw_scene()

        self.protocol("WM_DELETE_WINDOW", self._on_close)

    # ----------------- UI -----------------
    def _build_ui(self):
        wrap = ttk.Frame(self, padding=10)
        wrap.pack(fill="both", expand=True)

        self.canvas = tk.Canvas(wrap, bg="white", height=320)
        self.canvas.pack(fill="x")

        ctrl = ttk.Frame(wrap)
        ctrl.pack(fill="x", pady=(8, 0))

        self.btn_pause = ttk.Button(ctrl, text="Pausar", command=self.toggle_pause)
        self.btn_pause.pack(side="left")

        # Leyenda
        legend = ttk.Frame(ctrl)
        legend.pack(side="left", padx=16)
        ttk.Label(legend, text="Leyenda: ").pack(side="left")
        self._legend_dot(legend, self.COLOR_DATA); ttk.Label(legend, text=" DATA   ").pack(side="left")
        self._legend_dot(legend, self.COLOR_ACK);  ttk.Label(legend, text=" ACK").pack(side="left")

        ttk.Label(ctrl, text="(Solo visual; no altera el protocolo)").pack(side="left", padx=12)

    def _legend_dot(self, parent, color):
        cc = tk.Canvas(parent, width=16, height=16, highlightthickness=0, bg="white")
        cc.create_oval(3, 3, 13, 13, fill=color, outline="")
        cc.pack(side="left")

    def _layout_coords(self):
        # “laptops” y dos carriles
        self.ax1, self.ay1, self.ax2, self.ay2 = 80, 110, 200, 220
        self.bx1, self.by1, self.bx2, self.by2 = 700, 110, 820, 220

        # carriles: superior (A→B) e inferior (B→A)
        self.y_top = (self.ay1 + self.ay2) // 2 - 28
        self.y_bot = (self.ay1 + self.ay2) // 2 + 28

        self.link_left  = self.ax2 + 18
        self.link_right = self.bx1 - 18

    def _draw_scene(self):
        c = self.canvas
        c.delete("all")
        # Laptops
        c.create_rectangle(self.ax1, self.ay1, self.ax2, self.ay2, fill=self.COLOR_BOX, outline=self.COLOR_OUT, width=2)
        c.create_text((self.ax1 + self.ax2)//2, self.ay1-12, text="Laptop A", font=("Segoe UI", 10, "bold"))
        c.create_rectangle(self.bx1, self.by1, self.bx2, self.by2, fill=self.COLOR_BOX, outline=self.COLOR_OUT, width=2)
        c.create_text((self.bx1 + self.bx2)//2, self.by1-12, text="Laptop B", font=("Segoe UI", 10, "bold"))

        # Enlaces: dos carriles (líneas separadas)
        c.create_line(self.link_left, self.y_top, self.link_right, self.y_top, fill=self.COLOR_LINK, width=2)
        c.create_text((self.link_left + self.link_right)//2, self.y_top - 14, text="A → B", fill="#555")
        c.create_line(self.link_left, self.y_bot, self.link_right, self.y_bot, fill=self.COLOR_LINK, width=2)
        c.create_text((self.link_left + self.link_right)//2, self.y_bot + 14, text="B → A", fill="#555")

    # ------------- API pública -------------
    def set_paused(self, value: bool):
        value = bool(value)
        if value == self.paused:
            return
        self.paused = value
        self.btn_pause.config(text="Reanudar" if self.paused else "Pausar")
        if self.paused:
            # cancelar afters activos
            for lane in ("A2B", "B2A"):
                st = self.state[lane]
                if st["after_id"]:
                    try: self.after_cancel(st["after_id"])
                    except Exception: pass
                    st["after_id"] = None
        else:
            # retomar si hay algo en vuelo
            for lane in ("A2B", "B2A"):
                st = self.state[lane]
                if st["in_flight"] and st["dot_id"] is not None:
                    self._schedule_next(lane)

    def toggle_pause(self):
        self.set_paused(not self.paused)

    def reset(self):
        """Limpia el canvas y estados."""
        for lane in ("A2B", "B2A"):
            st = self.state[lane]
            st["in_flight"] = False
            st["dot_id"] = None
            st["x"] = st["x_end"] = st["y"] = None
            if st["after_id"]:
                try: self.after_cancel(st["after_id"])
                except Exception: pass
                st["after_id"] = None
            st["queue"].clear()
        self._draw_scene()

    def consume_log(self, line: str):
        """Recibe cada línea impresa por los protocolos y la interpreta para animar."""
        s = (line or "").strip()
        if not s:
            return

        is_ack = bool(self.RE_IS_ACK.search(s))  # DATA vs ACK por heurística

        # A → medio (inicio A→B)
        if self.RE_A_TO_MED.match(s):
            self._enqueue_or_start("A2B", is_ack); return

        # medio → B (fin A→B)
        if self.RE_MED_TO_B.match(s):
            self._finish_if_lane("A2B"); return

        # B → medio (inicio B→A)
        if self.RE_B_TO_MED.match(s):
            self._enqueue_or_start("B2A", is_ack); return

        # medio → A (fin B→A)
        if self.RE_MED_TO_A.match(s):
            self._finish_if_lane("B2A"); return

    # ------------- Lógica de carriles / animación -------------
    def _enqueue_or_start(self, lane: str, is_ack: bool):
        st = self.state[lane]
        kind = "ACK" if is_ack else "DATA"
        if st["in_flight"]:
            st["queue"].append(kind)
            return
        self._start_lane(lane, kind)

    def _start_lane(self, lane: str, kind: str):
        st = self.state[lane]
        st["color"] = self.COLOR_ACK if kind == "ACK" else self.COLOR_DATA

        # borrar punto previo si existía
        if st["dot_id"] is not None:
            try: self.canvas.delete(st["dot_id"])
            except Exception: pass
            st["dot_id"] = None

        # origen/destino por carril
        if lane == "A2B":
            x0, x1, y = self.link_left, self.link_right, self.y_top
        else:  # B2A
            x0, x1, y = self.link_right, self.link_left, self.y_bot

        st["x"], st["x_end"], st["y"] = x0, x1, y
        r = self.dot_radius
        st["dot_id"] = self.canvas.create_oval(x0-r, y-r, x0+r, y+r, outline="", fill=st["color"])
        st["in_flight"] = True

        if not self.paused:
            self._schedule_next(lane)

    def _finish_if_lane(self, lane: str):
        st = self.state[lane]
        if not st["in_flight"] or st["dot_id"] is None:
            return

        # Ajustar al final exacto
        r = self.dot_radius
        self.canvas.coords(st["dot_id"], st["x_end"]-r, st["y"]-r, st["x_end"]+r, st["y"]+r)

        # limpiar animación actual
        st["in_flight"] = False
        if st["after_id"]:
            try: self.after_cancel(st["after_id"])
            except Exception: pass
            st["after_id"] = None

        # ¿Hay cola pendiente? iniciar siguiente
        if st["queue"]:
            nxt_kind = st["queue"].popleft()
            self._start_lane(lane, nxt_kind)

    def _schedule_next(self, lane: str):
        st = self.state[lane]
        if st["after_id"]:
            try: self.after_cancel(st["after_id"])
            except Exception: pass
        st["after_id"] = self.after(self.delay_ms, lambda: self._tick(lane))

    def _tick(self, lane: str):
        st = self.state[lane]
        if self.paused or not st["in_flight"] or st["dot_id"] is None:
            st["after_id"] = None
            return

        # Dirección (según x_end)
        step = self.step_px if st["x_end"] >= st["x"] else -self.step_px
        nx = st["x"] + step
        reached = (nx >= st["x_end"]) if st["x_end"] >= st["x"] else (nx <= st["x_end"])
        if reached:
            nx = st["x_end"]

        dx = nx - st["x"]
        self.canvas.move(st["dot_id"], dx, 0)
        st["x"] = nx

        if reached:
            st["in_flight"] = False
            st["after_id"] = None
            # Si no llega el "medio → X" por logs, aún así encadenamos siguiente
            if st["queue"]:
                nxt_kind = st["queue"].popleft()
                self._start_lane(lane, nxt_kind)
            return

        self._schedule_next(lane)

    def _on_close(self):
        for lane in ("A2B", "B2A"):
            st = self.state[lane]
            if st["after_id"]:
                try: self.after_cancel(st["after_id"])
                except Exception: pass
            st["after_id"] = None
        self.destroy()
