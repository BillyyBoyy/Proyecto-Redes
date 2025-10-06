''' 
Interfaz gráfica para lanzar y observar los protocolos de la simulación.
 Pausa/Reanuda/Detén sin tocar los protocolos
'''
  
import sys
import threading
import time
import traceback
import queue
import re
from typing import List, Optional

import tkinter as tk
from tkinter import ttk, messagebox
from tkinter.scrolledtext import ScrolledText

# Estado de ejecución (id del hilo runner)
_RUNNER_TID: Optional[int] = None  # Se asigna al lanzar la simulación
_STOP_REQUESTED = False            # Bandera global para stop
_STOPPING = False                  # Bandera para indicar que estamos en proceso de stop

# Import de configuración y utilidades del proyecto 
try:
    from events import set_setting, get_setting  
except Exception:
    _SETTINGS = {"error_rate": 0.0, "timeout_prob": 0.0, "step_delay": 0.25,
                 "paused": False, "stop_requested": False}
    def get_setting(key: str):
        return _SETTINGS.get(key, (False if key in ("paused", "stop_requested") else 0.0))
    def set_setting(key: str, value):
        _SETTINGS[key] = value

# Parchear sleep_step antes de importar los protocolos
try:
    import events as _aux  # type: ignore

    if hasattr(_aux, "sleep_step"):
        def _patched_sleep_step(dt: Optional[float] = None):
            # Stop inmediato
            if _STOP_REQUESTED or bool(get_setting("stop_requested")):
                raise KeyboardInterrupt("Stop solicitado por el usuario.")
            # dt por defecto: step_delay global
            if dt is None:
                try:
                    dt = float(get_setting("step_delay") or 0.0)
                except Exception:
                    dt = 0.0
            # Esperar mientras esté pausado
            while bool(get_setting("paused")) and not (_STOP_REQUESTED or bool(get_setting("stop_requested"))):
                time.sleep(0.05)
            # Espera fraccionada (para re-chequear flags)
            end = time.time() + max(0.0, float(dt))
            while time.time() < end:
                if _STOP_REQUESTED or bool(get_setting("stop_requested")):
                    raise KeyboardInterrupt("Stop solicitado por el usuario.")
                while bool(get_setting("paused")) and not (_STOP_REQUESTED or bool(get_setting("stop_requested"))):
                    time.sleep(0.05)
                time.sleep(0.02)
        _aux.sleep_step = _patched_sleep_step  # type: ignore
except Exception:
    _aux = None  # fallback

from Protocols.protocol_utopia import test as test_utopia
from Protocols.protocol_stop_and_wait import test as test_snw
from Protocols.protocol_par import test as test_par
from Protocols.protocol_sliding_window import test as test_sw
from Protocols.protocol_go_back_n import test as test_gbn
from Protocols.protocol_selective_repeat import test as test_sr

# Utilidades GUI
def parse_csv(s: str) -> List[str]:
    return [x.strip() for x in s.split(",") if x.strip()]

class TextRedirector:
    """
    Redirige stdout/stderr a un ScrolledText de Tk y opcionalmente notifica
    cada línea a un 'listener' (para la vista animada).
    También coopera con Pausa/Stop cuando escribe el hilo runner.
    """
    def __init__(self, widget: ScrolledText, listener=None):
        self.widget = widget
        self.listener = listener
        self.queue = queue.Queue()
        self._stop = False
        self.widget.after(50, self._drain)

    def write(self, msg: str):
        # Si se está en proceso de stop, no hacer chequeos de pausa/stop
        if _STOPPING:
            self.queue.put(msg)
            if self.listener:
                try: self.listener(msg)
                except Exception: pass
            return

        # Cooperar si escribe el hilo runner (no la GUI)
        try:
            if _RUNNER_TID is not None and threading.get_ident() == _RUNNER_TID:
                if _aux is not None and hasattr(_aux, "sleep_step") and not _STOP_REQUESTED:
                    _aux.sleep_step(0.0)  # respeta pausa y puede lanzar KeyboardInterrupt
                else:
                    if _STOP_REQUESTED or bool(get_setting("stop_requested")):
                        raise KeyboardInterrupt("Stop solicitado por el usuario.")
                    while bool(get_setting("paused")) and not (_STOP_REQUESTED or bool(get_setting("stop_requested"))):
                        time.sleep(0.05)
        except KeyboardInterrupt:
            raise

        # Encolar el texto (no bloquear el hilo)
        self.queue.put(msg)
        # Notificar al listener para animación
        if self.listener:
            try: self.listener(msg)
            except Exception: pass

    def flush(self):
        pass

    def _drain(self):
        try:
            while True:
                msg = self.queue.get_nowait()
                self.widget.insert(tk.END, msg)
                self.widget.see(tk.END)
        except queue.Empty:
            pass
        if not self._stop:
            self.widget.after(50, self._drain)

    def stop(self):
        self._stop = True

# Visualizador 
class InlineVisualizer(ttk.Frame):
    """
    Visualizador simple A ↔ B .
    Reacciona a textos impresos por los protocolos:
      "A → medio:"  -> inicia A→B
      "medio → B:"  -> finaliza A→B
      "B → medio:"  -> inicia B→A
      "medio → A:"  -> finaliza B→A
    """
    RE_A_TO_MED = re.compile(r"^\s*A\s*→\s*medio\s*:", re.I)
    RE_MED_TO_B = re.compile(r"^\s*medio\s*→\s*B\s*:", re.I)
    RE_B_TO_MED = re.compile(r"^\s*B\s*→\s*medio\s*:", re.I)
    RE_MED_TO_A = re.compile(r"^\s*medio\s*→\s*A\s*:", re.I)

    def __init__(self, master):
        super().__init__(master)
        self.paused = False
        self.in_flight = False
        self.direction = None  # "A2B" | "B2A"
        self.dot_id = None
        self.after_id = None
        self.x = None; self.x_end = None; self.y = None
        self.step_px = 8
        self.delay_ms = 24
        self.dot_radius = 7

        # UI
        self.columnconfigure(0, weight=1)
        ttk.Label(self, text="Vista animada A ↔ B", font=("TkDefaultFont", 10, "bold")).grid(
            row=0, column=0, sticky="w", pady=(4, 2)
        )
        self.canvas = tk.Canvas(self, bg="white", height=160)
        self.canvas.grid(row=1, column=0, sticky="ew")
        self._layout_coords()
        self._draw_scene()

    def _layout_coords(self):
        self.ax1, self.ay1, self.ax2, self.ay2 = 40, 50, 120, 120
        self.bx1, self.by1, self.bx2, self.by2 = 480, 50, 560, 120
        self.y_link = (self.ay1 + self.ay2) // 2
        self.link_left = self.ax2 + 14
        self.link_right = self.bx1 - 14

    def _draw_scene(self):
        c = self.canvas
        c.delete("all")
        c.create_rectangle(self.ax1, self.ay1, self.ax2, self.ay2, fill="#EAF2FF", outline="#4A77F0", width=2)
        c.create_text((self.ax1 + self.ax2)//2, self.ay1-10, text="A")
        c.create_rectangle(self.bx1, self.by1, self.bx2, self.by2, fill="#EAF2FF", outline="#4A77F0", width=2)
        c.create_text((self.bx1 + self.bx2)//2, self.by1-10, text="B")
        c.create_line(self.link_left, self.y_link, self.link_right, self.y_link, fill="#999", width=2)

    def set_paused(self, value: bool):
        if bool(value) != self.paused:
            self.paused = bool(value)
            if self.paused and self.after_id:
                try: self.after_cancel(self.after_id)
                except Exception: pass
                self.after_id = None
            elif (not self.paused) and self.in_flight and self.dot_id is not None:
                self._schedule_next()

    def consume_log(self, line: str):
        s = (line or "").strip()
        if not s:
            return
        if self.RE_A_TO_MED.match(s):
            self._start_anim_A2B(); return
        if self.RE_MED_TO_B.match(s):
            self._finish_if_dir("A2B"); return
        if self.RE_B_TO_MED.match(s):
            self._start_anim_B2A(); return
        if self.RE_MED_TO_A.match(s):
            self._finish_if_dir("B2A"); return

    # Animación
    def _start_anim_A2B(self):
        if self.in_flight: return
        self.direction = "A2B"
        self._spawn_dot(self.link_left, self.link_right)

    def _start_anim_B2A(self):
        if self.in_flight: return
        self.direction = "B2A"
        self._spawn_dot(self.link_right, self.link_left)

    def _spawn_dot(self, x0, x1):
        if self.dot_id is not None:
            self.canvas.delete(self.dot_id)
            self.dot_id = None
        self.x = x0; self.x_end = x1; self.y = self.y_link
        r = self.dot_radius
        self.dot_id = self.canvas.create_oval(self.x-r, self.y-r, self.x+r, self.y+r, outline="", fill="#4A77F0")
        self.in_flight = True
        if not self.paused:
            self._schedule_next()

    def _finish_if_dir(self, direction):
        if self.in_flight and self.direction == direction and self.dot_id is not None:
            self.canvas.coords(
                self.dot_id,
                self.x_end - self.dot_radius, self.y - self.dot_radius,
                self.x_end + self.dot_radius, self.y + self.dot_radius
            )
            self.in_flight = False
            self.direction = None
            if self.after_id:
                try: self.after_cancel(self.after_id)
                except Exception: pass
            self.after_id = None

    def _schedule_next(self):
        if self.after_id:
            try: self.after_cancel(self.after_id)
            except Exception: pass
        self.after_id = self.after(self.delay_ms, self._tick)

    def _tick(self):
        if self.paused or not self.in_flight or self.dot_id is None:
            self.after_id = None
            return
        step = self.step_px if self.x_end >= self.x else -self.step_px
        nx = self.x + step
        reached = (nx >= self.x_end) if self.x_end >= self.x else (nx <= self.x_end)
        if reached:
            nx = self.x_end
        dx = nx - self.x
        self.canvas.move(self.dot_id, dx, 0)
        self.x = nx
        if reached:
            self.in_flight = False
            self.direction = None
            self.after_id = None
            return
        self._schedule_next()

# Ventana principal 
class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("SIMULADOR DE PROTOCOLOS — GUI")
        self.geometry("1100x720")
        self.minsize(980, 640)

        # Estado ejecución
        self.run_thread: Optional[threading.Thread] = None
        self.running = False
        self.paused = False  # Estado local de pausa

        # Layout principal
        self.columnconfigure(0, weight=0)  # panel izquierdo
        self.columnconfigure(1, weight=1)  # panel derecho (consola + animación)
        self.rowconfigure(0, weight=1)

        self._build_left_panel()
        self._build_console_and_visualizer()

        # Redirección de stdout/err (con listener para la animación)
        self.stdout_redirect = TextRedirector(self.console, listener=self._on_log_line)
        self.stderr_redirect = TextRedirector(self.console, listener=self._on_log_line)

        self._orig_stdout = sys.stdout
        self._orig_stderr = sys.stderr
        sys.stdout = self.stdout_redirect  
        sys.stderr = self.stderr_redirect  

        # Inicializar configs visuales con valores actuales
        self._load_current_settings()

    # UI: Panel izquierdo (controles) 
    def _build_left_panel(self):
        left = ttk.Frame(self, padding=10)
        left.grid(row=0, column=0, sticky="nsw")

        ttk.Label(left, text="SIMULADOR DE PROTOCOLOS", font=("TkDefaultFont", 12, "bold")).grid(
            row=0, column=0, columnspan=2, sticky="w", pady=(0, 8)
        )

        cfg = ttk.Labelframe(left, text="Configuración del canal", padding=10)
        cfg.grid(row=1, column=0, columnspan=2, sticky="ew", pady=5)
        cfg.columnconfigure(1, weight=1)

        self.var_error = tk.DoubleVar(value=0.0)
        self.var_timeout = tk.DoubleVar(value=0.0)
        self.var_step = tk.DoubleVar(value=0.25)

        ttk.Label(cfg, text="Prob. error/pérdida (0–1)").grid(row=0, column=0, sticky="w")
        self.sld_error = ttk.Scale(cfg, from_=0.0, to=1.0, variable=self.var_error)
        self.sld_error.grid(row=0, column=1, sticky="ew", padx=6)
        self.lbl_error = ttk.Label(cfg, text="0.00"); self.lbl_error.grid(row=0, column=2, sticky="e")
        self.var_error.trace_add("write", lambda *_: self.lbl_error.config(text=f"{self.var_error.get():.2f}"))

        ttk.Label(cfg, text="Prob. timeout (0–1)").grid(row=1, column=0, sticky="w")
        self.sld_timeout = ttk.Scale(cfg, from_=0.0, to=1.0, variable=self.var_timeout)
        self.sld_timeout.grid(row=1, column=1, sticky="ew", padx=6)
        self.lbl_timeout = ttk.Label(cfg, text="0.00"); self.lbl_timeout.grid(row=1, column=2, sticky="e")
        self.var_timeout.trace_add("write", lambda *_: self.lbl_timeout.config(text=f"{self.var_timeout.get():.2f}"))

        ttk.Label(cfg, text="Velocidad (seg/step)").grid(row=2, column=0, sticky="w")
        self.sld_step = ttk.Scale(cfg, from_=0.0, to=2.0, variable=self.var_step)
        self.sld_step.grid(row=2, column=1, sticky="ew", padx=6)
        self.lbl_step = ttk.Label(cfg, text="0.25 s"); self.lbl_step.grid(row=2, column=2, sticky="e")
        self.var_step.trace_add("write", lambda *_: self.lbl_step.config(text=f"{self.var_step.get():.2f} s"))

        ttk.Button(cfg, text="Aplicar", command=self.apply_settings).grid(row=3, column=0, columnspan=3, sticky="ew", pady=(8,0))

        proto = ttk.Labelframe(left, text="Protocolo", padding=10)
        proto.grid(row=2, column=0, columnspan=2, sticky="ew", pady=5)
        proto.columnconfigure(1, weight=1)

        self.var_proto = tk.StringVar(value="Utopía (ideal)")
        ttk.Label(proto, text="Elegir:").grid(row=0, column=0, sticky="w")
        self.cmb_proto = ttk.Combobox(
            proto, textvariable=self.var_proto,
            values=["Utopía (ideal)","Stop-and-Wait (simple)","PAR (con retransmisión)",
                    "Sliding Window 1-bit (bidireccional)","Go-Back-N","Selective-Repeat"],
            state="readonly",
        )
        self.cmb_proto.grid(row=0, column=1, sticky="ew", padx=6)
        self.cmb_proto.bind("<<ComboboxSelected>>", lambda e: self._refresh_inputs())

        self.inputs_frame = ttk.Labelframe(left, text="Parámetros", padding=10)
        self.inputs_frame.grid(row=3, column=0, columnspan=2, sticky="ew", pady=5)
        self.inputs_frame.columnconfigure(1, weight=1)

        self.var_data = tk.StringVar(value="a,b,c")
        self.var_data2 = tk.StringVar(value="R1,R2")
        self.var_win = tk.IntVar(value=3)

        self._refresh_inputs()

        run = ttk.Labelframe(left, text="Ejecución", padding=10)
        run.grid(row=4, column=0, columnspan=2, sticky="ew", pady=5)
        run.columnconfigure(0, weight=1); run.columnconfigure(1, weight=1); run.columnconfigure(2, weight=1)

        self.btn_run   = ttk.Button(run, text="▶ Ejecutar", command=self.start_run); self.btn_run.grid(row=0, column=0, sticky="ew", padx=(0,4))
        self.btn_pause = ttk.Button(run, text="⏸ Pausar", command=self.toggle_pause, state="disabled"); self.btn_pause.grid(row=0, column=1, sticky="ew", padx=4)
        self.btn_stop  = ttk.Button(run, text="⏹ Detener", command=self.stop_run, state="disabled"); self.btn_stop.grid(row=0, column=2, sticky="ew", padx=(4,0))

        extras = ttk.Frame(left, padding=(0,4,0,0)); extras.grid(row=5, column=0, columnspan=2, sticky="ew")
        ttk.Button(extras, text="Limpiar consola", command=self.clear_console).grid(row=0, column=0, sticky="ew")

    # UI: Consola y Visualizador 
    def _build_console_and_visualizer(self):
        right = ttk.Frame(self, padding=10); right.grid(row=0, column=1, sticky="nsew")
        right.rowconfigure(1, weight=1); right.columnconfigure(0, weight=1)

        ttk.Label(right, text="Consola de salida", font=("TkDefaultFont", 10, "bold")).grid(row=0, column=0, sticky="w", pady=(0,6))
        self.console = ScrolledText(right, wrap="word", height=12)
        self.console.grid(row=1, column=0, sticky="nsew")

        ttk.Separator(right).grid(row=2, column=0, sticky="ew", pady=8)

        # Inline visualizer debajo de la consola
        self.inline_vis = InlineVisualizer(right)
        self.inline_vis.grid(row=3, column=0, sticky="ew")

    # Lógica de entradas dinámicas 
    def _refresh_inputs(self):
        for child in self.inputs_frame.winfo_children():
            child.destroy()

        proto = self.var_proto.get()
        if proto in ("Utopía (ideal)", "Stop-and-Wait (simple)", "PAR (con retransmisión)"):
            ttk.Label(self.inputs_frame, text="Datos (coma):").grid(row=0, column=0, sticky="w")
            default = "a,b,c" if proto != "PAR (con retransmisión)" else "H,O,L,A"
            self.var_data.set(default)
            ttk.Entry(self.inputs_frame, textvariable=self.var_data).grid(row=0, column=1, sticky="ew", padx=6)

        elif proto == "Sliding Window 1-bit (bidireccional)":
            ttk.Label(self.inputs_frame, text="Mensajes A (coma):").grid(row=0, column=0, sticky="w")
            self.var_data.set("H1,H2,H3")
            ttk.Entry(self.inputs_frame, textvariable=self.var_data).grid(row=0, column=1, sticky="ew", padx=6)

            ttk.Label(self.inputs_frame, text="Mensajes B (coma):").grid(row=1, column=0, sticky="w")
            self.var_data2.set("R1,R2")
            ttk.Entry(self.inputs_frame, textvariable=self.var_data2).grid(row=1, column=1, sticky="ew", padx=6)

        elif proto == "Go-Back-N":
            ttk.Label(self.inputs_frame, text="Tamaño de ventana (w):").grid(row=0, column=0, sticky="w")
            self.var_win.set(3)
            ttk.Spinbox(self.inputs_frame, from_=1, to=32, textvariable=self.var_win, width=6)\
                .grid(row=0, column=1, sticky="w", padx=6)

            ttk.Label(self.inputs_frame, text="Mensajes A (coma):").grid(row=1, column=0, sticky="w")
            self.var_data.set("a,b,c,d,e,f")
            ttk.Entry(self.inputs_frame, textvariable=self.var_data).grid(row=1, column=1, sticky="ew", padx=6)

            ttk.Label(self.inputs_frame, text="Mensajes B (coma):").grid(row=2, column=0, sticky="w")
            self.var_data2.set("r1,r2,r3")
            ttk.Entry(self.inputs_frame, textvariable=self.var_data2).grid(row=2, column=1, sticky="ew", padx=6)

        elif proto == "Selective-Repeat":
            ttk.Label(self.inputs_frame, text="Tamaño de ventana (w):").grid(row=0, column=0, sticky="w")
            self.var_win.set(3)
            ttk.Spinbox(self.inputs_frame, from_=1, to=32, textvariable=self.var_win, width=6)\
                .grid(row=0, column=1, sticky="w", padx=6)

            ttk.Label(self.inputs_frame, text="Mensajes A (coma):").grid(row=1, column=0, sticky="w")
            self.var_data.set("a,b,c,d,e,f")
            ttk.Entry(self.inputs_frame, textvariable=self.var_data).grid(row=1, column=1, sticky="ew", padx=6)

            ttk.Label(self.inputs_frame, text="Mensajes B (coma):").grid(row=2, column=0, sticky="w")
            self.var_data2.set("r1,r2,r3")
            ttk.Entry(self.inputs_frame, textvariable=self.var_data2).grid(row=2, column=1, sticky="ew", padx=6)

    def _load_current_settings(self):
        try:
            self.var_error.set(float(get_setting("error_rate") or 0.0))
            self.var_timeout.set(float(get_setting("timeout_prob") or 0.0))
            self.var_step.set(float(get_setting("step_delay") or 0.25))
        except Exception:
            pass
        self.lbl_error.config(text=f"{self.var_error.get():.2f}")
        self.lbl_timeout.config(text=f"{self.var_timeout.get():.2f}")
        self.lbl_step.config(text=f"{self.var_step.get():.2f} s")

    def apply_settings(self):
        try:
            set_setting("error_rate", max(0.0, min(1.0, float(self.var_error.get()))))
            set_setting("timeout_prob", max(0.0, min(1.0, float(self.var_timeout.get()))))
            set_setting("step_delay", max(0.0, float(self.var_step.get())))
            print(f"[Config] error_rate={get_setting('error_rate'):.2f}  "
                  f"timeout_prob={get_setting('timeout_prob'):.2f}  "
                  f"step_delay={float(get_setting('step_delay')):.2f}s")
        except Exception as e:
            messagebox.showerror("Error", f"No se pudo aplicar configuración:\n{e}")

    # Animación: hook de logs 
    def _on_log_line(self, line: str):
        if hasattr(self, "inline_vis") and self.inline_vis.winfo_exists():
            self.inline_vis.consume_log(line)

    # Ejecución
    def start_run(self):
        global _RUNNER_TID, _STOP_REQUESTED, _STOPPING
        if self.running:
            return

        self.clear_console()
        self.apply_settings()
        set_setting("paused", False)
        set_setting("stop_requested", False)
        _STOP_REQUESTED = False
        _STOPPING = False
        self.paused = False
        if hasattr(self, "inline_vis") and self.inline_vis.winfo_exists():
            self.inline_vis.set_paused(False)

        proto = self.var_proto.get()
        try:
            if proto == "Utopía (ideal)":
                fn = lambda: test_utopia(parse_csv(self.var_data.get()))
            elif proto == "Stop-and-Wait (simple)":
                fn = lambda: test_snw(parse_csv(self.var_data.get()))
            elif proto == "PAR (con retransmisión)":
                fn = lambda: test_par(parse_csv(self.var_data.get()))
            elif proto == "Sliding Window 1-bit (bidireccional)":
                fn = lambda: test_sw(parse_csv(self.var_data.get()), parse_csv(self.var_data2.get()))
            elif proto == "Go-Back-N":
                w = int(self.var_win.get())
                a_list = parse_csv(self.var_data.get())
                b_list = parse_csv(self.var_data2.get())
                fn = lambda: test_gbn(w, a_list, b_list)  # versión bidireccional
            elif proto == "Selective-Repeat":
                w = int(self.var_win.get())
                a_list = parse_csv(self.var_data.get())
                b_list = parse_csv(self.var_data2.get())
                fn = lambda: test_sr(w, a_list, b_list)    # versión bidireccional
            else:
                messagebox.showwarning("Atención", "Selecciona un protocolo válido.")
                return
        except Exception as e:
            messagebox.showerror("Error", f"Parámetros inválidos:\n{e}")
            return

        self.running = True
        self.btn_run.config(state="disabled")
        self.btn_pause.config(state="normal", text="⏸ Pausar")
        self.btn_stop.config(state="normal")

        def runner():
            global _RUNNER_TID, _STOPPING
            _RUNNER_TID = threading.get_ident()
            print(f"\n== Ejecutando: {proto} ==\n")
            try:
                fn()
                if not _STOP_REQUESTED:
                    print("\n== Finalizado ==\n")
            except KeyboardInterrupt:
                _STOPPING = True
                if _STOP_REQUESTED:
                    print("\n== Detenido por el usuario ==\n")
                else:
                    print("\n== Interrumpido ==\n")
            except Exception:
                _STOPPING = True
                tb = traceback.format_exc()
                print(tb)
                self.after(0, lambda: messagebox.showerror("Error en ejecución", tb))
            finally:
                self.after(0, self._finish_run_ui)
                _RUNNER_TID = None

        self.run_thread = threading.Thread(target=runner, daemon=True)
        self.run_thread.start()

    def _finish_run_ui(self):
        global _STOP_REQUESTED, _STOPPING
        self.running = False
        self.paused = False
        _STOP_REQUESTED = False
        _STOPPING = False
        set_setting("paused", False)
        set_setting("stop_requested", False)
        self.btn_run.config(state="normal")
        self.btn_pause.config(state="disabled", text="⏸ Pausar")
        self.btn_stop.config(state="disabled")
        if hasattr(self, "inline_vis") and self.inline_vis.winfo_exists():
            self.inline_vis.set_paused(False)

    def toggle_pause(self):
        if not self.running:
            return
        self.paused = not self.paused
        set_setting("paused", self.paused)
        if self.paused:
            self.btn_pause.config(text="▶ Reanudar")
            print("[Pausa]")
        else:
            self.btn_pause.config(text="⏸ Pausar")
            print("[Reanudar]")
        if hasattr(self, "inline_vis") and self.inline_vis.winfo_exists():
            self.inline_vis.set_paused(self.paused)

    def stop_run(self):
        global _STOP_REQUESTED
        if not self.running:
            return
        _STOP_REQUESTED = True
        set_setting("stop_requested", True)
        print("[Stop solicitado] intentando detener con seguridad…")

    # Utilidades de consola
    def clear_console(self):
        self.console.delete("1.0", tk.END)

    # Cierre limpio 
    def destroy(self):
        global _STOP_REQUESTED, _STOPPING
        try:
            _STOP_REQUESTED = True
            _STOPPING = True
            self.stdout_redirect.stop()
            self.stderr_redirect.stop()
            sys.stdout = sys.__stdout__
            sys.stderr = sys.__stderr__
        except Exception:
            pass
        super().destroy()

if __name__ == "__main__":
    app = App()
    app.mainloop()
