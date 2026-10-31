import threading

import pytest

from distga.clocks import LamportClock, PhysicalClock, berkeley_adjustments


def test_lamport_tick_incrementa():
    c = LamportClock()
    assert c.time == 0
    assert c.tick() == 1
    assert c.tick() == 2


def test_lamport_update_usa_maximo_mais_um():
    c = LamportClock()
    c.tick()                      # L = 1
    assert c.update(10) == 11     # max(1, 10) + 1
    assert c.update(3) == 12      # max(11, 3) + 1


def test_lamport_cadeia_causal_exercicio_5():
    # A envia com 10 -> B recebe (11) -> B envia (12) -> C recebe (13)
    b, c = LamportClock(), LamportClock()
    assert b.update(10) == 11
    assert b.tick() == 12
    assert c.update(12) == 13


def test_lamport_thread_safe():
    c = LamportClock()
    threads = [threading.Thread(target=lambda: [c.tick() for _ in range(500)]) for _ in range(8)]
    [t.start() for t in threads]
    [t.join() for t in threads]
    assert c.time == 4000


def test_physical_clock_skew_e_ajuste():
    pc = PhysicalClock(skew=5.0, time_fn=lambda: 100.0)
    assert pc.now() == 105.0
    pc.adjust(-2.5)
    assert pc.now() == 102.5


def test_berkeley_exemplo_do_exercicio_7f():
    # Líder P4 (10:00:30). Diferenças: P1 -30, P2 -45, P3 +40, P4 0.
    avg, adj = berkeley_adjustments({1: -30, 2: -45, 3: 40, 4: 0})
    assert avg == pytest.approx(-8.75)
    assert adj == pytest.approx({1: 21.25, 2: 36.25, 3: -48.75, 4: -8.75})


def test_berkeley_todos_convergem_para_mesma_hora():
    diffs = {1: -30, 2: -45, 3: 40, 4: 0}
    _, adj = berkeley_adjustments(diffs)
    finais = {pid: diffs[pid] + adj[pid] for pid in diffs}
    assert len(set(round(v, 9) for v in finais.values())) == 1


def test_berkeley_descarta_outlier_da_media():
    avg, adj = berkeley_adjustments({1: 0, 2: 2, 3: 4, 4: 1000}, threshold=10)
    assert avg == pytest.approx(2.0)
    assert adj[4] == pytest.approx(2.0 - 1000)   # o outlier também é corrigido


def test_berkeley_sem_relogios_validos():
    with pytest.raises(ValueError):
        berkeley_adjustments({1: 100, 2: 200}, threshold=1)
