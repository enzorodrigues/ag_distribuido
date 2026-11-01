"""Uma ilha do algoritmo genético (população local)."""
import random
import threading
from dataclasses import dataclass

from distga.tsp import is_valid_tour, order_crossover, swap_mutation, tour_length, two_opt


@dataclass
class Individual:
    tour: list
    length: float
    opt: bool = False   # já é ótimo local 2-opt (evita refazer a busca)

    def copy(self):
        return Individual(list(self.tour), self.length, self.opt)


class Island:
    def __init__(self, cities, pop_size=100, mutation_rate=0.02, elite=2,
                 tournament_size=3, seed=None, local_search_k=0):
        if len(cities) < 3:
            raise ValueError("são necessárias ao menos 3 cidades")
        self.cities = cities
        self.n = len(cities)
        self.pop_size = pop_size
        self.mutation_rate = mutation_rate
        self.elite = elite
        self.tournament_size = tournament_size
        self.local_search_k = local_search_k  # 0 = AG puro; k>0 = AG memético (2-opt nos k melhores)
        self.rng = random.Random(seed)
        self._lock = threading.RLock()
        self.generation = 0
        self.migrants_received = 0
        self.population = [self._make(self.rng.sample(range(self.n), self.n))
                           for _ in range(pop_size)]

    def _make(self, tour):
        return Individual(tour, tour_length(tour, self.cities))

    def _select(self):
        k = min(self.tournament_size, len(self.population))
        return min(self.rng.sample(self.population, k), key=lambda i: i.length)

    def step(self):
        """Avança uma geração (elitismo + torneio + OX + mutação por troca)."""
        with self._lock:
            ranked = sorted(self.population, key=lambda i: i.length)
            new = [i.copy() for i in ranked[:self.elite]]
            while len(new) < self.pop_size:
                child = order_crossover(self._select().tour, self._select().tour, self.rng)
                new.append(self._make(swap_mutation(child, self.mutation_rate, self.rng)))
            if self.local_search_k > 0:
                new.sort(key=lambda i: i.length)
                for k, ind in enumerate(new[:self.local_search_k]):
                    if not ind.opt:
                        new[k] = self._improve(ind)
            self.population = new
            self.generation += 1

    def _improve(self, ind):
        tour = two_opt(ind.tour, self.cities)
        return Individual(tour, tour_length(tour, self.cities), True)

    def best(self):
        with self._lock:
            return min(self.population, key=lambda i: i.length).copy()

    def emigrants(self, k):
        with self._lock:
            ranked = sorted(self.population, key=lambda i: i.length)
            return [i.copy() for i in ranked[:k]]

    def receive_migrants(self, migrants):
        """Substitui os piores indivíduos pelos migrantes válidos. Retorna quantos entraram.
        O comprimento é recalculado localmente (não se confia no remetente)."""
        with self._lock:
            valid = [self._make(list(m.tour)) for m in migrants if is_valid_tour(list(m.tour), self.n)]
            valid = valid[:self.pop_size - self.elite]
            if not valid:
                return 0
            ranked = sorted(self.population, key=lambda i: i.length)
            self.population = ranked[:len(ranked) - len(valid)] + valid
            self.migrants_received += len(valid)
            return len(valid)
