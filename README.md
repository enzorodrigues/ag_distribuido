# AG Distribuído para o Caixeiro Viajante (modelo de ilhas)

Trabalho Prático, Entrega 1. Requisitos: **gRPC, eleição valentão, relógio de Lamport, Berkeley e web service REST**.

## Instalação e execução
```bash
pip install -r requirements.txt
python -m grpc_tools.protoc -I proto --python_out=. --grpc_python_out=. proto/distga/island.proto   # só se editar o .proto
./run_local.sh                      # 3 nós na mesma máquina
```
Em máquinas diferentes, rode em cada uma:
```bash
python run_node.py --id 2 --peers 1=192.168.0.10:50051,2=192.168.0.11:50051,3=192.168.0.12:50051
```
Porta REST de cada nó = porta gRPC + 1000.

```bash
curl localhost:51051/status          # estado do nó
curl localhost:51053/best            # só o líder: melhor tour global
curl -X POST localhost:51053/berkeley  # só o líder: força sincronização
```
Teste de falha: mate o líder (maior ID) com Ctrl-C/kill e observe a reeleição nos logs.

## Testes
```bash
pytest -q            # 94 testes (unitários + integração)
pytest tests/test_integration.py -q
```
Detalhes de projeto, conexão e plano de testes: `docs/PLANO.md`.
