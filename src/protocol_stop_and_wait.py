
# -*- coding: utf-8 -*-
"""
Protocol 2 (Stop-and-Wait): flujo unidireccional, canal sin errores, pero el receptor
tiene capacidad/velocidad finita, así que el emisor espera un "despertador" antes de seguir.
Basado en Tanenbaum.
"""
from __future__ import annotations
from protocol_env import Environment, Packet, Frame, EventType

class Protocol2StopAndWait:
    def __init__(self, env: Environment):
        self.env = env

    def sender(self, steps: int = 1_000):
        for _ in range(steps):
            buffer = Packet()
            self.env.from_network_layer(buffer)  # obtiene un paquete a enviar
            s = Frame()
            s.info = buffer
            self.env.to_physical_layer(s)       # lo envía
            # Espera a que el receptor "lo despierte" (dummy frame)
            event = self.env.wait_for_event()
            if event != EventType.FRAME_ARRIVAL:
                # En el modelo original, el único evento esperado es FRAME_ARRIVAL
                # (no hay errores). Aquí lo ignoramos.
                pass

    def receiver(self, steps: int = 1_000):
        for _ in range(steps):
            event = self.env.wait_for_event()
            if event == EventType.FRAME_ARRIVAL:
                r = Frame()
                self.env.from_physical_layer(r)   # recibe trama
                self.env.to_network_layer(r.info) # entrega a la app
                s = Frame()                        # dummy frame para "despertar" emisor
                self.env.to_physical_layer(s)
