
from events import Packet, Frame, fmt_frame, EventType, Event, sleep_step

class SlidingWindowProtocol:
    """Sliding window bidireccional."""
    def __init__(self, a_messages, b_messages):
        self.a_msgs = [Packet(str(x)) for x in a_messages]
        self.b_msgs = [Packet(str(x)) for x in b_messages]
        self.a_seq = 0
        self.b_seq = 0
        self.medium = []  # frames en tránsito
        self.a_outstanding = None
        self.b_outstanding = None
        self.a_delivered = []
        self.b_delivered = []

    def _send_from_a(self):
        if self.a_outstanding is None and self.a_msgs:
            p = self.a_msgs.pop(0)
            f = Frame("data", self.a_seq, self.b_seq, p)
            self.a_outstanding = f
            self.medium.append(("A->B", f))
            print("A → medio:", fmt_frame(f))
            sleep_step()

    def _send_from_b(self):
        if self.b_outstanding is None and self.b_msgs:
            p = self.b_msgs.pop(0)
            f = Frame("data", self.b_seq, self.a_seq, p)
            self.b_outstanding = f
            self.medium.append(("B->A", f))
            print("B → medio:", fmt_frame(f))
            sleep_step()

    def _process_medium(self):
        if not self.medium:
            return
        direction, f = self.medium.pop(0)
        ev = Event.wait_for_event_static([EventType.FRAME_ARRIVAL, EventType.CKSUM_ERR, EventType.TIMEOUT])
        if ev.event_type != EventType.FRAME_ARRIVAL:
            print(f"× {direction} perdió {fmt_frame(f)} ({ev.event_type}). Retransmisión en el próximo turno.")
            # Poner de vuelta para retransmisión
            if direction == "A->B":
                self.a_msgs.insert(0, f.packet)
                self.a_outstanding = None
            else:
                self.b_msgs.insert(0, f.packet)
                self.b_outstanding = None
            sleep_step()
            return

        # Llegó al frame
        if direction == "A->B":
            self.a_seq = 1 - self.a_seq
            self.a_delivered.append(f.packet.data)
            self.a_outstanding = None
            print("medio → B:", fmt_frame(f))
        else:
            self.b_seq = 1 - self.b_seq
            self.b_delivered.append(f.packet.data)
            self.b_outstanding = None
            print("medio → A:", fmt_frame(f))
        sleep_step()

    def start(self):
        print("\n=== SLIDING WINDOW 1-bit (bidireccional) ===")
        steps = 0
        while (self.a_msgs or self.b_msgs or self.a_outstanding or self.b_outstanding) and steps < 200:
            self._send_from_a()
            self._send_from_b()
            self._process_medium()
            steps += 1
        print(" Entregado en B:", self.a_delivered)
        print(" Entregado en A:", self.b_delivered)

def test(a_messages=None, b_messages=None):
    if a_messages is None:
        a_messages = ["H1", "H2", "H3"]
    if b_messages is None:
        b_messages = ["R1", "R2"]
    SlidingWindowProtocol(a_messages, b_messages).start()
