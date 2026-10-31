#!/usr/bin/env bash
# Sobe 3 nós locais (relógios com defasagens diferentes). Ctrl-C encerra todos.
P="1=localhost:50051,2=localhost:50052,3=localhost:50053"
trap 'kill 0' EXIT
python3 run_node.py --id 1 --peers $P --skew -6 --seed 1 &
python3 run_node.py --id 2 --peers $P --skew 3  --seed 1 &
python3 run_node.py --id 3 --peers $P --skew 8  --seed 1 &
wait
