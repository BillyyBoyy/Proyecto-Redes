from events import Packet, Frame, fmt_frame, EventType, Event, sleep_step

class GoBackNBidiProtocol:
    """
    Go-Back-N bidireccional (A↔B) simplificado:
    - Cada lado (A y B) tiene su propia ventana (mismo w), base y next_seq.
    - No modelamos ACKs explícitos: si todos los frames de la ventana llegan → se desliza base.
      Si ocurre un error/timeout en el primero que falle → Go-Back-N desde la base de ese lado.
    - Se alternan turnos: primero A→B, luego B→A, y así sucesivamente.
    - Prints compatibles con el estilo del CLI:
        "A → medio: [DATA ...]"
        "medio → B: [DATA ...]"
        "B → medio: [DATA ...]"
        "medio → A: [DATA ...]"
    """

    def __init__(self, window_size, data_a, data_b):
        self.window_size = max(1, int(window_size))

        # Frames de A→B y B→A
        self.frames_a = [Frame("data", i, 0, Packet(str(d))) for i, d in enumerate(data_a)]
        self.frames_b = [Frame("data", i, 0, Packet(str(d))) for i, d in enumerate(data_b)]

        # Estado A→B
        self.base_a = 0
        self.next_a = 0
        self.medium_ab = []   # "en vuelo" de A hacia B
        self.dest_b = []      # entregados en B (desde A)

        # Estado B→A
        self.base_b = 0
        self.next_b = 0
        self.medium_ba = []   # "en vuelo" de B hacia A
        self.dest_a = []      # entregados en A (desde B)

    # ---------------- A → B ----------------
    def _send_window_ab(self):
        while self.next_a < self.base_a + self.window_size and self.next_a < len(self.frames_a):
            f = self.frames_a[self.next_a]
            self.medium_ab.append(f)
            print("A → medio:", fmt_frame(f))
            sleep_step(0.7)
            self.next_a += 1

    def _wait_and_process_ab(self):
        error = False
        # Procesa en orden de envío desde base_a hasta next_a-1
        for idx in range(self.base_a, self.next_a):
            if not self.medium_ab:
                break
            ev = Event.wait_for_event_static([EventType.FRAME_ARRIVAL, EventType.CKSUM_ERR, EventType.TIMEOUT])
            f = self.medium_ab.pop(0)
            if ev.event_type == EventType.FRAME_ARRIVAL:
                self.dest_b.append(f)
                print("medio → B:", fmt_frame(f))
                sleep_step(0.6)
            else:
                # Primer fallo: GBN desde base
                print(f"× Evento {ev.event_type} en s={f.sequence_number}. Go-Back-N A→B desde base={self.base_a}")
                sleep_step(0.6)
                error = True
                break

        if not error:
            # Todos confirmados (cumulativo) → deslizar ventana
            self.base_a = self.next_a
        else:
            # Reiniciar envío desde base y descartar cualquier "en vuelo" restante
            self.next_a = self.base_a
            self.medium_ab.clear()

    # ---------------- B → A ----------------
    def _send_window_ba(self):
        while self.next_b < self.base_b + self.window_size and self.next_b < len(self.frames_b):
            f = self.frames_b[self.next_b]
            self.medium_ba.append(f)
            print("B → medio:", fmt_frame(f))
            sleep_step(0.7)
            self.next_b += 1

    def _wait_and_process_ba(self):
        error = False
        for idx in range(self.base_b, self.next_b):
            if not self.medium_ba:
                break
            ev = Event.wait_for_event_static([EventType.FRAME_ARRIVAL, EventType.CKSUM_ERR, EventType.TIMEOUT])
            f = self.medium_ba.pop(0)
            if ev.event_type == EventType.FRAME_ARRIVAL:
                self.dest_a.append(f)
                print("medio → A:", fmt_frame(f))
                sleep_step(0.6)
            else:
                print(f"× Evento {ev.event_type} en s={f.sequence_number}. Go-Back-N B→A desde base={self.base_b}")
                sleep_step(0.6)
                error = True
                break

        if not error:
            self.base_b = self.next_b
        else:
            self.next_b = self.base_b
            self.medium_ba.clear()

    # ---------------- Orquestación ----------------
    def start(self):
        print(f"\n=== GO-BACK-N (bidireccional, ventana = {self.window_size}) ===")
        steps = 0
        # Ejecuta hasta terminar ambos sentidos o llegar a un límite razonable
        while (self.base_a < len(self.frames_a) or self.base_b < len(self.frames_b)) and steps < 400:
            # Turno A→B
            if self.base_a < len(self.frames_a):
                self._send_window_ab()
                self._wait_and_process_ab()

            # Turno B→A
            if self.base_b < len(self.frames_b):
                self._send_window_ba()
                self._wait_and_process_ba()

            steps += 1

        print(" Entrega en B (desde A):", [fr.packet.data for fr in self.dest_b])
        print(" Entrega en A (desde B):", [fr.packet.data for fr in self.dest_a])


def test(window_size=3, data_a=None, data_b=None):
    """
    Test bidireccional:
      - window_size: tamaño de ventana
      - data_a: mensajes desde A→B (lista de strings)
      - data_b: mensajes desde B→A (lista de strings)
    """
    if data_a is None:
        data_a = ["a", "b", "c", "d", "e", "f"]
    if data_b is None:
        data_b = ["r1", "r2", "r3"]
    GoBackNBidiProtocol(window_size, data_a, data_b).start()
