
# -*- coding: utf-8 -*-
"""
Protocol 5 (Go-Back-N): ventana de envío de tamaño MAX_SEQ+1; ACKs acumulativos;
retransmite todo lo pendiente tras TIMEOUT del más viejo.
Basado en Tanenbaum (protocol5).
"""
from __future__ import annotations
from typing import List
from protocol_env import Environment, Packet, Frame, EventType, inc, between

class Protocol5GoBackN:
    def __init__(self, env: Environment, max_seq: int = 7):
        self.env = env
        self.MAX_SEQ = max_seq

    def _send_data(self, frame_nr: int, frame_expected: int, buffer: List[Packet]) -> None:
        """Construye y envía una trama de datos (con piggyback ACK)."""
        s = Frame()
        s.info = buffer[frame_nr]
        s.seq = frame_nr
        s.ack = (frame_expected + self.MAX_SEQ) % (self.MAX_SEQ + 1)
        self.env.to_physical_layer(s)
        self.env.start_timer(frame_nr)

    def run(self, steps: int = 50_000):
        next_frame_to_send = 0
        ack_expected = 0
        frame_expected = 0
        nbuffered = 0
        buffer = [Packet() for _ in range(self.MAX_SEQ + 1)]

        self.env.enable_network_layer()

        for _ in range(steps):
            event = self.env.wait_for_event()
            if event == EventType.NETWORK_LAYER_READY:
                # obtener nuevo paquete
                self.env.from_network_layer(buffer[next_frame_to_send])
                nbuffered += 1
                self._send_data(next_frame_to_send, frame_expected, buffer)
                next_frame_to_send = inc(next_frame_to_send, self.MAX_SEQ)

            elif event == EventType.FRAME_ARRIVAL:
                r = Frame()
                self.env.from_physical_layer(r)

                # aceptar solo en orden
                if r.seq == frame_expected:
                    self.env.to_network_layer(r.info)
                    frame_expected = inc(frame_expected, self.MAX_SEQ)

                # ACK acumulativo (ack n implica n-1, n-2, ...)
                while between(ack_expected, r.ack, next_frame_to_send, self.MAX_SEQ):
                    nbuffered -= 1
                    self.env.stop_timer(ack_expected)
                    ack_expected = inc(ack_expected, self.MAX_SEQ)

            elif event == EventType.CKSUM_ERR:
                # ignorar tramas corruptas
                pass

            elif event == EventType.TIMEOUT:
                # retransmitir todo lo pendiente empezando por ack_expected
                next_frame_to_send = ack_expected
                i = 1
                while i <= nbuffered:
                    self._send_data(next_frame_to_send, frame_expected, buffer)
                    next_frame_to_send = inc(next_frame_to_send, self.MAX_SEQ)
                    i += 1

            # Control de la red
            if nbuffered < self.MAX_SEQ:
                self.env.enable_network_layer()
            else:
                self.env.disable_network_layer()
