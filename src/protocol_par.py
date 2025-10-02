
# -*- coding: utf-8 -*-
"""
Protocol 3 (PAR/ARQ Alternante): flujo unidireccional sobre canal NO confiable.
Usa números de secuencia {0,1} y ACKs. Reintenta en TIMEOUT.
Basado en Tanenbaum (sender3/receiver3).
"""
from __future__ import annotations
from protocol_env import Environment, Packet, Frame, EventType, inc

class Protocol3PAR:
    def __init__(self, env: Environment):
        self.env = env
        self.MAX_SEQ = 1  # en PAR debe ser 1 (0/1)

    def sender(self, steps: int = 10_000):
        next_frame_to_send = 0
        buffer = Packet()
        self.env.from_network_layer(buffer)  # primer paquete

        for _ in range(steps):
            s = Frame()
            s.info = buffer
            s.seq = next_frame_to_send
            self.env.to_physical_layer(s)
            self.env.start_timer(s.seq)

            event = self.env.wait_for_event()
            if event == EventType.FRAME_ARRIVAL:
                self.env.from_physical_layer(s)  # ACK
                if s.ack == next_frame_to_send:
                    self.env.stop_timer(s.ack)
                    self.env.from_network_layer(buffer)  # siguiente paquete
                    next_frame_to_send = inc(next_frame_to_send, self.MAX_SEQ)
            elif event == EventType.TIMEOUT:
                # Se reenvía en el siguiente ciclo automáticamente
                pass

    def receiver(self, steps: int = 10_000):
        frame_expected = 0
        for _ in range(steps):
            event = self.env.wait_for_event()
            if event == EventType.FRAME_ARRIVAL:
                r = Frame()
                self.env.from_physical_layer(r)
                if r.seq == frame_expected:
                    self.env.to_network_layer(r.info)
                    frame_expected = inc(frame_expected, self.MAX_SEQ)

                s = Frame()
                s.ack = (1 - frame_expected)  # "cuál frame estoy ACKeando"
                self.env.to_physical_layer(s)
