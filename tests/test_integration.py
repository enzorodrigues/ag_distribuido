"""Testes de integração: nós reais (gRPC em localhost) dentro do mesmo processo."""
import json
import socket
import threading
import time
import urllib.error
import urllib.request

import pytest

from distga.node import Node
from distga.tsp import make_cities


def free_ports(n):
    socks = [socket.socket() for _ in range(n)]
    for s in socks:
        s.bind(("127.0.0.1", 0))
    ports = [s.getsockname()[1] for s in socks]
    for s in socks:
        s.close()
    return ports


def wait_for(cond, timeout=8.0):
    end = time.time() + timeout
    while time.time() < end:
        if cond():
            return True
        time.sleep(0.05)
    return False


@pytest.fixture
def cluster():
    created = []

    def make(ids, skews=None, start=True, **kw):
        ports = free_ports(len(ids))
        peers = {i: f"localhost:{p}" for i, p in zip(ids, ports)}
        params = dict(generations=0, migration_interval=10**9, hb_interval=0.2,
                      rpc_timeout=0.5, startup_delay=0.3, election_timeout=1.5,
                      pop_size=20, quiet=True, berkeley_interval=10**6)
        params.update(kw)
        nodes = {i: Node(i, peers, make_cities(15, 1), skew=(skews or {}).get(i, 0.0), seed=1,
                         **params) for i in ids}
        created.extend(nodes.values())
        if start:
            start_all(nodes.values())
        return nodes

    def start_all(nodes):
        ts = [threading.Thread(target=n.start) for n in nodes]
        [t.start() for t in ts]
        [t.join() for t in ts]

    make.start_all = start_all
    yield make
    for n in created:
        n.stop()


def http(url, method="GET"):
    req = urllib.request.Request(url, method=method, data=b"" if method == "POST" else None)
    try:
        with urllib.request.urlopen(req, timeout=3) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read())


def test_eleicao_inicial_escolhe_maior_id(cluster):
    nodes = cluster([1, 2, 3])
    assert wait_for(lambda: all(n.leader == 3 for n in nodes.values()))


def test_reeleicao_apos_queda_do_lider(cluster):
    nodes = cluster([1, 2, 3])
    assert wait_for(lambda: all(n.leader == 3 for n in nodes.values()))
    nodes[3].stop()
    assert wait_for(lambda: nodes[1].leader == 2 and nodes[2].leader == 2)


def test_no_maior_que_entra_depois_assume_lideranca(cluster):
    nodes = cluster([1, 2, 3], start=False)
    cluster.start_all([nodes[1], nodes[2]])
    assert wait_for(lambda: nodes[1].leader == 2 and nodes[2].leader == 2)
    nodes[3].start()
    assert wait_for(lambda: all(n.leader == 3 for n in nodes.values()))


def test_migracao_em_anel_e_lamport(cluster):
    nodes = cluster([1, 2, 3])
    assert wait_for(lambda: all(n.leader == 3 for n in nodes.values()))
    before = nodes[1].clock.time
    assert nodes[1].migrate() == 2                       # próximo do anel
    assert wait_for(lambda: nodes[2].island.migrants_received > 0)
    assert nodes[2].clock.time > before                  # causalidade (Lamport)
    assert nodes[1].clock.time > before                  # ack também atualiza o remetente
    assert nodes[3].migrate() == 1                       # o anel fecha: 3 -> 1


def test_migracao_pula_no_morto(cluster):
    nodes = cluster([1, 2, 3])
    assert wait_for(lambda: all(n.leader == 3 for n in nodes.values()))
    nodes[2].stop()
    assert nodes[1].migrate() == 3


def test_migracao_automatica_durante_evolucao(cluster):
    nodes = cluster([1, 2], generations=60, migration_interval=10)
    assert wait_for(lambda: all(n.finished for n in nodes.values()), 20)
    assert all(n.island.migrants_received > 0 for n in nodes.values())


def test_berkeley_sincroniza_relogios(cluster):
    nodes = cluster([1, 2, 3], skews={1: 0.0, 2: 10.0, 3: -4.0})
    assert wait_for(lambda: all(n.leader == 3 for n in nodes.values()))
    avg, _ = nodes[3].run_berkeley()
    # a média é relativa ao líder (skew -4): diffs {1: +4, 2: +14, 3: 0} -> +6
    assert avg == pytest.approx(6.0, abs=0.05)
    # offset absoluto final = -4 + 6 = 2 = média dos skews (0, 10, -4)
    assert wait_for(lambda: all(abs(n.physical.offset - 2.0) < 0.05 for n in nodes.values()))


def test_berkeley_ignora_outlier_na_media(cluster):
    nodes = cluster([1, 2, 3], skews={1: 0.0, 2: 2.0, 3: 1000.0}, berkeley_threshold=10.0)
    assert wait_for(lambda: all(n.leader == 3 for n in nodes.values()))
    # o líder (3) tem relógio 1000; diffs relativos: 1: -1000, 2: -998, 3: 0 -> só o líder é válido
    avg, adj = nodes[3].run_berkeley()
    assert avg == pytest.approx(0.0, abs=0.05)


def test_rest_status_best_e_berkeley(cluster):
    nodes = cluster([1, 2, 3], rest_port=0, skews={1: 3.0, 2: -3.0})
    assert wait_for(lambda: all(n.leader == 3 for n in nodes.values()))
    base = {i: f"http://localhost:{n.rest_port}" for i, n in nodes.items()}

    code, st = http(base[1] + "/status")
    assert code == 200 and st["node"] == 1 and st["leader"] == 3

    code, body = http(base[1] + "/best")                  # nó 1 não é líder
    assert code == 409 and body["leader"] == 3

    code, best = http(base[3] + "/best")                  # líder agrega o melhor global
    assert code == 200 and len(best["nodes"]) == 3
    assert best["best_length"] == min(n["length"] for n in best["nodes"])
    assert sorted(best["best_tour"]) == list(range(15))

    code, bk = http(base[3] + "/berkeley", "POST")
    assert code == 200 and set(bk["adjustments"]) == {"1", "2", "3"}

    assert http(base[3] + "/inexistente")[0] == 404


def test_ping_informa_lider_e_lamport(cluster):
    nodes = cluster([1, 2])
    assert wait_for(lambda: all(n.leader == 2 for n in nodes.values()))
    r = nodes[1]._ping(2)
    assert r.leader_id == 2 and r.responder_id == 2 and r.lamport > 0
