
# -*- coding: utf-8 -*-
"""
Protocol 4 (Sliding Window de 1 bit, bidireccional).
Emisor y receptor simultáneos con piggyback ACK (MAX_SEQ=1).
Basado en Tanenbaum (protocol4).
"""
from __future__ import annotations
from protocol_env import Environment, Packet, Frame, EventType, inc

class Protocol4SlidingWindow1Bit:
    def __init__(self, env: Environment):
        self.env = env
        self.MAX_SEQ = 1  # 0/1

    def run(self, steps: int = 10_000):
        next_frame_to_send = 0   # 0 o 1
        frame_expected = 0       # 0 o 1

        buffer = Packet()
        self.env.from_network_layer(buffer)  # primer paquete

        # Enviar primer frame
        s = Frame()
        s.info = buffer
        s.seq = next_frame_to_send
        s.ack = (1 - frame_expected)
        self.env.to_physical_layer(s)
        self.env.start_timer(s.seq)

        for _ in range(steps):
            event = self.env.wait_for_event()
            if event == EventType.FRAME_ARRIVAL:
                r = Frame()
                self.env.from_physical_layer(r)

                # Flujo entrante
                if r.seq == frame_expected:
                    self.env.to_network_layer(r.info)
                    frame_expected = inc(frame_expected, self.MAX_SEQ)

                # Flujo saliente (piggyback ACK)
                if r.ack == next_frame_to_send:
                    self.env.stop_timer(r.ack)
                    self.env.from_network_layer(buffer)
                    next_frame_to_send = inc(next_frame_to_send, self.MAX_SEQ)

            # Construir y enviar siguiente trama (con piggyback del ACK más reciente)
            s = Frame()
            s.info = buffer
            s.seq = next_frame_to_send
            s.ack = (1 - frame_expected)
            self.env.to_physical_layer(s)
            self.env.start_timer(s.seq)
