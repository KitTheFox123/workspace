#!/usr/bin/env python3
"""
harris-matrix.py — Archaeological stratigraphy for attestation chains.

Harris Matrix: events ordered by deposition (what came before what),
not just timestamp. Forgery changes content but can't retroactively
insert layers into a hash chain.

Concepts:
- Terminus post quem (TPQ): event can't predate its earliest dependency
- Terminus ante quem (TAQ): event can't postdate its latest dependent
- Stratigraphic consistency: no cycles in deposition order
- Phase grouping: cluster contemporaneous events

Inspired by santaclawd's stratigraphy thread (Feb 25-26) and
DSF framework (MDPI 2025, 92.6% accuracy).
"""

import json
import hashlib
import sys
from collections import defaultdict
from datetime import datetime, timezone


def hash_event(event: dict) -> str:
    """Content-addressable hash for an attestation event."""
    canonical = json.dumps(event, sort_keys=True, separators=(',', ':'))
    return hashlib.sha256(canonical.encode()).hexdigest()[:16]


def build_matrix(events: list[dict]) -> dict:
    """
    Build Harris Matrix from attestation events.
    
    Each event should have:
      - id: unique identifier
      - timestamp: ISO 8601
      - depends_on: list of event IDs this event references
      - proof_type: type of attestation
      - content_hash: hash of attested content
    """
    # Build adjacency (child → parents)
    graph = defaultdict(set)  # id → set of dependencies
    nodes = {}
    
    for e in events:
        eid = e.get("id", hash_event(e))
        nodes[eid] = e
        for dep in e.get("depends_on", []):
            graph[eid].add(dep)
    
    # Check stratigraphic consistency (no cycles)
    cycles = _detect_cycles(graph, set(nodes.keys()))
    
    # Compute TPQ and TAQ for each event
    timestamps = {}
    for eid, e in nodes.items():
        ts = e.get("timestamp")
        if ts:
            try:
                timestamps[eid] = datetime.fromisoformat(ts.replace("Z", "+00:00"))
            except (ValueError, AttributeError):
                pass
    
    tpq = {}  # terminus post quem: can't be earlier than latest dependency
    taq = {}  # terminus ante quem: can't be later than earliest dependent
    
    # TPQ: max timestamp of all dependencies
    for eid in nodes:
        dep_times = [timestamps[d] for d in graph[eid] if d in timestamps]
        if dep_times:
            tpq[eid] = max(dep_times).isoformat()
    
    # TAQ: min timestamp of all dependents
    reverse_graph = defaultdict(set)
    for eid, deps in graph.items():
        for d in deps:
            reverse_graph[d].add(eid)
    
    for eid in nodes:
        dep_times = [timestamps[d] for d in reverse_graph[eid] if d in timestamps]
        if dep_times:
            taq[eid] = min(dep_times).isoformat()
    
    # Temporal violations: events whose timestamps violate TPQ/TAQ
    violations = []
    for eid in nodes:
        if eid in timestamps:
            if eid in tpq:
                tpq_dt = datetime.fromisoformat(tpq[eid])
                if timestamps[eid] < tpq_dt:
                    violations.append({
                        "event": eid,
                        "type": "tpq_violation",
                        "event_time": timestamps[eid].isoformat(),
                        "earliest_possible": tpq[eid],
                        "message": f"Event claims to predate its dependency"
                    })
    
    # Phase grouping: cluster events with no ordering between them
    phases = _compute_phases(graph, set(nodes.keys()))
    
    # Topological order (deposition sequence)
    topo_order = _topological_sort(graph, set(nodes.keys()))
    
    return {
        "n_events": len(nodes),
        "n_edges": sum(len(deps) for deps in graph.values()),
        "cycles": cycles,
        "consistent": len(cycles) == 0,
        "violations": violations,
        "forged": len(violations) > 0,
        "tpq": tpq,
        "taq": taq,
        "phases": phases,
        "deposition_order": topo_order,
        "scored_at": datetime.now(timezone.utc).isoformat(),
    }


def _detect_cycles(graph: dict, nodes: set) -> list:
    """DFS cycle detection."""
    WHITE, GRAY, BLACK = 0, 1, 2
    color = {n: WHITE for n in nodes}
    cycles = []
    
    def dfs(u, path):
        color[u] = GRAY
        for v in graph.get(u, []):
            if v not in color:
                continue
            if color[v] == GRAY:
                cycle_start = path.index(v)
                cycles.append(path[cycle_start:] + [v])
            elif color[v] == WHITE:
                dfs(v, path + [v])
        color[u] = BLACK
    
    for n in nodes:
        if color[n] == WHITE:
            dfs(n, [n])
    
    return cycles


def _topological_sort(graph: dict, nodes: set) -> list:
    """Kahn's algorithm."""
    in_degree = defaultdict(int)
    for n in nodes:
        in_degree[n] = 0
    for n, deps in graph.items():
        for d in deps:
            if d in nodes:
                in_degree[n] += 1  # n depends on d, so n has incoming edge
    
    queue = [n for n in nodes if in_degree[n] == 0]
    queue.sort()  # deterministic
    order = []
    
    while queue:
        n = queue.pop(0)
        order.append(n)
        # Find nodes that depend on n
        for m in nodes:
            if n in graph.get(m, set()):
                in_degree[m] -= 1
                if in_degree[m] == 0:
                    queue.append(m)
                    queue.sort()
    
    return order


def _compute_phases(graph: dict, nodes: set) -> list[list]:
    """Group events into phases (concurrent layers)."""
    # Phase = set of nodes at same topological depth
    depth = {}
    order = _topological_sort(graph, nodes)
    
    for n in order:
        dep_depths = [depth[d] for d in graph.get(n, set()) if d in depth]
        depth[n] = (max(dep_depths) + 1) if dep_depths else 0
    
    phases_dict = defaultdict(list)
    for n, d in depth.items():
        phases_dict[d].append(n)
    
    return [sorted(phases_dict[d]) for d in sorted(phases_dict.keys())]


def demo():
    """Demo with tc3-like attestation chain."""
    print("=== Harris Matrix — Attestation Stratigraphy ===\n")
    
    events = [
        {
            "id": "contract",
            "timestamp": "2026-02-24T06:26:00Z",
            "depends_on": [],
            "proof_type": "paylock",
            "content_hash": "abc123",
        },
        {
            "id": "delivery",
            "timestamp": "2026-02-24T07:06:00Z",
            "depends_on": ["contract"],
            "proof_type": "dkim",
            "content_hash": "def456",
        },
        {
            "id": "review",
            "timestamp": "2026-02-24T07:46:00Z",
            "depends_on": ["delivery"],
            "proof_type": "gen_sig",
            "content_hash": "ghi789",
        },
        {
            "id": "attestation_momo",
            "timestamp": "2026-02-24T08:00:00Z",
            "depends_on": ["delivery"],
            "proof_type": "witness",
            "content_hash": "jkl012",
        },
        {
            "id": "release",
            "timestamp": "2026-02-24T08:46:00Z",
            "depends_on": ["review", "attestation_momo"],
            "proof_type": "x402_tx",
            "content_hash": "mno345",
        },
    ]
    
    result = build_matrix(events)
    print(f"  Events: {result['n_events']}, Edges: {result['n_edges']}")
    print(f"  Consistent: {result['consistent']}")
    print(f"  Forged: {result['forged']}")
    print(f"  Phases: {result['phases']}")
    print(f"  Deposition order: {result['deposition_order']}")
    print()
    
    # Now test with a forged event (predates its dependency)
    print("--- Forgery test ---")
    forged = events + [{
        "id": "backdated_attestation",
        "timestamp": "2026-02-24T05:00:00Z",  # Before contract!
        "depends_on": ["delivery"],
        "proof_type": "witness",
        "content_hash": "forged",
    }]
    
    result2 = build_matrix(forged)
    print(f"  Forged: {result2['forged']}")
    for v in result2['violations']:
        print(f"  🚨 {v['event']}: {v['message']}")
        print(f"     Claims: {v['event_time']}, Earliest possible: {v['earliest_possible']}")


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--json":
        events = json.loads(sys.stdin.read())
        result = build_matrix(events)
        print(json.dumps(result, indent=2))
    else:
        demo()
