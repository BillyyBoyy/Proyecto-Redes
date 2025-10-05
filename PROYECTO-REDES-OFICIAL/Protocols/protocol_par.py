
from events import Packet, Frame, fmt_frame, EventType, Event, get_setting, sleep_step

class PARProtocol:
    def __init__(self, data, max_seq=1):
        self.queue = [Frame("data", i % (max_seq+1), 0, Packet(str(d))) for i, d in enumerate(data)]
        self.medium = []
        self.dest = []
        self.max_seq = max_seq

    def _send_next(self):
        if not self.queue:
            return None
        f = self.queue[0]  # peek
        print("A → medio:", fmt_frame(f))
        self.medium.append(f)
        sleep_step()
        return f

    def _wait_event(self):
        # Either the frame arrives OK, or there is an error/timeout
        return Event.wait_for_event_static([EventType.FRAME_ARRIVAL, EventType.CKSUM_ERR, EventType.TIMEOUT])

    def _deliver_or_retransmit(self, f):
        ev = self._wait_event()
        if ev.event_type == EventType.FRAME_ARRIVAL:
            # delivered to B and ACK simulated as success -> dequeue
            got = self.medium.pop(0)
            self.dest.append(got)
            print("medio → B:", fmt_frame(got), "  (ACK recibido)")
            sleep_step()
            # remove from queue
            self.queue.pop(0)
            return True
        else:
            # error or timeout: retransmit same frame
            if self.medium:
                self.medium.pop(0)
            print(f"× Evento: {ev.event_type}. Reintentando…")
            sleep_step()
            return False

    def start(self):
        print("\n=== PAR (con pérdidas/timeout) ===")
        steps = 0
        while self.queue and steps < 1000:  # safe-guard
            f = self._send_next()
            if f is None:
                break
            ok = self._deliver_or_retransmit(f)
            steps += 1

        print("✔ Entrega en B:", [fr.packet.data for fr in self.dest])

def test(data=None):
    if data is None:
        data = ["H", "O", "L", "A"]
    PARProtocol(data).start()
