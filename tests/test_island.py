import pytest

from distga.island import Individual, Island
from distga.tsp import is_valid_tour, make_cities, tour_length


@pytest.fixture
def island():
    return Island(make_cities(20, 1), pop_size=40, seed=7)


def test_minimo_de_cidades():
    with pytest.raises(ValueError):
        Island(make_cities(2), pop_size=10)


def test_populacao_inicial_valida(island):
    assert len(island.population) == 40
    assert all(is_valid_tour(i.tour, 20) for i in island.population)


def test_step_mantem_tamanho_e_validade(island):
    island.step()
    assert len(island.population) == 40
    assert island.generation == 1
    assert all(is_valid_tour(i.tour, 20) for i in island.population)
    assert all(i.length == pytest.approx(tour_length(i.tour, island.cities))
               for i in island.population)


def test_elitismo_melhor_nunca_piora(island):
    anterior = island.best().length
    for _ in range(30):
        island.step()
        atual = island.best().length
        assert atual <= anterior + 1e-9
        anterior = atual


def test_evolucao_melhora_solucao(island):
    inicial = island.best().length
    for _ in range(100):
        island.step()
    assert island.best().length < inicial


def test_emigrantes_sao_os_melhores_e_copias(island):
    em = island.emigrants(3)
    lens = [i.length for i in em]
    assert lens == sorted(lens) and lens[0] == island.best().length
    original = list(em[0].tour)
    em[0].tour.reverse()                      # alterar a cópia não afeta a população
    assert original in [i.tour for i in island.population]


def test_migrante_recalcula_comprimento_e_substitui_pior(island):
    tour = list(range(20))
    mentiroso = Individual(tour, 0.0)               # remetente mente sobre o comprimento
    antes = len(island.population)
    assert island.receive_migrants([mentiroso]) == 1
    assert len(island.population) == antes
    real = tour_length(tour, island.cities)
    assert any(i.tour == tour and i.length == pytest.approx(real) for i in island.population)
    assert island.migrants_received == 1


def test_migrantes_invalidos_sao_ignorados(island):
    assert island.receive_migrants([Individual([0, 0, 1], 1.0), Individual([1, 2], 1.0)]) == 0
    assert island.migrants_received == 0


def test_migrante_melhor_vira_o_best():
    cities = [(0, 0), (0, 1), (1, 1), (1, 0)] * 3   # pontos repetidos: ainda é válido
    isl = Island(cities, pop_size=10, seed=1)
    otimo = Individual([0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11], 0)
    isl.receive_migrants([otimo])
    assert isl.best().length <= tour_length(otimo.tour, cities) + 1e-9
