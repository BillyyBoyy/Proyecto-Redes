import random
import time
from dataclasses import dataclass
from typing import Optional, List

# ==============================================================
#  Configuración global de la simulación
#  (estos valores los ajusta el menú / usuario en tiempo de ejecución)
# ==============================================================

SETTINGS = {
    # Probabilidad de que un frame DATA se corrompa o “se pierda” (0.0 a 1.0)
    "error_rate": 0.0,
    # Probabilidad de timeout cuando se espera un ACK (0.0 a 1.0)
    "timeout_prob": 0.10,
    # Pausa entre pasos para “animar” la consola (en segundos)
    "step_delay": 0.5,
    # Estados de control de ejecución (añadidos para la GUI)
    "paused": False,
    "stop_requested": False,
}

def set_setting(key: str, value):
    """
    Actualiza una clave existente en SETTINGS.
    Si la clave no existe, la crea (necesario para paused/stop_requested).
    """
    SETTINGS[key] = value

def get_setting(key: str):
    """
    Devuelve el valor de SETTINGS[key] o None si la clave no existe.
    """
    return SETTINGS.get(key)


# ==============================================================
#  Tipos de evento (estados que pueden ocurrir en el canal)
# ==============================================================

class EventType:
    """
    Enumeración simple de tipos de eventos usados en la simulación.
    """
    FRAME_ARRIVAL = "frame_arrival"          # Llegada correcta de un frame
    CKSUM_ERR = "cksum_err"                  # Error de checksum (frame corrupto)
    TIMEOUT = "timeout"                      # Timeout esperando ACK/delivery
    ACK_TIMEOUT = "ack_timeout"              # (Reservado) Timeout específico de ACK
    NETWORK_LAYER_READY = "network_layer_ready"  # (Reservado) Capa de red lista


# ==============================================================
#  Modelo de evento (compatible con el uso original del proyecto)
# ==============================================================

class Event:
    """
    Representa un evento que ocurre en el sistema (ej. llegada de frame).
    La clase también expone un generador pseudoaleatorio de eventos
    con sesgo según SETTINGS (error_rate, timeout_prob).
    """

    def __init__(self, event_type: str):
        self.event_type = event_type

    def generate_event(self, event_type: str) -> "Event":
        """
        Mantiene compatibilidad con llamadas antiguas del proyecto.
        Simplemente crea y devuelve un Event del tipo solicitado.
        """
        return Event(event_type)

    def wait_for_event(self, event_types: List[str]) -> "Event":
        """
        Envoltura (wrapper) retrocompatible que delega en la versión estática,
        usando SETTINGS globales para la probabilidad de error/timeout.
        """
        return Event.wait_for_event_static(event_types)

    @staticmethod
    def wait_for_event_static(
        event_types: List[str],
        error_rate: Optional[float] = None,
        timeout_prob: Optional[float] = None
    ) -> "Event":
        """
        Dado un conjunto de tipos de eventos posibles (event_types), devuelve
        uno de ellos, eligiéndolo aleatoriamente pero sesgado por:
          - error_rate  → prob. de CKSUM_ERR
          - timeout_prob → prob. de TIMEOUT
        El resto de la masa de probabilidad se asigna a FRAME_ARRIVAL si está
        entre los event_types. Si no lo está, se normaliza el vector de probs.

        Importante:
        - Si event_types contiene un único elemento, se retorna ese tal cual.
        - Se respetan los límites [0, 1] para error_rate y timeout_prob.
        """
        # Si no se pasan explícitos, usamos los globales.
        if error_rate is None:
            error_rate = SETTINGS["error_rate"]
        if timeout_prob is None:
            timeout_prob = SETTINGS["timeout_prob"]

        # Caso trivial: solo un tipo de evento posible → retorna ese.
        if len(event_types) == 1:
            return Event(event_types[0])

        # Construimos un vector de probabilidades alineado a event_types.
        # Al inicio, asignamos 0 a todo lo que no sea error/timeout.
        probs: List[float] = []
        for et in event_types:
            if et == EventType.CKSUM_ERR:
                # “max(0.0, …)” por si alguien pone un valor negativo por error.
                probs.append(max(0.0, error_rate))
            elif et == EventType.TIMEOUT:
                probs.append(max(0.0, timeout_prob))
            else:
                # Para FRAME_ARRIVAL (u otros), de momento 0; luego repartimos.
                probs.append(0.0)

        # Si está FRAME_ARRIVAL, le damos toda la probabilidad restante.
        # Si no está, normalizamos lo que tengamos para que sume 1.
        if EventType.FRAME_ARRIVAL in event_types:
            remaining = max(0.0, 1.0 - sum(probs))
            idx = event_types.index(EventType.FRAME_ARRIVAL)
            probs[idx] = probs[idx] + remaining
        else:
            total = sum(probs) or 1.0  # evitas división entre 0
            probs = [p / total for p in probs]

        # Muestreo por distribución acumulada (técnica clásica):
        r = random.random()  # número en [0, 1)
        cumulative = 0.0
        chosen = event_types[-1]  # valor “por defecto” si nada hace match
        for et, p in zip(event_types, probs):
            cumulative += p
            if r <= cumulative:
                chosen = et
                break

        return Event(chosen)


# ==============================================================
#  Modelos de datos: Packet y Frame
# ==============================================================

@dataclass
class Packet:
    """
    Representa los datos “útiles” que viajan dentro de un frame.
    """
    data: str

@dataclass
class Frame:
    """
    Representa una unidad de transmisión en la capa de enlace.
      - frame_type: "data" o "ack"
      - sequence_number: número de secuencia del frame
      - acknowledgment_number: último ACK conocido/puesto
      - packet: payload (solo para DATA), puede ser None en ACK
    """
    frame_type: str                      # "data" o "ack"
    sequence_number: int
    acknowledgment_number: int
    packet: Optional[Packet] = None


# ==============================================================
#  Helpers “bonitos” para imprimir y animar en la TUI/CLI
# ==============================================================

def fmt_frame(frame: Frame) -> str:
    """
    Devuelve una descripción compacta en una sola línea de un frame.
    Está pensada para logs/prints en consola.
    - Para ACK:   [ACK a=NUM]
    - Para DATA:  [DATA s=NUM a=NUM data='...']
    """
    if frame.frame_type == "ack":
        return f"[ACK a={frame.acknowledgment_number}]"
    payload = "" if frame.packet is None else f" data={frame.packet.data!r}"
    return f"[DATA s={frame.sequence_number} a={frame.acknowledgment_number}{payload}]"

def sleep_step(mult: float = 1.0):
    """
    Pausa la ejecución un momento para “animar” la simulación.
    El tiempo es SETTINGS['step_delay'] * mult, pero nunca negativo.
    Esta versión incluye soporte para pausa y stop desde la GUI.
    """
    # Stop inmediato
    if bool(get_setting("stop_requested")):
        raise KeyboardInterrupt("Stop solicitado por el usuario.")
    
    # dt por defecto: step_delay global
    dt = max(0.0, float(get_setting("step_delay") or 0.0) * mult)
    
    # Esperar mientras esté pausado
    while bool(get_setting("paused")) and not bool(get_setting("stop_requested")):
        time.sleep(0.05)
    
    # Espera fraccionada (para re-chequear flags)
    end = time.time() + dt
    while time.time() < end:
        if bool(get_setting("stop_requested")):
            raise KeyboardInterrupt("Stop solicitado por el usuario.")
        while bool(get_setting("paused")) and not bool(get_setting("stop_requested")):
            time.sleep(0.05)
        time.sleep(0.02)