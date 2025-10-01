# simulator.py
# -*- coding: utf-8 -*-
from __future__ import annotations

import threading
from typing import Callable, Optional, List

from env_ext import EnvironmentEx
from channel import Channel, OnFrameFn

# Protocolos
from protocol_utopia import Protocol1Utopia
from protocol_stop_and_wait import Protocol2StopAndWait
from protocol_par import Protocol3PAR
from protocol_sliding_window import Protocol4SlidingWindow1Bit
from protocol_go_back_n import Protocol5GoBackN
from protocol_selective_repeat import Protocol6SelectiveRepeat

class Simulator:
    """
    Orquesta 2 entornos (A/B), el canal y los hilos de protocolo.
    Exposición mínima para la UI:
      - start(...), stop(), pause(bool)
      - log de frames vía callback 'on_frame'
    """
    def __init__(self, on_frame: Optional[OnFrameFn] = None, on_log: Optional[Callable[[str], None]] = None):
        self.on_frame = on_frame
        self.on_log = on_log or (lambda msg: None)

        self.envA: Optional[EnvironmentEx] = None
        self.envB: Optional[EnvironmentEx] = None
        self.channel: Optional[Channel] = None
        self.threads: List[threading.Thread] = []

    def _log(self, msg: str):
        self.on_log(msg)

    def _inject_payloads(self, env: EnvironmentEx, text: str, repeat: int = 1):
        # divide el texto en fragmentos "paquetes" (bytes)
        data = text.encode("utf-8")
        chunk = 16  # bytes por "packet" (ajustable)
        for _ in range(repeat):
            for i in range(0, len(data), chunk):
                env.app_send(data[i:i+chunk])

    def start(self,
              protocol: str,
              max_seq: int = 7,
              error_prob: float = 0.0,
              loss_prob: float = 0.0,
              min_delay_ms: int = 50,
              max_delay_ms: int = 150,
              payload_a: str = "HELLO FROM A " * 5,
              payload_b: str = "HELLO FROM B " * 5):
        # 1) entornos
        self.envA = EnvironmentEx(max_seq=max_seq)
        self.envB = EnvironmentEx(max_seq=max_seq)

        # 2) canal
        self.channel = Channel(self.envA, self.envB,
                               min_delay_ms=min_delay_ms, max_delay_ms=max_delay_ms,
                               error_prob=error_prob, loss_prob=loss_prob,
                               on_frame=self.on_frame)
        self.channel.start()

        # 3) protocolos
        protocol = protocol.lower().strip()

        if protocol == "utopia":
            # Tráfico A->B
            self._inject_payloads(self.envA, payload_a, repeat=2)
            pA = Protocol1Utopia(self.envA)
            pB = Protocol1Utopia(self.envB)

            t1 = threading.Thread(target=pA.sender, kwargs=dict(steps=50_000), daemon=True)
            t2 = threading.Thread(target=pB.receiver, kwargs=dict(steps=50_000), daemon=True)

        elif protocol == "stop-and-wait":
            # Tráfico A->B
            self._inject_payloads(self.envA, payload_a, repeat=2)
            pA = Protocol2StopAndWait(self.envA)
            pB = Protocol2StopAndWait(self.envB)

            t1 = threading.Thread(target=pA.sender, kwargs=dict(steps=50_000), daemon=True)
            t2 = threading.Thread(target=pB.receiver, kwargs=dict(steps=50_000), daemon=True)

        elif protocol == "par":
            # Tráfico A->B (ARQ alternante)
            self._inject_payloads(self.envA, payload_a, repeat=2)
            pA = Protocol3PAR(self.envA)
            pB = Protocol3PAR(self.envB)

            t1 = threading.Thread(target=pA.sender, kwargs=dict(steps=50_000), daemon=True)
            t2 = threading.Thread(target=pB.receiver, kwargs=dict(steps=50_000), daemon=True)

        elif protocol == "sliding-1bit":
            # Tráfico bidireccional
            self._inject_payloads(self.envA, payload_a, repeat=2)
            self._inject_payloads(self.envB, payload_b, repeat=2)
            pA = Protocol4SlidingWindow1Bit(self.envA)
            pB = Protocol4SlidingWindow1Bit(self.envB)

            t1 = threading.Thread(target=pA.run, kwargs=dict(steps=100_000), daemon=True)
            t2 = threading.Thread(target=pB.run, kwargs=dict(steps=100_000), daemon=True)

        elif protocol == "go-back-n":
            # Bidireccional
            self._inject_payloads(self.envA, payload_a, repeat=2)
            self._inject_payloads(self.envB, payload_b, repeat=2)
            pA = Protocol5GoBackN(self.envA, max_seq=max_seq)
            pB = Protocol5GoBackN(self.envB, max_seq=max_seq)

            t1 = threading.Thread(target=pA.run, kwargs=dict(steps=150_000), daemon=True)
            t2 = threading.Thread(target=pB.run, kwargs=dict(steps=150_000), daemon=True)

        elif protocol == "selective-repeat":
            # Bidireccional
            self._inject_payloads(self.envA, payload_a, repeat=2)
            self._inject_payloads(self.envB, payload_b, repeat=2)
            pA = Protocol6SelectiveRepeat(self.envA, max_seq=max_seq)
            pB = Protocol6SelectiveRepeat(self.envB, max_seq=max_seq)

            t1 = threading.Thread(target=pA.run, kwargs=dict(steps=200_000), daemon=True)
            t2 = threading.Thread(target=pB.run, kwargs=dict(steps=200_000), daemon=True)

        else:
            raise ValueError(f"Protocolo desconocido: {protocol}")

        # 4) arrancar hilos
        self.threads = [t1, t2]
        for t in self.threads:
            t.start()
        self._log(f"[Simulator] protocolo={protocol}, max_seq={max_seq}, err={error_prob:.2%}, loss={loss_prob:.2%}")

    def pause(self, value: bool):
        if self.channel:
            self.channel.pause(value)
        self._log("[Simulator] paused" if value else "[Simulator] resumed")

    def stop(self):
        # detener canal y dejar que los hilos terminen solos
        if self.channel:
            self.channel.stop()
        self._log("[Simulator] stopped")
