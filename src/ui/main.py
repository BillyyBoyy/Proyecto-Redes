# ui/main.py
# -*- coding: utf-8 -*-
from __future__ import annotations
# Bring your packages onto the path
import sys
import os

# Agrega el directorio superior al path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# Now do your import

import tkinter as tk
from tkinter import ttk
from queue import Queue, Empty
import threading
from simulator import Simulator

class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Simulador de Protocolos - Capa de Enlace")
        self.geometry("980x640")

        self.sim = None
        self.log_queue = Queue()

        # --- Controles ---
        frm = ttk.Frame(self, padding=10)
        frm.pack(fill=tk.X, side=tk.TOP)

        ttk.Label(frm, text="Protocolo:").grid(row=0, column=0, sticky="w")
        self.cbo_proto = ttk.Combobox(frm, values=["utopia", "stop-and-wait", "par", "sliding-1bit", "go-back-n", "selective-repeat"], width=16)
        self.cbo_proto.current(0)
        self.cbo_proto.grid(row=0, column=1, padx=6, sticky="w")

        ttk.Label(frm, text="MAX_SEQ:").grid(row=0, column=2, sticky="w")
        self.cbo_maxseq = ttk.Combobox(frm, values=[1, 3, 7, 15], width=5)
        self.cbo_maxseq.current(2)  # 7
        self.cbo_maxseq.grid(row=0, column=3, padx=6, sticky="w")

        ttk.Label(frm, text="Error (%):").grid(row=0, column=4, sticky="w")
        self.sld_err = ttk.Scale(frm, from_=0, to=30, orient=tk.HORIZONTAL, length=120)
        self.sld_err.set(0)
        self.sld_err.grid(row=0, column=5, padx=6)

        ttk.Label(frm, text="Pérdida (%):").grid(row=0, column=6, sticky="w")
        self.sld_loss = ttk.Scale(frm, from_=0, to=30, orient=tk.HORIZONTAL, length=120)
        self.sld_loss.set(0)
        self.sld_loss.grid(row=0, column=7, padx=6)

        ttk.Label(frm, text="Carga A:").grid(row=1, column=0, sticky="w", pady=(8,0))
        self.ent_payload_a = ttk.Entry(frm, width=40)
        self.ent_payload_a.insert(0, "HELLO FROM A " * 5)
        self.ent_payload_a.grid(row=1, column=1, columnspan=3, sticky="we", pady=(8,0))

        ttk.Label(frm, text="Carga B:").grid(row=1, column=4, sticky="w", pady=(8,0))
        self.ent_payload_b = ttk.Entry(frm, width=40)
        self.ent_payload_b.insert(0, "HELLO FROM B " * 5)
        self.ent_payload_b.grid(row=1, column=5, columnspan=3, sticky="we", pady=(8,0))

        # Botones
        btns = ttk.Frame(self, padding=(10, 0))
        btns.pack(fill=tk.X, side=tk.TOP)
        self.btn_start = ttk.Button(btns, text="Iniciar", command=self.on_start)
        self.btn_pause = ttk.Button(btns, text="Pausar", command=self.on_pause, state=tk.DISABLED)
        self.btn_resume = ttk.Button(btns, text="Continuar", command=self.on_resume, state=tk.DISABLED)
        self.btn_stop = ttk.Button(btns, text="Detener", command=self.on_stop, state=tk.DISABLED)
        self.btn_clear = ttk.Button(btns, text="Limpiar log", command=self.on_clear)
        for i, b in enumerate([self.btn_start, self.btn_pause, self.btn_resume, self.btn_stop, self.btn_clear]):
            b.grid(row=0, column=i, padx=6, pady=8, sticky="w")

        # Consola de eventos
        self.txt = tk.Text(self, height=28, wrap="none")
        self.txt.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        self.txt.insert("end", "Listo.\n")

        self.after(50, self._drain_logs)

    # ---- callbacks de simulador ----
    def _on_frame(self, ev: str, direction: str, frame, detail: str):
        self.log_queue.put(f"[{ev.upper():9}] {direction:5s}  kind={frame.kind.name}  seq={frame.seq}  ack={frame.ack}  {detail}")

    def _on_log(self, msg: str):
        self.log_queue.put(msg)

    # ---- UI actions ----
    def on_start(self):
        if self.sim is not None:
            return
        proto = self.cbo_proto.get().strip().lower()
        max_seq = int(self.cbo_maxseq.get())
        err = float(self.sld_err.get()) / 100.0
        loss = float(self.sld_loss.get()) / 100.0
        payload_a = self.ent_payload_a.get()
        payload_b = self.ent_payload_b.get()

        self.sim = Simulator(on_frame=self._on_frame, on_log=self._on_log)
        self.sim.start(protocol=proto,
                       max_seq=max_seq,
                       error_prob=err, loss_prob=loss,
                       payload_a=payload_a, payload_b=payload_b)

        self.btn_start.config(state=tk.DISABLED)
        self.btn_pause.config(state=tk.NORMAL)
        self.btn_stop.config(state=tk.NORMAL)

    def on_pause(self):
        if self.sim:
            self.sim.pause(True)
            self.btn_pause.config(state=tk.DISABLED)
            self.btn_resume.config(state=tk.NORMAL)

    def on_resume(self):
        if self.sim:
            self.sim.pause(False)
            self.btn_pause.config(state=tk.NORMAL)
            self.btn_resume.config(state=tk.DISABLED)

    def on_stop(self):
        if self.sim:
            self.sim.stop()
            self.sim = None
        self.btn_start.config(state=tk.NORMAL)
        self.btn_pause.config(state=tk.DISABLED)
        self.btn_resume.config(state=tk.DISABLED)
        self.btn_stop.config(state=tk.DISABLED)

    def on_clear(self):
        self.txt.delete("1.0", "end")

    def _drain_logs(self):
        try:
            while True:
                line = self.log_queue.get_nowait()
                self.txt.insert("end", line + "\n")
                self.txt.see("end")
        except Empty:
            pass
        self.after(50, self._drain_logs)

if __name__ == "__main__":
    App().mainloop()
