"""Eleição de líder pelo algoritmo do valentão (bully), independente de transporte."""
import threading
from concurrent.futures import ThreadPoolExecutor


class BullyElection:
    """
    send_election(pid) -> bool : True se pid respondeu OK (falso se não respondeu).
    send_coordinator(pid)      : anuncia o novo líder (melhor esforço).
    """

    def __init__(self, node_id, peer_ids, send_election, send_coordinator,
                 wait_timeout=3.0, max_rounds=3):
        self.node_id = node_id
        self.peer_ids = list(peer_ids)
        self.send_election = send_election
        self.send_coordinator = send_coordinator
        self.wait_timeout = wait_timeout
        self.max_rounds = max_rounds
        self.leader = None
        self._coord_event = threading.Event()
        self._lock = threading.Lock()
        self._running = False

    def _parallel(self, fn, ids):
        if not ids:
            return []
        with ThreadPoolExecutor(max_workers=len(ids)) as ex:
            return list(ex.map(fn, ids))

    def start(self):
        """Inicia uma eleição (bloqueante). Se já houver uma em curso, retorna."""
        with self._lock:
            if self._running:
                return self.leader
            self._running = True
        try:
            for _ in range(self.max_rounds):
                self._coord_event.clear()
                higher = [p for p in self.peer_ids if p > self.node_id]
                oks = self._parallel(self.send_election, higher)
                if not any(oks):
                    self._become_leader()
                    return self.leader
                # Alguém maior respondeu OK: aguarda o anúncio de COORDENADOR.
                if self._coord_event.wait(self.wait_timeout):
                    return self.leader
            # Quem respondeu OK não anunciou: assume a liderança.
            self._become_leader()
            return self.leader
        finally:
            with self._lock:
                self._running = False

    def _become_leader(self):
        self.leader = self.node_id
        self._parallel(self.send_coordinator, self.peer_ids)
        self._coord_event.set()

    def handle_election(self, sender_id):
        """Recebeu ELEIÇÃO. A resposta OK é feita pelo chamador; se o remetente
        tem ID menor, inicia a própria eleição em outra thread."""
        if sender_id < self.node_id:
            threading.Thread(target=self.start, daemon=True).start()
        return True

    def handle_coordinator(self, leader_id):
        self.leader = leader_id
        self._coord_event.set()
