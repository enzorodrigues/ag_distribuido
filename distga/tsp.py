"""Problema do Caixeiro Viajante: instâncias e operadores genéticos."""
import math
import random


def make_cities(n, seed=0):
    rng = random.Random(seed)
    return [(rng.random() * 100, rng.random() * 100) for _ in range(n)]


def tour_length(tour, cities):
    n = len(tour)
    return sum(math.dist(cities[tour[i]], cities[tour[(i + 1) % n]]) for i in range(n))


def is_valid_tour(tour, n):
    return sorted(tour) == list(range(n))


def order_crossover(p1, p2, rng):
    """Cruzamento por ordem (OX): copia um trecho de p1 e completa na ordem de p2."""
    n = len(p1)
    a, b = sorted(rng.sample(range(n), 2))
    child = [None] * n
    child[a:b + 1] = p1[a:b + 1]
    used = set(p1[a:b + 1])
    fill = iter(g for g in p2 if g not in used)
    for i in range(n):
        if child[i] is None:
            child[i] = next(fill)
    return child


def swap_mutation(tour, rate, rng):
    t = list(tour)
    for i in range(len(t)):
        if rng.random() < rate:
            j = rng.randrange(len(t))
            t[i], t[j] = t[j], t[i]
    return t


def two_opt(tour, cities, max_passes=None):
    """Busca local 2-opt (primeira melhoria): inverte trechos enquanto isso encurtar o tour.
    Usa apenas a variação (delta) das 2 arestas trocadas, custo O(n^2) por passada."""
    t = list(tour)
    n = len(t)
    d = math.dist
    passes = 0
    improved = True
    while improved and (max_passes is None or passes < max_passes):
        improved = False
        passes += 1
        for i in range(n - 1):
            a, b = cities[t[i]], cities[t[i + 1]]
            for j in range(i + 2, n):
                if i == 0 and j == n - 1:
                    continue  # mesmas arestas (tour circular)
                c, e = cities[t[j]], cities[t[(j + 1) % n]]
                if d(a, c) + d(b, e) - d(a, b) - d(c, e) < -1e-9:
                    t[i + 1:j + 1] = t[i + 1:j + 1][::-1]
                    b = cities[t[i + 1]]
                    improved = True
    return t
