"""Nó do sistema: serviço gRPC, ilha do AG, eleição, Lamport, Berkeley e REST."""
import json
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import grpc

from distga import island_pb2 as pb
from distga import island_pb2_grpc as pbg
from distga.clocks import LamportClock, PhysicalClock, berkeley_adjustments
from distga.election import BullyElection
from distga.island import Island


class Node(pbg.IslandServiceServicer):
    def __init__(self, node_id, peers, cities, generations=500, migration_interval=20,
                 n_migrants=3, pop_size=100, skew=0.0, seed=None, rpc_timeout=1.0,
                 hb_interval=1.0, startup_delay=1.0, gen_delay=0.0,
                 berkeley_interval=10.0, berkeley_threshold=None,
                 election_timeout=3.0, rest_port=None, quiet=False):
        """peers: {id: 'host:porta'} de TODOS os nós, inclusive este."""
        self.id = node_id
        self.address = peers[node_id]
        self.peers = {p: a for p, a in peers.items() if p != node_id}
        self.generations = generations
        self.migration_interval = migration_interval
        self.n_migrants = n_migrants
        self.rpc_timeout = rpc_timeout
        self.hb_interval = hb_interval
        self.startup_delay = startup_delay
        self.gen_delay = gen_delay
        self.berkeley_interval = berkeley_interval
        self.berkeley_threshold = berkeley_threshold
        self.rest_port = rest_port
        self.quiet = quiet

        self.clock = LamportClock()
        self.physical = PhysicalClock(skew)
        self.island = Island(cities, pop_size=pop_size,
                             seed=None if seed is None else seed + node_id)
        self.election = BullyElection(self.id, list(self.peers), self._send_election,
                                      self._send_coordinator, wait_timeout=election_timeout)
        self.finished = False
        self.logs = []
        self.rest_server = None
        self._stubs = {}
        self._stop = threading.Event()
        self._server = None
        self._threads = []

    # ---------------------------------------------------------------- util
    def log(self, msg):
        line = f"[L={self.clock.time:>4}] [nó {self.id}] {msg}"
        self.logs.append(line)
        if not self.quiet:
            print(line, flush=True)

    def _stub(self, pid):
        if pid not in self._stubs:
            self._stubs[pid] = pbg.IslandServiceStub(grpc.insecure_channel(self.peers[pid]))
        return self._stubs[pid]

    @property
    def leader(self):
        return self.election.leader

    # ------------------------------------------------- handlers (servidor)
    def Migrate(self, req, ctx):
        self.clock.update(req.lamport)
        n = self.island.receive_migrants(req.migrants)
        self.log(f"recebeu {n} migrante(s) do nó {req.sender_id}")
        return pb.Ack(lamport=self.clock.tick(), ok=True)

    def Election(self, req, ctx):
        self.clock.update(req.lamport)
        self.log(f"ELEIÇÃO recebida de {req.sender_id} -> respondendo OK")
        self.election.handle_election(req.sender_id)
        return pb.ElectionReply(responder_id=self.id, lamport=self.clock.tick())

    def Coordinator(self, req, ctx):
        self.clock.update(req.lamport)
        self.election.handle_coordinator(req.leader_id)
        self.log(f"COORDENADOR: líder é o nó {req.leader_id}")
        return pb.Ack(lamport=self.clock.tick(), ok=True)

    def Ping(self, req, ctx):
        self.clock.update(req.lamport)
        return pb.PingReply(responder_id=self.id, lamport=self.clock.tick(),
                            leader_id=self.leader or 0)

    def GetTime(self, req, ctx):
        self.clock.update(req.lamport)
        return pb.TimeReply(physical_time=self.physical.now(), lamport=self.clock.tick())

    def AdjustTime(self, req, ctx):
        self.clock.update(req.lamport)
        self.physical.adjust(req.offset)
        self.log(f"relógio físico ajustado em {req.offset:+.3f}s (Berkeley)")
        return pb.Ack(lamport=self.clock.tick(), ok=True)

    def GetBest(self, req, ctx):
        self.clock.update(req.lamport)
        b = self.island.best()
        return pb.BestReply(node_id=self.id, lamport=self.clock.tick(),
                            generation=self.island.generation,
                            best=pb.Individual(tour=b.tour, length=b.length))

    # ------------------------------------------------- chamadas (cliente)
    def _send_election(self, pid):
        try:
            r = self._stub(pid).Election(
                pb.ElectionRequest(sender_id=self.id, lamport=self.clock.tick()),
                timeout=self.rpc_timeout)
            self.clock.update(r.lamport)
            return True
        except grpc.RpcError:
            return False

    def _send_coordinator(self, pid):
        try:
            r = self._stub(pid).Coordinator(
                pb.CoordinatorRequest(leader_id=self.id, lamport=self.clock.tick()),
                timeout=self.rpc_timeout)
            self.clock.update(r.lamport)
        except grpc.RpcError:
            pass

    def _ping(self, pid):
        """Retorna o PingReply ou None se o nó não respondeu."""
        try:
            r = self._stub(pid).Ping(pb.PingRequest(sender_id=self.id, lamport=self.clock.tick()),
                                     timeout=self.rpc_timeout)
            self.clock.update(r.lamport)
            return r
        except grpc.RpcError:
            return None

    def migrate(self):
        """Envia os melhores indivíduos ao próximo nó vivo do anel. Retorna o id destino."""
        ids = sorted(self.peers)
        ring = [p for p in ids if p > self.id] + [p for p in ids if p < self.id]
        migrants = self.island.emigrants(self.n_migrants)
        for pid in ring:
            req = pb.MigrationRequest(
                sender_id=self.id, lamport=self.clock.tick(),
                migrants=[pb.Individual(tour=m.tour, length=m.length) for m in migrants])
            try:
                ack = self._stub(pid).Migrate(req, timeout=self.rpc_timeout)
                self.clock.update(ack.lamport)
                self.log(f"enviou {len(migrants)} migrante(s) ao nó {pid}")
                return pid
            except grpc.RpcError:
                self.log(f"nó {pid} indisponível; tentando o próximo do anel")
        return None

    def run_berkeley(self):
        """Executado pelo líder: coleta horas, calcula a média e envia os ajustes."""
        diffs = {self.id: 0.0}
        for pid in self.peers:
            try:
                t0 = self.physical.now()
                r = self._stub(pid).GetTime(
                    pb.TimeRequest(sender_id=self.id, lamport=self.clock.tick()),
                    timeout=self.rpc_timeout)
                t1 = self.physical.now()
                self.clock.update(r.lamport)
                diffs[pid] = (r.physical_time + (t1 - t0) / 2) - t1  # compensa RTT/2
            except grpc.RpcError:
                self.log(f"Berkeley: nó {pid} não respondeu; ignorado")
        avg, adj = berkeley_adjustments(diffs, self.berkeley_threshold)
        for pid, delta in adj.items():
            if pid == self.id:
                self.physical.adjust(delta)
                continue
            try:
                r = self._stub(pid).AdjustTime(
                    pb.AdjustRequest(sender_id=self.id, lamport=self.clock.tick(), offset=delta),
                    timeout=self.rpc_timeout)
                self.clock.update(r.lamport)
            except grpc.RpcError:
                self.log(f"Berkeley: falha ao ajustar nó {pid}")
        self.log(f"Berkeley concluído: média das diferenças {avg:+.3f}s")
        return avg, adj

    def collect_best(self):
        """Executado pelo líder: coleta o melhor tour de todos os nós."""
        own = self.island.best()
        nodes = [{"node": self.id, "generation": self.island.generation, "length": own.length}]
        best = (own.length, own.tour)
        for pid in self.peers:
            try:
                r = self._stub(pid).GetBest(
                    pb.BestRequest(sender_id=self.id, lamport=self.clock.tick()),
                    timeout=self.rpc_timeout)
                self.clock.update(r.lamport)
                nodes.append({"node": pid, "generation": r.generation, "length": r.best.length})
                if r.best.length < best[0]:
                    best = (r.best.length, list(r.best.tour))
            except grpc.RpcError:
                nodes.append({"node": pid, "error": "indisponível"})
        return {"leader": self.id, "best_length": best[0], "best_tour": best[1], "nodes": nodes}

    # ------------------------------------------------------------ threads
    def _evolution_loop(self):
        for gen in range(1, self.generations + 1):
            if self._stop.is_set():
                return
            self.island.step()
            if gen % self.migration_interval == 0:
                self.migrate()
            if self.gen_delay:
                time.sleep(self.gen_delay)
        self.finished = True
        self.log(f"evolução concluída. melhor tour local: {self.island.best().length:.2f}")

    def _monitor_loop(self):
        """Detecção de falha do líder por heartbeat; dispara nova eleição."""
        while not self._stop.wait(self.hb_interval):
            leader = self.leader
            if leader == self.id:
                continue
            if leader is None or self._ping(leader) is None:
                self.log(f"líder {leader} indisponível -> iniciando eleição")
                self.election.start()

    def _leader_loop(self):
        while not self._stop.wait(self.berkeley_interval):
            if self.leader == self.id:
                self.run_berkeley()

    def start(self):
        self._server = grpc.server(ThreadPoolExecutor(max_workers=16))
        pbg.add_IslandServiceServicer_to_server(self, self._server)
        self._server.add_insecure_port(f"[::]:{self.address.split(':')[1]}")
        self._server.start()
        self.log(f"gRPC em {self.address}")
        self._stop.wait(self.startup_delay)  # dá tempo dos demais subirem
        self._discover_or_elect()
        for target in (self._evolution_loop, self._monitor_loop, self._leader_loop):
            t = threading.Thread(target=target, daemon=True)
            t.start()
            self._threads.append(t)
        if self.rest_port is not None:
            self._start_rest()
        return self

    def _discover_or_elect(self):
        for pid in self.peers:
            r = self._ping(pid)
            # Só adota o líder existente se ele tiver ID maior; senão, o valentão
            # manda este nó (maior ID vivo) disputar e assumir a liderança.
            if r is not None and r.leader_id > self.id:
                self.election.leader = r.leader_id
                self.log(f"líder descoberto via nó {pid}: {r.leader_id}")
                return
        self.log("nenhum líder de ID maior conhecido -> iniciando eleição")
        self.election.start()
        self.log(f"líder eleito: {self.leader}")

    def stop(self):
        self._stop.set()
        if self.rest_server:
            self.rest_server.shutdown()
        if self._server:
            self._server.stop(0)

    def wait(self):
        self._server.wait_for_termination()

    # ---------------------------------------------------------------- REST
    def status(self):
        b = self.island.best()
        return {"node": self.id, "leader": self.leader, "lamport": self.clock.time,
                "generation": self.island.generation, "finished": self.finished,
                "best_length": b.length, "physical_offset": self.physical.offset,
                "migrants_received": self.island.migrants_received}

    def _start_rest(self):
        node = self

        class Handler(BaseHTTPRequestHandler):
            def _send(self, code, obj):
                body = json.dumps(obj).encode()
                self.send_response(code)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def _leader_only(self):
                if node.leader != node.id:
                    self._send(409, {"error": "este nó não é o líder", "leader": node.leader})
                    return False
                return True

            def do_GET(self):
                if self.path == "/status":
                    self._send(200, node.status())
                elif self.path == "/best":
                    if self._leader_only():
                        self._send(200, node.collect_best())
                else:
                    self._send(404, {"error": "rota inexistente"})

            def do_POST(self):
                if self.path == "/berkeley":
                    if self._leader_only():
                        avg, adj = node.run_berkeley()
                        self._send(200, {"average_diff": avg,
                                         "adjustments": {str(k): v for k, v in adj.items()}})
                else:
                    self._send(404, {"error": "rota inexistente"})

            def log_message(self, *a):
                pass

        self.rest_server = ThreadingHTTPServer(("0.0.0.0", self.rest_port), Handler)
        self.rest_port = self.rest_server.server_address[1]
        threading.Thread(target=self.rest_server.serve_forever, daemon=True).start()
        self.log(f"REST em http://localhost:{self.rest_port} (/status, /best, POST /berkeley)")
