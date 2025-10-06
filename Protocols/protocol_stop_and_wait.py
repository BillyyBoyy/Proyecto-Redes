
from events import Packet, Frame, fmt_frame, sleep_step

class StopAndWaitProtocol:
    """
    Protocolo Stop-and-Wait (canal sin errores):
    - A envía un DATA (frame_type="data") con sequence_number s.
    - B, al recibirlo, lo entrega a su "capa de red" y responde con un ACK
      (frame_type="ack") donde acknowledgment_number = s.
    - A solo envía el siguiente DATA cuando llega el ACK esperado.
    - Se imprime A→medio, medio→B, B→medio, medio→A para animación en la GUI.
    """

    def __init__(self, data):
        # "Capa de red" en A: empaquetar los datos en frames DATA con s=0..n-1 y a=0
        self.source_network = [
            Frame("data", i, 0, Packet(str(d))) for i, d in enumerate(data)
        ]

        # Medio físico en ambos sentidos (buffers de tránsito)
        self.medium_ab = []  # DATA A → medio → B
        self.medium_ba = []  # ACK  B → medio → A

        # "Capa de red" destino (B)
        self.dest_network = []

        # Estado del emisor A
        self.awaiting_ack = False          # A está esperando el ACK del último DATA
        self.last_sent_seq = None          # s del último DATA enviado

    def start(self):
        print("\n=== STOP & WAIT (con ACK explícito; sin errores) ===")

        # Continuar mientras haya por enviar, algo en tránsito o un ACK pendiente
        while self.source_network or self.medium_ab or self.medium_ba or self.awaiting_ack:

            # A emite DATA si no está esperando ACK y aún hay frames en su cola
            if not self.awaiting_ack and self.source_network:
                data_frame = self.source_network.pop(0)           # Frame("data", s, a=0, Packet(...))
                self.last_sent_seq = data_frame.sequence_number   # recordar s del DATA emitido
                self.medium_ab.append(data_frame)
                self.awaiting_ack = True

                print("A → medio:", fmt_frame(data_frame))
                sleep_step()

            # Tránsito del DATA A→B por el medio
            if self.medium_ab:
                f = self.medium_ab.pop(0)  # Llega a B
                print("medio → B:", fmt_frame(f))
                # Entrega a la "capa de red" de B
                self.dest_network.append(f)
                sleep_step()

                # B genera y envía ACK con acknowledgment_number = s recibido
                ack = Frame("ack", 0, f.sequence_number, None)    # payload None en ACK
                self.medium_ba.append(ack)

                print("B → medio:", fmt_frame(ack))
                sleep_step()

            # Tránsito del ACK B→A por el medio
            if self.medium_ba:
                ack = self.medium_ba.pop(0)  # Llega a A
                print("medio → A:", fmt_frame(ack))
                sleep_step()

                # A procesa el ACK; si coincide con el último s enviado, libera el siguiente DATA
                if self.awaiting_ack and ack.acknowledgment_number == self.last_sent_seq:
                    self.awaiting_ack = False
                    self.last_sent_seq = None

        # Resumen de entrega en B (payloads en orden)
        print(" Entrega completa en B:", [fr.packet.data for fr in self.dest_network])


def test(data=None):
    if data is None:
        data = [1, 2, 3]
    StopAndWaitProtocol(data).start()
