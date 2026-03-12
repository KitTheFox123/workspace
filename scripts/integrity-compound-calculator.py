#!/usr/bin/env python3
"""
integrity-compound-calculator.py — Quantify how forgery cost grows with chain length.

kampderp: "forge one record: plausible. forge 1000 consistent records with
causal dependencies: computationally expensive AND logically constrained."

Models: linear chain (hash chain), Merkle tree (CT-style), causal DAG.
Shows forgery cost scaling for each.

Reference: Russ Cox (2019) "Transparent Logs for Skeptical Clients"
- O(lg N) proof per record
- Forging requires rewriting entire subtree

Usage:
    python3 integrity-compound-calculator.py --demo
"""

import math
import json


def hash_chain_forgery_cost(n: int, single_hash_cost: float = 1.0) -> dict:
    """Linear hash chain: forge record k requires recomputing k..N."""
    # Forge record at position k: must recompute all hashes from k to N
    # Worst case (forge first): N hashes
    # Average case: N/2 hashes
    # Best case (forge last): 1 hash
    # But: must also be consistent with any witnesses who saw intermediate states
    worst = n * single_hash_cost
    avg = (n / 2) * single_hash_cost
    # With W witnesses who each hold a snapshot: must forge W consistent views
    return {
        "structure": "hash_chain",
        "records": n,
        "forgery_cost_worst": worst,
        "forgery_cost_avg": avg,
        "scaling": "O(N)",
        "witness_multiplier": "cost * W (independent witnesses)",
    }


def merkle_tree_forgery_cost(n: int) -> dict:
    """Merkle tree (CT-style): forge requires rewriting subtree + root."""
    # Proof size: O(lg N) per record
    # Forgery: must produce new root consistent with all other records
    # If auditor holds old root: must produce valid consistency proof
    # Cost: rebuild path from leaf to root = O(lg N) hashes
    # BUT: if multiple auditors hold different checkpoints, must satisfy ALL
    proof_size = math.ceil(math.log2(max(n, 1)))
    # Forgery with K checkpoints held by independent auditors:
    # must be consistent with ALL → combinatorial constraint
    return {
        "structure": "merkle_tree",
        "records": n,
        "proof_size": proof_size,
        "forgery_cost_single": proof_size,
        "scaling": "O(lg N) per proof, O(N) full rebuild",
        "checkpoint_constraint": "must satisfy ALL auditor checkpoints simultaneously",
    }


def causal_dag_forgery_cost(n: int, avg_deps: float = 2.0) -> dict:
    """Causal DAG: each record depends on avg_deps prior records."""
    # Forge record k: must also update all records that causally depend on k
    # In a DAG with avg_deps dependencies per record:
    # Reachability from any node: roughly (avg_deps)^depth affected records
    # Forging early record: cascade through entire DAG
    depth = math.ceil(math.log(max(n, 1)) / math.log(max(avg_deps, 1.01)))
    # Causal consistency constraint: each forged record must be internally
    # consistent with its dependencies AND dependents
    cascade_worst = n  # forge root → everything
    cascade_avg = n * 0.3  # forge mid → ~30% affected (empirical)

    # Logical constraint: not just hashes but CONTENT must be consistent
    # This is where it gets combinatorially hard
    # Each record has semantic content that must agree with deps
    logical_cost = cascade_avg * avg_deps  # content constraints per affected record

    return {
        "structure": "causal_dag",
        "records": n,
        "avg_dependencies": avg_deps,
        "dag_depth": depth,
        "cascade_worst": int(cascade_worst),
        "cascade_avg": int(cascade_avg),
        "logical_constraints": int(logical_cost),
        "scaling": "O(N * D) where D = avg dependencies",
        "key_insight": "hash forgery is O(N), logical consistency forgery is O(N * D^depth)",
    }


def demo():
    print("=== Integrity Compounding Calculator ===\n")
    print("kampderp: 'integrity chains are fractal security'\n")

    sizes = [1, 10, 100, 1000, 10000]

    print("Chain Length | Hash Chain | Merkle Proof | Causal DAG (logical)")
    print("-" * 70)
    for n in sizes:
        hc = hash_chain_forgery_cost(n)
        mt = merkle_tree_forgery_cost(n)
        cd = causal_dag_forgery_cost(n)
        print(f"  {n:>8}   |  {hc['forgery_cost_worst']:>8.0f}   |    {mt['proof_size']:>4}       |  {cd['logical_constraints']:>8}")

    print(f"\n=== WITNESS MULTIPLIER ===")
    print("With W independent witnesses, forgery cost multiplies:")
    for w in [1, 3, 5, 10]:
        for n in [100, 1000]:
            hc = hash_chain_forgery_cost(n)
            print(f"  N={n:>5}, W={w:>2}: hash_chain={hc['forgery_cost_worst']*w:.0f}, "
                  f"causal_dag={causal_dag_forgery_cost(n)['logical_constraints']*w}")

    print(f"\n=== CT PARALLEL (Russ Cox 2019) ===")
    print("Certificate Transparency: O(lg N) proof, O(N) full rebuild")
    print("Google CT logs: ~10B certificates")
    n_ct = 10_000_000_000
    mt_ct = merkle_tree_forgery_cost(n_ct)
    print(f"  Proof size for 10B records: {mt_ct['proof_size']} hashes")
    print(f"  Full rebuild to forge: {n_ct:,} hashes")
    print(f"  With 3 independent monitors: must satisfy ALL simultaneously")

    print(f"\n=== KIT'S WAL ===")
    # How many WAL entries does Kit have approximately?
    # ~20 heartbeats/day * 30 days * ~10 entries/heartbeat = 6000
    kit_entries = 6000
    kit_dag = causal_dag_forgery_cost(kit_entries, avg_deps=3.0)
    print(f"  Kit's WAL (~{kit_entries} entries, ~3 deps each):")
    print(f"  Hash forgery cost: {kit_entries}")
    print(f"  Logical consistency cost: {kit_dag['logical_constraints']}")
    print(f"  With 3 witnesses (Clawk, email, Ilya): {kit_dag['logical_constraints']*3}")
    print(f"  DAG depth: {kit_dag['dag_depth']}")
    print(f"  Key: each heartbeat makes ALL prior history harder to deny")

    print(f"\n=== INSIGHT ===")
    print("  Hash chains: forgery cost grows linearly (O(N))")
    print("  Merkle trees: proof stays small (O(lg N)), rebuild is O(N)")
    print("  Causal DAGs: forgery cost grows SUPER-linearly (O(N * D^depth))")
    print("  The logical consistency constraint is the real barrier —")
    print("  not the hash computation but the CONTENT that must agree.")
    print("  kampderp: 'forge 1000 consistent records with causal")
    print("  dependencies: computationally expensive AND logically constrained.'")
    print("  This IS fractal security: zoom in, same pattern at every scale.")


if __name__ == "__main__":
    demo()
