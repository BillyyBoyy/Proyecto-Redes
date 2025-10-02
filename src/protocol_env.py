
# -*- coding: utf-8 -*-
"""
Entorno de simulación para los protocolos de enlace de datos de Tanenbaum.
Este módulo provee las estructuras (Packet, Frame), los tipos de eventos,
y una clase Environment que implementa las primitivas de "protocol.h":
  - wait_for_event, from_network_layer, to_network_layer,
  - from_physical_layer, to_physical_layer,
  - start_timer/stop_timer, start_ack_timer/stop_ack_timer,
  - enable_network_layer/disable_network_layer.
La idea es que puedas enchufar estos métodos a una simulación propia
(o a pruebas unitarias) sin tener que depender de hilos reales.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Deque, Dict, Optional
from collections import deque
import time

MAX_PKT = 1024  # tamaño máximo del paquete (bytes)


class EventType(Enum):
    """Tipos de eventos que notifican el 'hardware/simulador' al protocolo."""
    FRAME_ARRIVAL = auto()
    CKSUM_ERR = auto()
    TIMEOUT = auto()
    NETWORK_LAYER_READY = auto()
    ACK_TIMEOUT = auto()


class FrameKind(Enum):
    """Tipo de trama (solo necesario para Selective Repeat)."""
    DATA = auto()
    ACK = auto()
    NAK = auto()


@dataclass
class Packet:
    """Paquete de capa de red (payload)."""
    data: bytes = b""


@dataclass
class Frame:
    """Trama de capa de enlace (lleva un Packet)."""
    kind: FrameKind = FrameKind.DATA
    seq: int = 0
    ack: int = 0
    info: Packet = field(default_factory=Packet)


def inc(k: int, max_seq: int) -> int:
    """
    Incrementa 'k' circularmente en rango [0, max_seq].
    Equivalente a la macro inc de 'protocol.h'.
    """
    return (k + 1) % (max_seq + 1)


def between(a: int, b: int, c: int, max_seq: int) -> bool:
    """
    Devuelve True si a <= b < c circularmente; False en caso contrario.
    Usado en Go-Back-N y Selective Repeat.
    """
    return ((a <= b) and (b < c)) or ((c < a) and (a <= b)) or ((b < c) and (c < a))


class Environment:
    """
    Entorno minimalista que emula las operaciones del 'protocol.h'.
    Puedes ajustar los tiempos de timers y el modelado de canal (entrega inmediata).
    Para una simulación realista, conecta dos entornos y haz que el to_physical_layer
    de uno deposite en el from_physical_layer del otro con latencia/errores.
    """
    def __init__(self, max_seq: int = 7, timer_seconds: float = 0.5, ack_timer_seconds: float = 0.25):
        self.MAX_SEQ = max_seq
        self._network_enabled = True

        # Colas para modelar red y canal físico
        self._net_outgoing: Deque[Packet] = deque()   # produce el "sender" con from_network_layer
        self._net_incoming: Deque[Packet] = deque()   # recibe el "receiver" con to_network_layer

        self._phy_incoming: Deque[Frame] = deque()    # llega al protocolo via from_physical_layer
        self._phy_outgoing: Deque[Frame] = deque()    # lo que envía el protocolo (útil en tests)

        # Timers por trama (k -> deadline)
        self._timer_deadline: Dict[int, float] = {}
        self._timer_seconds = timer_seconds

        # Ack timer
        self._ack_timer_on = False
        self._ack_timer_deadline = 0.0
        self._ack_timer_seconds = ack_timer_seconds

    # ---------------- Primitivas "protocol.h" ----------------
    def wait_for_event(self) -> EventType:
        """
        Bloquea activamente hasta que ocurra un evento:
        1) timeout de algún timer, 2) ack timeout,
        3) arrival de una trama física, 4) network layer ready.
        Simulación simple: se verifica en bucle con sleep corto.
        """
        while True:
            now = time.time()

            # 1) ¿Expiró algún timer de trama?
            expired_k = None
            for k, deadline in list(self._timer_deadline.items()):
                if now >= deadline:
                    expired_k = k
                    break
            if expired_k is not None:
                # Consumimos el timer; los protocolos decidirán qué hacer.
                del self._timer_deadline[expired_k]
                return EventType.TIMEOUT

            # 2) ¿Ack timer?
            if self._ack_timer_on and now >= self._ack_timer_deadline:
                self._ack_timer_on = False
                return EventType.ACK_TIMEOUT

            # 3) ¿Llegó una trama por el canal físico?
            if self._phy_incoming:
                return EventType.FRAME_ARRIVAL

            # 4) ¿La capa de red tiene algo y está habilitada?
            if self._network_enabled and self._net_outgoing:
                return EventType.NETWORK_LAYER_READY

            time.sleep(0.001)

    # Red (aplicación) -> Protocolo
    def from_network_layer(self, p: Packet) -> None:
        """Entrega un paquete de la capa de red al protocolo (lado emisor)."""
        if not self._net_outgoing:
            raise RuntimeError("from_network_layer(): no hay paquetes en cola.")
        pkt = self._net_outgoing.popleft()
        p.data = pkt.data

    # Protocolo -> Red (aplicación)
    def to_network_layer(self, p: Packet) -> None:
        """El protocolo entrega al host receptor un paquete decodificado."""
        self._net_incoming.append(Packet(data=p.data))

    # Canal físico -> Protocolo
    def from_physical_layer(self, r: Frame) -> None:
        """Carga la siguiente trama recibida desde el canal físico al parámetro 'r'."""
        if not self._phy_incoming:
            raise RuntimeError("from_physical_layer(): no hay tramas disponibles.")
        f = self._phy_incoming.popleft()
        r.kind = f.kind
        r.seq = f.seq
        r.ack = f.ack
        r.info = Packet(data=f.info.data)

    # Protocolo -> Canal físico
    def to_physical_layer(self, s: Frame) -> None:
        """Envía una trama; aquí solo la registramos en _phy_outgoing (eco inmediato)."""
        # En una simulación real, aquí harías: "canal.deliver(s)" con pérdidas/errores/latencia.
        self._phy_outgoing.append(Frame(kind=s.kind, seq=s.seq, ack=s.ack, info=Packet(data=s.info.data)))

    # Timers
    def start_timer(self, k: int) -> None:
        self._timer_deadline[k] = time.time() + self._timer_seconds

    def stop_timer(self, k: int) -> None:
        self._timer_deadline.pop(k, None)

    def start_ack_timer(self) -> None:
        self._ack_timer_on = True
        self._ack_timer_deadline = time.time() + self._ack_timer_seconds

    def stop_ack_timer(self) -> None:
        self._ack_timer_on = False

    # Control de la capa de red
    def enable_network_layer(self) -> None:
        self._network_enabled = True

    def disable_network_layer(self) -> None:
        self._network_enabled = False

    # ---------------- Utilidades de prueba ----------------
    def app_send(self, payload: bytes) -> None:
        """Simula que la aplicación (capa de red) genera un paquete a enviar."""
        self._net_outgoing.append(Packet(data=payload))

    def app_recv_all(self) -> bytes:
        """Recoge todos los paquetes que el receptor haya entregado a la aplicación."""
        out = b""
        while self._net_incoming:
            out += self._net_incoming.popleft().data
        return out

    def channel_push_frame(self, f: Frame) -> None:
        """Inyecta manualmente una trama 'recibida' en el lado receptor (tests)."""
        self._phy_incoming.append(f)

    def take_phy_outgoing(self) -> Optional[Frame]:
        """Obtiene (y consume) la siguiente trama que el protocolo envió por el canal físico."""
        return self._phy_outgoing.popleft() if self._phy_outgoing else None
