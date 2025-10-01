# channel.py
# -*- coding: utf-8 -*-
from __future__ import annotations

import threading
import time
import random
from typing import Callable, List, Optional, Tuple
from protocol_env import Frame, FrameKind
from env_ext import EnvironmentEx

OnFrameFn = Callable[[str, str, Frame, str], None]
# firma: on_frame(evento, direccion, frame, detalle)
# evento ∈ {"sent", "delivered", "dropped", "errored"}
# direccion ∈ {"A->B", "B->A"}

class Channel:
    """
    Canal dúplex con latencia, pérdida y corrupción.
    - Toma frames de envA y los entrega a envB (y viceversa) con retardo.
    - Con 'error_prob' inyecta CKSUM_ERR en el receptor.
    - Con 'loss_prob' descarta la trama silenciosamente.
    """
    def __init__(self,
                 env_a: EnvironmentEx,
                 env_b: EnvironmentEx,
                 min_delay_ms: int = 50,
                 max_delay_ms: int = 150,
                 error_prob: float = 0.0,
                 loss_prob: float = 0.0,
                 on_frame: Optional[OnFrameFn] = None):
        self.env_a = env_a
        self.env_b = env_b
        self.min_delay = min_delay_ms / 1000.0
        self.max_delay = max_delay_ms / 1000.0
        self.error_prob = error_prob
        self.loss_prob = loss_prob
        self.on_frame = on_frame

        self._running = threading.Event()
        self._paused = threading.Event()
        self._paused.clear()
        self._running.clear()
        self._thread = threading.Thread(target=self._pump, daemon=True)

        # Agenda de entregas: (t_entrega, destino, frame, direccion, es_error)
        self._in_flight: List[Tuple[float, EnvironmentEx, Frame, str, bool]] = []
        self._lock = threading.Lock()

    def start(self):
        self._running.set()
        self._thread.start()

    def stop(self):
        self._running.clear()
        self._thread.join(timeout=1.0)

    def pause(self, value: bool):
        if value:
            self._paused.set()
        else:
            self._paused.clear()

    def _schedule(self, dst: EnvironmentEx, frame: Frame, direction: str, is_error: bool):
        delay = random.uniform(self.min_delay, self.max_delay)
        t_delivery = time.time() + delay
        with self._lock:
            self._in_flight.append((t_delivery, dst, frame, direction, is_error))

    def _take_and_schedule(self, src: EnvironmentEx, dst: EnvironmentEx, direction: str):
        f = src.take_phy_outgoing()
        if f is None:
            return
        if self.on_frame:
            self.on_frame("sent", direction, f, f"seq={f.seq}, ack={f.ack}, kind={f.kind.name}")

        # ¿se pierde?
        if random.random() < self.loss_prob:
            if self.on_frame:
                self.on_frame("dropped", direction, f, "lost in channel")
            return

        # ¿se corrompe?
        is_error = (random.random() < self.error_prob)
        self._schedule(dst, f, direction, is_error)

    def _deliver_due(self):
        now = time.time()
        due: List[Tuple[float, EnvironmentEx, Frame, str, bool]] = []
        with self._lock:
            keep: List[Tuple[float, EnvironmentEx, Frame, str, bool]] = []
            for item in self._in_flight:
                if item[0] <= now:
                    due.append(item)
                else:
                    keep.append(item)
            self._in_flight = keep

        for _, dst, f, direction, is_error in due:
            if is_error:
                dst.channel_push_error()
                if self.on_frame:
                    self.on_frame("errored", direction, f, "CKSUM_ERR injected")
            else:
                dst.channel_push_frame(f)
                if self.on_frame:
                    self.on_frame("delivered", direction, f, "OK")

    def _pump(self):
        while self._running.is_set():
            if self._paused.is_set():
                time.sleep(0.01)
                continue

            # Aspirar tramas salientes en ambos sentidos
            self._take_and_schedule(self.env_a, self.env_b, "A->B")
            self._take_and_schedule(self.env_b, self.env_a, "B->A")

            # Entregar lo vencido
            self._deliver_due()

            time.sleep(0.001)
