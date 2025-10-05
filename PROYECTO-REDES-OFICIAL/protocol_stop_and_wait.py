
from events import Packet, Frame, fmt_frame, EventType, Event, sleep_step

class StopAndWaitProtocol:
    def __init__(self, data):
        self.source_network = self._load_frames(data)
        self.medium = []
        self.dest_network = []
        self.awaiting = False  # waiting for delivery confirmation (simulated immediate in this model)

    def _load_frames(self, data):
        return [Frame("data", i, 0, Packet(str(d))) for i, d in enumerate(data)]

    def start(self):
        print("\n=== STOP & WAIT (sin errores) ===")
        while self.source_network or self.medium:
            if not self.awaiting and self.source_network:
                f = self.source_network.pop(0)
                self.medium.append(f)
                self.awaiting = True
                print("A → medio:", fmt_frame(f))
                sleep_step()

            if self.medium:
                f = self.medium.pop(0)
                self.dest_network.append(f)
                print("medio → B:", fmt_frame(f))
                sleep_step()
                self.awaiting = False

        print("✔ Entrega completa en B:", [fr.packet.data for fr in self.dest_network])

def test(data=None):
    if data is None:
        data = [1, 2, 3]
    StopAndWaitProtocol(data).start()
