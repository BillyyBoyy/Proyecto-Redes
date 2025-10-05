from events import Packet, Frame, fmt_frame, EventType, Event, sleep_step

class UtopiaProtocol:
    """
    Canal ideal unidireccional (Utopía):
    - No hay pérdidas ni errores.
    - Cada frame que sale de A llega siempre a B.
    - El objetivo es mostrar el “pipeline” A -> medio -> B de forma clara.
    """

    def __init__(self, data):
        """
        data: iterable con los “datos” (payloads) a enviar.
        """
        # Cola de salida en A (capa de red de A convertida a frames DATA)
        self.source_network = self._load_frames(data)
        # “Medio” o canal por donde transitan los frames
        self.medium = []
        # Cola de llegada en B (lo recibido en B)
        self.dest_network = []

        # Métricas internas (control de ciclo)
        self.total = len(self.source_network)   # total a entregar
        self.delivered = 0                      # entregados en B

    # ------------------------ UI helpers (solo impresión) ------------------------

    def _ui_header(self):
        """Encabezado visual de la simulación (solo estética)."""
        print("\n" + "═" * 62)
        print("  U T O P Í A   –   Canal ideal unidireccional (sin errores)")
        print("═" * 62)
        print("  A (Emisor)           MEDIO              B (Receptor)")
        print("  ──────────     ───────────────     ───────────────")
        print()

    def _ui_divider(self):
        """Separador visual entre pasos para mejor lectura."""
        print("-" * 62)

    # ------------------------ Lógica (sin cambios de comportamiento) ------------------------

    def _load_frames(self, data):
        """
        Transforma cada ítem de 'data' en un Frame de tipo DATA.
        - sequence_number: índice del dato
        - acknowledgment_number: 0 (no se usa en Utopía)
        - packet: Packet con str(d)
        """
        frames = []
        for i, d in enumerate(data):
            frames.append(Frame("data", i, 0, Packet(str(d))))
        return frames

    def _send(self):
        """
        Saca el siguiente frame de la cola de A y lo pone en el medio.
        (No hay fallos: lo que se envía, eventualmente se recibirá.)
        """
        f = self.source_network.pop(0)
        self.medium.append(f)

        # Línea original (conservada para compatibilidad con logs/pruebas)
        print("A → medio:", fmt_frame(f))

        # Pausa de “animación” (no altera la lógica)
        sleep_step()

    def _receive(self):
        """
        Toma el frame del medio y lo entrega a la cola de B.
        Incrementa el contador 'delivered'.
        """
        f = self.medium.pop(0)
        self.dest_network.append(f)

        # Línea original (conservada para compatibilidad con logs/pruebas)
        print("medio → B:", fmt_frame(f))

        # Pausa de “animación”
        sleep_step()

        # Actualiza métrica
        self.delivered += 1

    def start(self):
        """
        Ejecuta el ciclo completo:
          mientras falten entregas: enviar desde A y luego recibir en B.
        (En Utopía, cada send va seguido por su receive 1:1.)
        """
        self._ui_header()
        while self.delivered < self.total:
            self._send()
            self._receive()

        # Resumen final (misma info de antes, solo con un marco más claro)
        self._ui_divider()
        print("✔ Entrega completa en B:",
              [fr.packet.data for fr in self.dest_network])
        print("═" * 62)

def test(data=None):
    """
    Función de prueba/ejemplo: mantiene la misma firma y comportamiento.
    """
    if data is None:
        data = ["a", "b", "c"]
    UtopiaProtocol(data).start()
