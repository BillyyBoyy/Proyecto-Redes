
# -*- coding: utf-8 -*-
"""
Protocol 6 (Selective Repeat): acepta tramas fuera de orden y las entrega en orden.
Cada trama pendiente tiene su propio timer; al expirar, solo se retransmite esa trama.
Basado en Tanenbaum (protocol6).
"""
from __future__ import annotations
from typing import List
from protocol_env import Environment, Packet, Frame, EventType, FrameKind, inc, between

class Protocol6SelectiveRepeat:
    def __init__(self, env: Environment, max_seq: int = 7):
        self.env = env
        self.MAX_SEQ = max_seq
        self.NR_BUFS = (self.MAX_SEQ + 1) // 2
        self.no_nak = True
        self.oldest_frame = self.MAX_SEQ + 1  # usado solo por el simulador en el libro

    def _send_frame(self, fk: FrameKind, frame_nr: int, frame_expected: int, out_buf: List[Packet]) -> None:
        """Construye y envía trama de DATA/ACK/NAK. Reinicia timers según corresponda."""
        s = Frame()
        s.kind = fk
        if fk == FrameKind.DATA:
            s.info = out_buf[frame_nr % self.NR_BUFS]
        s.seq = frame_nr
        s.ack = (frame_expected + self.MAX_SEQ) % (self.MAX_SEQ + 1)
        if fk == FrameKind.NAK:
            self.no_nak = False
        self.env.to_physical_layer(s)
        if fk == FrameKind.DATA:
            self.env.start_timer(frame_nr % self.NR_BUFS)
        self.env.stop_ack_timer()  # al enviar algo, no hace falta un ACK separado

    def run(self, steps: int = 100_000):
        ack_expected = 0               # borde inferior de la ventana del emisor
        next_frame_to_send = 0         # borde superior + 1
        frame_expected = 0             # borde inferior de la ventana del receptor
        too_far = self.NR_BUFS         # borde superior del receptor + 1

        out_buf = [Packet() for _ in range(self.NR_BUFS)]
        in_buf = [Packet() for _ in range(self.NR_BUFS)]
        arrived = [False] * self.NR_BUFS
        nbuffered = 0

        self.env.enable_network_layer()

        for _ in range(steps):
            event = self.env.wait_for_event()
            if event == EventType.NETWORK_LAYER_READY:
                nbuffered += 1
                self.env.from_network_layer(out_buf[next_frame_to_send % self.NR_BUFS])
                self._send_frame(FrameKind.DATA, next_frame_to_send, frame_expected, out_buf)
                next_frame_to_send = inc(next_frame_to_send, self.MAX_SEQ)

            elif event == EventType.FRAME_ARRIVAL:
                r = Frame()
                self.env.from_physical_layer(r)

                if r.kind == FrameKind.DATA:
                    if (r.seq != frame_expected) and self.no_nak:
                        self._send_frame(FrameKind.NAK, 0, frame_expected, out_buf)
                    else:
                        self.env.start_ack_timer()

                    if between(frame_expected, r.seq, too_far, self.MAX_SEQ) and (not arrived[r.seq % self.NR_BUFS]):
                        arrived[r.seq % self.NR_BUFS] = True
                        in_buf[r.seq % self.NR_BUFS] = r.info

                        # Entrega en orden mientras hayan llegado consecutivas
                        while arrived[frame_expected % self.NR_BUFS]:
                            self.env.to_network_layer(in_buf[frame_expected % self.NR_BUFS])
                            self.no_nak = True
                            arrived[frame_expected % self.NR_BUFS] = False
                            frame_expected = inc(frame_expected, self.MAX_SEQ)
                            too_far = inc(too_far, self.MAX_SEQ)
                            self.env.start_ack_timer()

                if (r.kind == FrameKind.NAK) and between(ack_expected, (r.ack + 1) % (self.MAX_SEQ + 1), next_frame_to_send, self.MAX_SEQ):
                    self._send_frame(FrameKind.DATA, (r.ack + 1) % (self.MAX_SEQ + 1), frame_expected, out_buf)

                # Process piggybacked ACKs
                while between(ack_expected, r.ack, next_frame_to_send, self.MAX_SEQ):
                    nbuffered -= 1
                    self.env.stop_timer(ack_expected % self.NR_BUFS)
                    ack_expected = inc(ack_expected, self.MAX_SEQ)

            elif event == EventType.CKSUM_ERR:
                if self.no_nak:
                    self._send_frame(FrameKind.NAK, 0, frame_expected, out_buf)

            elif event == EventType.TIMEOUT:
                # Retransmitir la trama más vieja
                self._send_frame(FrameKind.DATA, self.oldest_frame, frame_expected, out_buf)

            elif event == EventType.ACK_TIMEOUT:
                # Enviar ACK puro
                self._send_frame(FrameKind.ACK, 0, frame_expected, out_buf)

            if nbuffered < self.NR_BUFS:
                self.env.enable_network_layer()
            else:
                self.env.disable_network_layer()
