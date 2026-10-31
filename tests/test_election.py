import threading
import time

from distga.election import BullyElection


class FakeCluster:
    """Rede simulada: nós vivos respondem OK e processam mensagens; mortos não respondem."""

    def __init__(self, ids, dead=(), wait_timeout=2.0):
        self.alive = set(ids) - set(dead)
        self.calls = []        # (origem, destino, tipo)
        self.nodes = {}
        for i in ids:
            self.nodes[i] = BullyElection(
                i, [p for p in ids if p != i],
                send_election=lambda to, i=i: self._election(i, to),
                send_coordinator=lambda to, i=i: self._coord(i, to),
                wait_timeout=wait_timeout)

    def _election(self, src, dst):
        self.calls.append((src, dst, "ELEICAO"))
        if dst not in self.alive:
            return False
        self.nodes[dst].handle_election(src)
        return True

    def _coord(self, src, dst):
        self.calls.append((src, dst, "COORD"))
        if dst in self.alive:
            self.nodes[dst].handle_coordinator(src)


def wait_for(cond, timeout=3.0):
    end = time.time() + timeout
    while time.time() < end:
        if cond():
            return True
        time.sleep(0.02)
    return False


def test_maior_id_vivo_vence_exercicio_7b():
    # P5 falhou; P2 detecta e inicia a eleição -> P4 deve vencer.
    c = FakeCluster([1, 2, 3, 4, 5], dead=[5])
    assert c.nodes[2].start() == 4
    assert wait_for(lambda: all(c.nodes[i].leader == 4 for i in (1, 2, 3, 4)))


def test_todos_vivos_vence_o_maior():
    c = FakeCluster([1, 2, 3, 4, 5])
    c.nodes[1].start()
    assert wait_for(lambda: all(n.leader == 5 for n in c.nodes.values()))


def test_maior_id_nao_envia_eleicao_e_anuncia():
    c = FakeCluster([1, 2, 3])
    assert c.nodes[3].start() == 3
    assert not [x for x in c.calls if x[2] == "ELEICAO"]
    assert {(s, d) for s, d, t in c.calls if t == "COORD"} == {(3, 1), (3, 2)}
    assert c.nodes[1].leader == c.nodes[2].leader == 3


def test_todos_os_maiores_mortos_assume_lideranca():
    c = FakeCluster([1, 2, 3, 4], dead=[3, 4])
    assert c.nodes[1].start() == 2
    assert wait_for(lambda: c.nodes[2].leader == 2)


def test_unico_no_vivo_vira_lider():
    c = FakeCluster([1, 2, 3], dead=[2, 3])
    assert c.nodes[1].start() == 1


def test_eleicoes_simultaneas_convergem_exercicio_7e():
    c = FakeCluster([1, 2, 3, 4, 5], dead=[5])
    ts = [threading.Thread(target=c.nodes[i].start) for i in (2, 3)]
    [t.start() for t in ts]
    [t.join() for t in ts]
    assert wait_for(lambda: all(c.nodes[i].leader == 4 for i in (1, 2, 3, 4)))


def test_ok_sem_coordenador_assume_apos_rodadas():
    # Nó 2 recebe OK do 3, mas 3 "morre" antes de anunciar: 2 acaba assumindo.
    ids = [1, 2, 3]
    sent = []
    e = BullyElection(2, [1, 3], send_election=lambda p: p == 3,
                      send_coordinator=lambda p: sent.append(p),
                      wait_timeout=0.05, max_rounds=2)
    assert e.start() == 2
    assert sorted(sent) == [1, 3]


def test_handle_election_de_id_menor_dispara_eleicao_propria():
    c = FakeCluster([1, 2, 3], dead=[3])
    c.nodes[2].handle_election(1)
    assert wait_for(lambda: c.nodes[2].leader == 2)


def test_handle_election_de_id_maior_nao_dispara():
    c = FakeCluster([1, 2, 3])
    assert c.nodes[1].handle_election(3) is True
    time.sleep(0.1)
    assert not c.calls
