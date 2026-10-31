# Plano: AG Distribuído (TSP, ilhas) — Entrega 1

## 1. Refinamento

**Problema.** Caixeiro Viajante com N cidades (padrão 60), resolvido por algoritmo genético em modelo de ilhas: cada nó mantém uma população própria e, a cada M gerações, envia seus melhores indivíduos ao vizinho no anel (migração).

**Requisitos da entrega (mínimo 2; implementados 5)**

| Requisito do enunciado | Onde está | Papel no sistema |
|---|---|---|
| RPC (gRPC) | `proto/distga/island.proto`, `node.py` | Toda comunicação entre nós |
| Eleição de líder | `election.py` (valentão) | Escolhe o coordenador; reelege se ele cair |
| Relógios lógicos | `clocks.py` (Lamport) | Campo `lamport` em todas as mensagens; logs ordenados causalmente |
| Sincronização de relógios físicos | `clocks.py` + `node.run_berkeley` | O líder sincroniza os relógios dos nós |
| Web service | `node._start_rest` (REST) | Monitoramento e controle pelo líder |

**Papéis.** *Nó comum:* roda a ilha, migra indivíduos, responde RPCs, monitora o líder por heartbeat. *Líder (maior ID vivo):* além disso, executa o Berkeley periodicamente e agrega o melhor tour global (REST `/best`).

**Decisões e premissas**
- Todos os nós usam a mesma instância do TSP (`--instance-seed`) e sementes de AG diferentes (`seed + id`).
- Relógio físico simulado com defasagem (`--skew`), para o Berkeley ter o que corrigir.
- Migrante recebido tem o comprimento recalculado (não se confia no remetente) e tours inválidos são descartados.
- Falhas na migração: o remetente tenta o próximo nó do anel. Falha do líder: heartbeat detecta e dispara eleição. (A Entrega 2 aprofunda o tratamento de falhas.)
- Fora do escopo: persistência, autenticação/TLS, partições de rede, replicação.

## 2. Plano de implementação e conexão

**Topologia.** Malha completa para eleição, heartbeat e Berkeley (todos conhecem todos); anel lógico por ID crescente para migração.

```
        migração (anel) 1 ──► 2 ──► 3 ──► 1
 Nó 1 ◄──── gRPC (eleição, ping, tempo, melhor) ────► Nó 2, Nó 3
 cliente HTTP ──REST──► líder (/status /best POST /berkeley)
```

**Mensagens gRPC** (todas com `lamport`)

| RPC | De → Para | Conteúdo | Quando |
|---|---|---|---|
| `Migrate` | nó → sucessor no anel | `sender_id`, lista de `Individual(tour, length)` | a cada M gerações |
| `Election` | iniciador → IDs maiores | `sender_id`; resposta = OK | falha do líder / entrada |
| `Coordinator` | novo líder → todos | `leader_id` | fim da eleição |
| `Ping` | nó → líder / descoberta | `sender_id`; resposta traz `leader_id` | a cada `hb-interval` |
| `GetTime` | líder → nós | resposta traz `physical_time` | ciclo do Berkeley |
| `AdjustTime` | líder → nós | `offset` a somar | ciclo do Berkeley |
| `GetBest` | líder → nós | resposta traz melhor `Individual` | REST `/best` |

**Algoritmos**
- *Lamport:* envio = `tick()` e coloca em `lamport`; recepção = `max(local, msg)+1`.
- *Valentão:* envia ELEIÇÃO aos maiores (em paralelo). Sem OK → vira líder e anuncia COORDENADOR. Com OK → espera o anúncio (timeout) e repete até 3 rodadas. Quem recebe ELEIÇÃO de ID menor responde OK e inicia a própria. Nó que entra depois só adota o líder se este tiver ID maior; senão, disputa e assume.
- *Berkeley:* líder mede `t0/t1` ao pedir a hora, estima o relógio do nó como `t_nó + RTT/2`, calcula diferenças em relação a si, descarta outliers acima do limite, tira a média e envia a cada nó o **ajuste relativo** `média − diferença` (inclusive a si).
- *AG:* elitismo (2) + torneio (3) + cruzamento OX + mutação por troca.

**Ordem de construção (já realizada)**
1. `.proto` + stubs → 2. `clocks`, `tsp`, `island`, `election` (puros e testáveis) → 3. `node` (gRPC, migração, monitor, Berkeley, REST) → 4. `run_node.py` → 5. testes → 6. execução com processos reais.

## 3. Plano de testes

| Nível | Foco | Arquivo |
|---|---|---|
| Unitário | Lamport (regras, thread-safety), cálculo do Berkeley (exemplo do Ex. 7f, outliers), operadores do TSP (permutação válida), ilha (elitismo, migrantes, validação) | `test_clocks.py`, `test_tsp.py`, `test_island.py` |
| Unitário c/ rede simulada | Valentão: Ex. 7b (P5 falho → P4), eleições simultâneas (Ex. 7e), maior ID, único vivo, OK sem COORDENADOR | `test_election.py` |
| Integração | Nós reais via gRPC: eleição, reeleição ao matar o líder, nó maior que entra tarde, migração em anel e pulo de nó morto, causalidade de Lamport, Berkeley, REST | `test_integration.py` |
| Sistema (manual) | 3 processos independentes, `curl` nos endpoints, matar o líder | `run_local.sh` |

Critérios de aceite: líder = maior ID vivo em todos os nós; reeleição em poucos segundos; relógios convergem à média; `/best` responde 409 fora do líder; melhor tour nunca piora.

## 4. Resultados obtidos
- `pytest`: **94 testes passando** (3 execuções seguidas, sem instabilidade).
- Execução real com 3 processos: líder 3 eleito; Berkeley levou os relógios (skews −3, 4, 11) à média 4,0; `/best` agregou o melhor tour; ao matar o nó 3, o nó 2 detectou e assumiu a liderança.
- Defeito encontrado e corrigido nos testes: nó de ID maior que entra tarde adotava o líder menor; agora dispara eleição e assume.

## 5. Limitações conhecidas (insumo para a Entrega 2)
- Berkeley aplica o ajuste de uma vez (a lentificação gradual do relógio, vista no Ex. 14.2, não foi implementada).
- Sem tratamento de partição de rede (pode surgir mais de um líder).
- Sem replicação do estado; se um nó cai, sua população é perdida.
- Análise de desempenho (1 máquina × N nós) ainda não feita.
