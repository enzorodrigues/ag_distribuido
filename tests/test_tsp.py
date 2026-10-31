import random

import pytest

from distga.tsp import (is_valid_tour, make_cities, order_crossover, swap_mutation,
                        tour_length)


def test_make_cities_determinista():
    assert make_cities(10, seed=1) == make_cities(10, seed=1)
    assert make_cities(10, seed=1) != make_cities(10, seed=2)
    assert len(make_cities(25)) == 25


def test_tour_length_quadrado():
    cities = [(0, 0), (0, 1), (1, 1), (1, 0)]
    assert tour_length([0, 1, 2, 3], cities) == pytest.approx(4.0)
    assert tour_length([0, 2, 1, 3], cities) > 4.0   # tour que cruza é pior


def test_tour_length_independe_do_ponto_inicial():
    cities = make_cities(8, 3)
    t = list(range(8))
    assert tour_length(t, cities) == pytest.approx(tour_length(t[3:] + t[:3], cities))


def test_is_valid_tour():
    assert is_valid_tour([2, 0, 1], 3)
    assert not is_valid_tour([0, 0, 1], 3)
    assert not is_valid_tour([0, 1], 3)
    assert not is_valid_tour([0, 1, 3], 3)


@pytest.mark.parametrize("seed", range(50))
def test_order_crossover_gera_permutacao_valida(seed):
    rng = random.Random(seed)
    p1, p2 = rng.sample(range(20), 20), rng.sample(range(20), 20)
    assert is_valid_tour(order_crossover(p1, p2, rng), 20)


def test_order_crossover_preserva_trecho_do_pai1():
    rng = random.Random(0)
    p1, p2 = list(range(10)), list(reversed(range(10)))
    child = order_crossover(p1, p2, rng)
    assert any(child[i] == p1[i] for i in range(10))


def test_swap_mutation_taxa_zero_nao_muda():
    t = list(range(10))
    assert swap_mutation(t, 0.0, random.Random(1)) == t


def test_swap_mutation_mantem_permutacao_e_nao_altera_original():
    t = list(range(15))
    m = swap_mutation(t, 1.0, random.Random(1))
    assert is_valid_tour(m, 15)
    assert t == list(range(15))
