"""Relógios: Lamport (lógico), físico simulado e cálculo do algoritmo de Berkeley."""
import threading
import time


class LamportClock:
    """Relógio lógico de Lamport, seguro para várias threads."""

    def __init__(self):
        self._t = 0
        self._lock = threading.Lock()

    @property
    def time(self):
        with self._lock:
            return self._t

    def tick(self):
        """Evento local ou de envio: L = L + 1. Retorna o novo valor."""
        with self._lock:
            self._t += 1
            return self._t

    def update(self, received):
        """Recepção: L = max(L, L_msg) + 1."""
        with self._lock:
            self._t = max(self._t, received) + 1
            return self._t


class PhysicalClock:
    """Relógio físico com defasagem (skew) configurável, para demonstrar o Berkeley."""

    def __init__(self, skew=0.0, time_fn=time.time):
        self._time_fn = time_fn
        self.offset = skew
        self._lock = threading.Lock()

    def now(self):
        with self._lock:
            return self._time_fn() + self.offset

    def adjust(self, delta):
        with self._lock:
            self.offset += delta


def berkeley_adjustments(diffs, threshold=None):
    """Algoritmo de Berkeley sobre diferenças em relação ao líder.

    diffs: {id: relógio_do_nó - relógio_do_líder} (o líder entra com 0.0).
    threshold: diferenças com |d| > threshold são ignoradas na média (outliers),
               mas o nó ainda recebe o ajuste para chegar na média.
    Retorna (média_das_diferenças, {id: ajuste_a_aplicar}).
    """
    valid = [d for d in diffs.values() if threshold is None or abs(d) <= threshold]
    if not valid:
        raise ValueError("nenhum relógio dentro do limite")
    avg = sum(valid) / len(valid)
    return avg, {pid: avg - d for pid, d in diffs.items()}
