# protocol_selective_repeat.py
from events import Packet, Frame, fmt_frame, EventType, Event, sleep_step

class SelectiveRepeatBidiProtocol:
    """
    Selective Repeat bidireccional (A↔B) simplificado para la simulación:
    - Cada lado (A y B) tiene su ventana w, base y next_seq.
    - Los frames pueden llegar fuera de orden; el receptor los bufferiza y entrega en orden.
    - Solo se retransmiten los frames con error/timeout (no se hace rollback completo).
    - Turnos alternados: primero A→B, luego B→A.

    Prints compatibles con el resto del proyecto:
      A → medio: [DATA ...]
      medio → B (llegó): [DATA ...]
      B ↓ capa_red (entregado): [DATA ...]
      B → medio: [DATA ...]
      medio → A (llegó): [DATA ...]
      A ↓ capa_red (entregado): [DATA ...]
    """

    def __init__(self, window_size, data_a, data_b):
        self.w = max(1, int(window_size))

        # Construcción de frames para cada sentido
        self.frames_ab = [Frame("data", i, 0, Packet(str(d))) for i, d in enumerate(data_a)]
        self.frames_ba = [Frame("data", i, 0, Packet(str(d))) for i, d in enumerate(data_b)]

        # ----- Estado A→B -----
        self.n_ab = len(self.frames_ab)
        self.base_ab = 0
        self.next_ab = 0
        self.pending_ab = {}   # seq -> frame aún no "ackeado"
        self.medium_ab = []    # frames en tránsito A→B
        self.recvbuf_b = {}    # buffer en B por seq
        self.expected_b = 0    # próximo en orden que B puede entregar
        self.dest_b = []       # entregados en orden a B

        # ----- Estado B→A -----
        self.n_ba = len(self.frames_ba)
        self.base_ba = 0
        self.next_ba = 0
        self.pending_ba = {}
        self.medium_ba = []
        self.recvbuf_a = {}
        self.expected_a = 0
        self.dest_a = []

    # ======================== A → B ========================
    def _send_window_ab(self):
        while self.next_ab < self.base_ab + self.w and self.next_ab < self.n_ab:
            f = self.frames_ab[self.next_ab]
            self.medium_ab.append(f)
            self.pending_ab[f.sequence_number] = f
            print("A → medio:", fmt_frame(f))
            sleep_step(0.7)
            self.next_ab += 1

    def _wait_and_process_ab(self):
        errors = []
        while self.medium_ab:
            f = self.medium_ab.pop(0)
            ev = Event.wait_for_event_static(
                [EventType.FRAME_ARRIVAL, EventType.CKSUM_ERR, EventType.TIMEOUT]
            )
            if ev.event_type == EventType.FRAME_ARRIVAL:
                print("medio → B (llegó):", fmt_frame(f))
                if f.sequence_number in self.pending_ab:
                    del self.pending_ab[f.sequence_number]
                # Buffer si está dentro de la ventana de recepción de B
                if self.base_ab <= f.sequence_number < self.base_ab + self.w:
                    self.recvbuf_b[f.sequence_number] = f
                # Entregar en orden todo lo posible
                self._deliver_in_order_b()
                sleep_step(0.6)
            else:
                print(f"× Evento {ev.event_type} en s={f.sequence_number}. Se reintenta solo ese frame (A→B).")
                errors.append(f.sequence_number)
                sleep_step(0.6)
        # Reintentamos empezando por el menor seq que falló
        if errors:
            self.next_ab = min(self.next_ab, min(errors))

    def _deliver_in_order_b(self):
        while self.expected_b in self.recvbuf_b:
            fr = self.recvbuf_b.pop(self.expected_b)
            self.dest_b.append(fr)
            print("B ↓ capa_red (entregado):", fmt_frame(fr))
            self.base_ab += 1
            self.expected_b += 1

    # ======================== B → A ========================
    def _send_window_ba(self):
        while self.next_ba < self.base_ba + self.w and self.next_ba < self.n_ba:
            f = self.frames_ba[self.next_ba]
            self.medium_ba.append(f)
            self.pending_ba[f.sequence_number] = f
            print("B → medio:", fmt_frame(f))
            sleep_step(0.7)
            self.next_ba += 1

    def _wait_and_process_ba(self):
        errors = []
        while self.medium_ba:
            f = self.medium_ba.pop(0)
            ev = Event.wait_for_event_static(
                [EventType.FRAME_ARRIVAL, EventType.CKSUM_ERR, EventType.TIMEOUT]
            )
            if ev.event_type == EventType.FRAME_ARRIVAL:
                print("medio → A (llegó):", fmt_frame(f))
                if f.sequence_number in self.pending_ba:
                    del self.pending_ba[f.sequence_number]
                if self.base_ba <= f.sequence_number < self.base_ba + self.w:
                    self.recvbuf_a[f.sequence_number] = f
                self._deliver_in_order_a()
                sleep_step(0.6)
            else:
                print(f"× Evento {ev.event_type} en s={f.sequence_number}. Se reintenta solo ese frame (B→A).")
                errors.append(f.sequence_number)
                sleep_step(0.6)
        if errors:
            self.next_ba = min(self.next_ba, min(errors))

    def _deliver_in_order_a(self):
        while self.expected_a in self.recvbuf_a:
            fr = self.recvbuf_a.pop(self.expected_a)
            self.dest_a.append(fr)
            print("A ↓ capa_red (entregado):", fmt_frame(fr))
            self.base_ba += 1
            self.expected_a += 1

    # ======================== Orquestación ========================
    def start(self):
        print(f"\n=== SELECTIVE REPEAT (bidireccional, ventana = {self.w}) ===")
        steps = 0
        # Ejecuta hasta terminar ambos sentidos o un límite de seguridad
        while (len(self.dest_b) < self.n_ab or len(self.dest_a) < self.n_ba) and steps < 800:
            # Turno A→B
            if len(self.dest_b) < self.n_ab:
                self._send_window_ab()
                self._wait_and_process_ab()
            # Turno B→A
            if len(self.dest_a) < self.n_ba:
                self._send_window_ba()
                self._wait_and_process_ba()
            steps += 1

        print("✔ Entrega en B (desde A):", [fr.packet.data for fr in self.dest_b])
        print("✔ Entrega en A (desde B):", [fr.packet.data for fr in self.dest_a])


def test(window_size=3, data_a=None, data_b=None):
    """
    Firma nueva (bidireccional). Para compatibilidad:
    - Si te llaman como test(w, data) (viejo), lo tratamos como A→B y B→A vacío.
    """
    if data_b is None and data_a is not None and not isinstance(data_a, int):
        # Modo compat: solo A→B
        data_b = []
    if data_a is None:
        data_a = ["a", "b", "c", "d", "e", "f"]
    if data_b is None:
        data_b = ["r1", "r2", "r3"]
    SelectiveRepeatBidiProtocol(window_size, data_a, data_b).start()
