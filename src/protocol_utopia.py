
# -*- coding: utf-8 -*-
"""
Protocol 1 (Utopia): flujo unidireccional, canal sin errores, receptor procesa infinito.
Basado en el esquema del libro de Tanenbaum (sender1/receiver1).
"""
from __future__ import annotations
from dataclasses import dataclass
from protocol_env import Environment, Packet, Frame, EventType

class Protocol1Utopia:
    """Implementación directa del 'pseudocódigo C' en Python, con comentarios en español."""
    def __init__(self, env: Environment):
        self.env = env

    def sender(self, steps: int = 1_000):
        """Emisor: bombea paquetes hacia el canal tan rápido como la red los produce."""
        for _ in range(steps):
            # from_network_layer: trae un paquete de la cola de la aplicación
            buffer = Packet()
            self.env.from_network_layer(buffer)

            # Construye y envía la trama
            s = Frame()
            s.info = buffer
            self.env.to_physical_layer(s)

    def receiver(self, steps: int = 1_000):
        """Receptor: espera arrival de tramas y entrega al host receptor."""
        for _ in range(steps):
            event = self.env.wait_for_event()  # aquí será FRAME_ARRIVAL
            if event == EventType.FRAME_ARRIVAL:
                r = Frame()
                self.env.from_physical_layer(r)
                self.env.to_network_layer(r.info)
