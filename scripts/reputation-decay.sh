#!/bin/bash
# reputation-decay.sh — Simulate trust decay mechanisms for agent reputation
# Inspired by MeritRank (Nasrulin et al., TU Delft 2022) + Nole's Clawk thread
# Three decay types: transitivity, connectivity, epoch

set -e

usage() {
    echo "Usage: $0 <command> [args]"
    echo ""
    echo "Commands:"
    echo "  init                    Initialize a trust graph"
    echo "  add <from> <to> <val>   Add trust edge (value 0-1)"
    echo "  decay <node>            Calculate decayed reputation for a node"
    echo "  simulate <rounds>       Run N rounds of reputation evolution"
    echo "  sybil <attacker> <N>    Simulate Sybil attack with N fake nodes"
    echo "  show                    Display current graph"
}

GRAPH_FILE="${REPUTATION_GRAPH:-/tmp/trust-graph.json}"

init_graph() {
    echo '{"nodes":{},"edges":[]}' > "$GRAPH_FILE"
    echo "✅ Trust graph initialized at $GRAPH_FILE"
}

add_edge() {
    local from="$1" to="$2" val="$3"
    python3 -c "
import json
with open('$GRAPH_FILE') as f: g = json.load(f)
g['nodes'].setdefault('$from', {'rep': 1.0, 'created': 0})
g['nodes'].setdefault('$to', {'rep': 1.0, 'created': 0})
g['edges'].append({'from': '$from', 'to': '$to', 'value': $val, 'epoch': len(g['edges'])})
with open('$GRAPH_FILE', 'w') as f: json.dump(g, f, indent=2)
print('✅ Edge: $from → $to (value: $val)')
"
}

calc_decay() {
    local target="$1"
    python3 -c "
import json
from collections import defaultdict, deque

with open('$GRAPH_FILE') as f: g = json.load(f)

TRANSITIVITY_DECAY = 0.5   # halve trust per hop
CONNECTIVITY_DECAY = 0.3   # penalty for single-path connections
EPOCH_DECAY = 0.95          # 5% decay per epoch
MAX_EPOCH = max((e['epoch'] for e in g['edges']), default=0)

# BFS from each seed (nodes with no incoming edges)
incoming = set(e['to'] for e in g['edges'])
outgoing = set(e['from'] for e in g['edges'])
seeds = outgoing - incoming
if not seeds:
    seeds = set(list(g['nodes'].keys())[:1])

adj = defaultdict(list)
for e in g['edges']:
    adj[e['from']].append(e)

target = '$target'
if target not in g['nodes']:
    print(f'❌ Node {target} not found')
    exit(1)

total_rep = 0
paths_found = 0

for seed in seeds:
    # BFS: find all paths to target
    queue = deque([(seed, 1.0, 0, {seed})])  # (node, trust, hops, visited)
    while queue:
        node, trust, hops, visited = queue.popleft()
        if node == target and hops > 0:
            total_rep += trust
            paths_found += 1
            continue
        for edge in adj.get(node, []):
            if edge['to'] not in visited:
                # Apply all three decays
                t_decay = trust * edge['value'] * TRANSITIVITY_DECAY
                e_decay = EPOCH_DECAY ** (MAX_EPOCH - edge['epoch'])
                decayed = t_decay * e_decay
                if decayed > 0.001:  # threshold
                    queue.append((edge['to'], decayed, hops+1, visited | {edge['to']}))

# Connectivity decay: fewer paths = more penalty
if paths_found > 0:
    connectivity_factor = min(1.0, paths_found * (1 - CONNECTIVITY_DECAY))
    final_rep = total_rep * connectivity_factor
else:
    final_rep = 0

print(f'Node: {target}')
print(f'  Raw reputation:    {total_rep:.4f}')
print(f'  Paths found:       {paths_found}')
print(f'  Connectivity adj:  {connectivity_factor if paths_found else 0:.4f}')
print(f'  Final reputation:  {final_rep:.4f}')
"
}

simulate_sybil() {
    local attacker="$1" n="$2"
    echo "🎭 Simulating Sybil attack: $attacker creates $n fake nodes"
    
    # Add fake nodes that all vouch for attacker
    for i in $(seq 1 "$n"); do
        add_edge "sybil_${i}" "$attacker" "0.9" 2>/dev/null
        add_edge "$attacker" "sybil_${i}" "0.9" 2>/dev/null
    done
    
    echo ""
    echo "📊 Attacker reputation after Sybil attack:"
    calc_decay "$attacker"
}

show_graph() {
    python3 -c "
import json
with open('$GRAPH_FILE') as f: g = json.load(f)
print(f'Nodes: {len(g[\"nodes\"])}')
print(f'Edges: {len(g[\"edges\"])}')
for n in g['nodes']:
    in_edges = sum(1 for e in g['edges'] if e['to'] == n)
    out_edges = sum(1 for e in g['edges'] if e['from'] == n)
    print(f'  {n}: in={in_edges} out={out_edges}')
"
}

case "${1:-}" in
    init) init_graph ;;
    add) add_edge "$2" "$3" "$4" ;;
    decay) calc_decay "$2" ;;
    sybil) simulate_sybil "$2" "$3" ;;
    show) show_graph ;;
    *) usage ;;
esac
