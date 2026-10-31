"""Executa um nó. Exemplo:
python run_node.py --id 1 --peers 1=localhost:50051,2=localhost:50052,3=localhost:50053
"""
import argparse
import time

from distga.node import Node
from distga.tsp import make_cities


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--id", type=int, required=True)
    ap.add_argument("--peers", required=True, help="id=host:porta,... (todos os nós, inclusive este)")
    ap.add_argument("--cities", type=int, default=60)
    ap.add_argument("--instance-seed", type=int, default=42, help="mesma instância em todos os nós")
    ap.add_argument("--seed", type=int, default=None, help="semente do AG (soma-se ao id)")
    ap.add_argument("--generations", type=int, default=2000)
    ap.add_argument("--pop", type=int, default=100)
    ap.add_argument("--migration-interval", type=int, default=20)
    ap.add_argument("--migrants", type=int, default=3)
    ap.add_argument("--gen-delay", type=float, default=0.02)
    ap.add_argument("--skew", type=float, default=0.0, help="defasagem inicial do relógio físico (s)")
    ap.add_argument("--hb-interval", type=float, default=1.0)
    ap.add_argument("--berkeley-interval", type=float, default=10.0)
    ap.add_argument("--no-rest", action="store_true")
    a = ap.parse_args()

    peers = {int(i): addr for i, addr in (p.split("=") for p in a.peers.split(","))}
    port = int(peers[a.id].split(":")[1])
    node = Node(a.id, peers, make_cities(a.cities, a.instance_seed),
                generations=a.generations, migration_interval=a.migration_interval,
                n_migrants=a.migrants, pop_size=a.pop, skew=a.skew, seed=a.seed,
                hb_interval=a.hb_interval, gen_delay=a.gen_delay,
                berkeley_interval=a.berkeley_interval,
                rest_port=None if a.no_rest else port + 1000)
    node.start()
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        node.stop()


if __name__ == "__main__":
    main()
