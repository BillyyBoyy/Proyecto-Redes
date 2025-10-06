import os
import sys

# Forzar stdout/stderr a UTF-8 para evitar UnicodeEncodeError en Windows 
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")  
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

# Intento de importar la configuración desde events.py 
# Si no existe o no exporta las funciones, se usa un fallback en memoria.
try:
    from events import set_setting, get_setting  
except Exception:
    _SETTINGS = {"error_rate": 0.0, "timeout_prob": 0.0, "step_delay": 0.25,
                 "paused": False, "stop_requested": False}

    def get_setting(key: str):
        return _SETTINGS.get(key, (False if key in ("paused", "stop_requested") else 0.0))

    def set_setting(key: str, value):
        _SETTINGS[key] = value

# Import de pruebas de protocolos 
from Protocols.protocol_utopia import test as test_utopia
from Protocols.protocol_stop_and_wait import test as test_snw
from Protocols.protocol_par import test as test_par
from Protocols.protocol_sliding_window import test as test_sw
from Protocols.protocol_go_back_n import test as test_gbn
from Protocols.protocol_selective_repeat import test as test_sr


def clear():
    try:
        os.system("cls" if os.name == "nt" else "clear")
    except Exception:
        print("\n" + "-" * 50 + "\n")


ASCII = r"""
    ╔══════════════════════════════════════════════════════════╗
    ║                  SIMULADOR DE PROTOCOLOS                 ║
    ╚══════════════════════════════════════════════════════════╝
      A (Emisor)                            B (Receptor)
      ┌──────────┐                       ┌──────────┐
      │          │  ========> DATA =====>│          │
      │   A      │  <=======  ACK  ===== │    B     │
      │          │                       │          │
      └──────────┘                       └──────────┘
"""

# Fallback si la consola no soporta Unicode
ASCII_FALLBACK = r"""
+============================================================+
|                  SIMULADOR DE PROTOCOLOS                   |
+============================================================+
  A (Emisor)                            B (Receptor)
  [ A ]  ========> DATA =====> [ B ]
         <=======  ACK  =====
"""


def show_header():
    clear()
    # Intentar imprimir el ASCII Unicode; si falla, usar el fallback ASCII
    try:
        print(ASCII)
    except UnicodeEncodeError:
        print(ASCII_FALLBACK)

    print(
        "[ Config ]  error_rate={:.2f}  timeout_prob={:.2f}  step_delay={:.2f}s".format(
            float(get_setting("error_rate") or 0.0),
            float(get_setting("timeout_prob") or 0.0),
            float(get_setting("step_delay") or 0.0),
        )
    )
    print()


def _parse_list(raw: str) -> list[str]:
    """Convierte 'a,b,c' -> ['a','b','c'] sin vacíos."""
    return [x.strip() for x in raw.split(",") if x.strip()]


def set_config():
    show_header()
    try:
        er_str = input(
            "Probabilidad de error/pérdida (0-1) [actual {:.2f}]: ".format(
                float(get_setting("error_rate") or 0.0)
            )
        ).strip()
        to_str = input(
            "Probabilidad de timeout (0-1)     [actual {:.2f}]: ".format(
                float(get_setting("timeout_prob") or 0.0)
            )
        ).strip()
        sd_str = input(
            "Velocidad (segundos por paso)     [actual {:.2f}]: ".format(
                float(get_setting("step_delay") or 0.0)
            )
        ).strip()

        er = float(er_str) if er_str else float(get_setting("error_rate") or 0.0)
        to = float(to_str) if to_str else float(get_setting("timeout_prob") or 0.0)
        sd = float(sd_str) if sd_str else float(get_setting("step_delay") or 0.0)

        set_setting("error_rate", max(0.0, min(1.0, er)))
        set_setting("timeout_prob", max(0.0, min(1.0, to)))
        set_setting("step_delay", max(0.0, sd))
        
        # Resetear estados de control de ejecución
        set_setting("paused", False)
        set_setting("stop_requested", False)
        
    except Exception:
        print("Valores inválidos, se mantienen los actuales.")
    input("\nEnter para continuar…")


def main_menu():
    while True:
        show_header()
        print("1) Utopía (ideal)")
        print("2) Stop-and-Wait (simple)")
        print("3) PAR (con retransmisión)")
        print("4) Sliding Window 1-bit (bidireccional)")
        print("5) Go-Back-N")
        print("6) Selective-Repeat")
        print("7) Configuración")
        print("0) Salir")
        op = input("\nSeleccione una opción: ").strip()

        if op == "1":
            show_header()
            data = input("Datos (coma) default: a,b,c: ").strip() or "a,b,c"
            test_utopia(_parse_list(data))
            input("\nEnter para volver al menú…")

        elif op == "2":
            show_header()
            data = input("Datos (coma) default: 1,2,3: ").strip() or "1,2,3"
            test_snw(_parse_list(data))
            input("\nEnter para volver al menú…")

        elif op == "3":
            show_header()
            data = input("Datos (coma) default: H,O,L,A: ").strip() or "H,O,L,A"
            test_par(_parse_list(data))
            input("\nEnter para volver al menú…")

        elif op == "4":
            show_header()
            a = input("Mensajes de A (coma) default: H1,H2,H3: ").strip() or "H1,H2,H3"
            b = input("Mensajes de B (coma) default: R1,R2: ").strip() or "R1,R2"
            test_sw(_parse_list(a), _parse_list(b))
            input("\nEnter para volver al menú…")

        elif op == "5":
            show_header()
            data = input("Datos (coma) default: a,b,c,d,e,f: ").strip() or "a,b,c,d,e,f"
            try:
                w = int(input("Tamaño de ventana (w) default: 3: ").strip() or "3")
            except Exception:
                w = 3
            test_gbn(w, _parse_list(data))
            input("\nEnter para volver al menú…")

        elif op == "6":
            show_header()
            data = input("Datos (coma) default: a,b,c,d,e,f: ").strip() or "a,b,c,d,e,f"
            try:
                w = int(input("Tamaño de ventana (w) default: 3: ").strip() or "3")
            except Exception:
                w = 3
            test_sr(w, _parse_list(data))
            input("\nEnter para volver al menú…")

        elif op == "7":
            set_config()

        elif op == "0":
            print("¡Listo!")
            return

        else:
            input("Opción inválida. Enter para intentar de nuevo…")


if __name__ == "__main__":
    main_menu()