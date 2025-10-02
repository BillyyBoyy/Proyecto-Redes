# env_ext.py
# -*- coding: utf-8 -*-
"""
Extiende Environment para permitir inyectar eventos de CKSUM_ERR desde el canal.
Mantiene compatibilidad con las primitivas de protocol_env.py.
"""
from __future__ import annotations

import time
from protocol_env import Environment, EventType

class EnvironmentEx(Environment):
    def __init__(self, max_seq: int = 7, timer_seconds: float = 0.5, ack_timer_seconds: float = 0.25):
        super().__init__(max_seq=max_seq, timer_seconds=timer_seconds, ack_timer_seconds=ack_timer_seconds)
        self._phy_error_count = 0  # cuántos errores están pendientes de notificar

    def channel_push_error(self) -> None:
        """El 'canal' solicita que el próximo evento sea un CKSUM_ERR."""
        self._phy_error_count += 1

    def wait_for_event(self) -> EventType:
        """
        Igual a la versión base, pero agregando la verificación de 'errores' del canal
        antes de revisar llegadas físicas. Así los protocolos pueden reaccionar a CKSUM_ERR.
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
                del self._timer_deadline[expired_k]
                return EventType.TIMEOUT

            # 2) ¿Ack timer?
            if self._ack_timer_on and now >= self._ack_timer_deadline:
                self._ack_timer_on = False
                return EventType.ACK_TIMEOUT

            # >>> INYECCIÓN DE ERRORES DEL CANAL <<<
            if self._phy_error_count > 0:
                self._phy_error_count -= 1
                return EventType.CKSUM_ERR

            # 3) ¿Llegó una trama por el canal físico?
            if self._phy_incoming:
                return EventType.FRAME_ARRIVAL

            # 4) ¿La capa de red tiene algo y está habilitada?
            if self._network_enabled and self._net_outgoing:
                return EventType.NETWORK_LAYER_READY

            time.sleep(0.001)
