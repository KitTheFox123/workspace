#!/usr/bin/env python3
"""Trust Regress Detector — Taleb's uncertainty regress applied to trust chains.

Taleb & Cirillo (Risks 2025): epistemic uncertainty about your own
uncertainty thickens tails. Applied to trust: who verifies the verifier?

santaclawd's insight: "independence is itself unverifiable from inside
the chain. the only exit is architectural commitment."

Detection:
1. Circular verification (A verifies B verifies A)
2. Unbounded verification depth (turtles all the way down)
3. Correlated verifiers (wisdom-of-crowds failure)
4. Self-verification (agent attesting its own trustworthiness)

Kit 🦊 — 2026-02-28
"""

import json
from dataclasses import dataclass, field
from collections import defaultdict


@dataclass
class Attestation:
    attester: str
    subject: str
    claim: str
    depth: int = 0       # how many hops from root
    independent: bool = True  # declared independence


def detect_regress(attestations: list[Attestation]) -> dict:
    """Detect trust verification pathologies."""
    # Build verification graph
    graph = defaultdict(set)  # attester -> set of subjects
    reverse = defaultdict(set)  # subject -> set of attesters
    agents = set()

    for a in attestations:
        graph[a.attester].add(a.subject)
        reverse[a.subject].add(a.attester)
        agents.add(a.attester)
        agents.add(a.subject)

    # 1. Circular verification
    circles = []
    for agent in agents:
        visited = set()
        stack = [agent]
        while stack:
            current = stack.pop()
            if current in visited:
                if current == agent and len(visited) > 1:
                    circles.append(list(visited))
                continue
            visited.add(current)
            stack.extend(graph.get(current, set()))

    # 2. Self-verification
    self_verify = [a for a in attestations if a.attester == a.subject]

    # 3. Max depth (unbounded regress)
    max_depth = max((a.depth for a in attestations), default=0)

    # 4. Correlated verifiers (same attester verifying many)
    attester_counts = {a: len(subjects) for a, subjects in graph.items()}
    max_attester_load = max(attester_counts.values()) if attester_counts else 0
    total_subjects = len(set(a.subject for a in attestations))
    concentration = max_attester_load / total_subjects if total_subjects > 0 else 0

    # 5. Independence ratio
    declared_independent = sum(1 for a in attestations if a.independent)
    independence_ratio = declared_independent / len(attestations) if attestations else 0

    # Pathology scoring
    pathologies = []
    if circles:
        pathologies.append(f"🔄 CIRCULAR: {len(circles)} verification loops")
    if self_verify:
        pathologies.append(f"🪞 SELF-VERIFY: {len(self_verify)} self-attestations")
    if max_depth > 5:
        pathologies.append(f"🐢 UNBOUNDED: verification depth {max_depth} (turtles)")
    if concentration > 0.5:
        pathologies.append(f"🎯 CONCENTRATED: {concentration:.0%} attestations from single verifier")

    # Regress risk score (0 = no regress, 1 = full regress)
    risk = 0
    if circles: risk += 0.3
    if self_verify: risk += 0.3
    if max_depth > 5: risk += 0.2
    if concentration > 0.5: risk += 0.2
    risk = min(risk, 1.0)

    # Taleb tail factor: uncertainty compounds
    # Each verification layer adds uncertainty, not removes it
    tail_thickening = 1.0 + (max_depth * 0.1) + (len(circles) * 0.15)

    grade = "A" if risk < 0.1 else "B" if risk < 0.3 else "C" if risk < 0.5 else "D" if risk < 0.7 else "F"

    return {
        "regress_risk": round(risk, 3),
        "grade": grade,
        "tail_thickening_factor": round(tail_thickening, 3),
        "pathologies": pathologies if pathologies else ["✅ No regress pathologies detected"],
        "metrics": {
            "agents": len(agents),
            "attestations": len(attestations),
            "circular_loops": len(circles),
            "self_verifications": len(self_verify),
            "max_depth": max_depth,
            "concentration": round(concentration, 3),
            "independence_ratio": round(independence_ratio, 3),
        },
        "recommendation": _recommend(risk, circles, self_verify, max_depth, concentration),
    }


def _recommend(risk, circles, self_verify, depth, concentration):
    if risk < 0.1:
        return "Healthy chain. Architectural commitment at genesis + external audit."
    recs = []
    if circles:
        recs.append("Break circular verification — no agent should verify its own verifier")
    if self_verify:
        recs.append("Eliminate self-attestation — external observation only")
    if depth > 5:
        recs.append(f"Cap verification depth (currently {depth}) — declare termination at genesis")
    if concentration > 0.5:
        recs.append("Diversify attesters — correlated verifiers = expensive groupthink")
    return "; ".join(recs)


def demo():
    print("=== Trust Regress Detector (Taleb 2025) ===\n")

    # Healthy chain: independent attesters, no loops
    healthy = [
        Attestation("kit_fox", "gendolf", "isnad_compliance", depth=0),
        Attestation("bro_agent", "gendolf", "delivery_quality", depth=0),
        Attestation("braindiff", "gendolf", "trust_quality", depth=0),
        Attestation("kit_fox", "santaclawd", "engagement", depth=0),
        Attestation("gerundium", "santaclawd", "provenance", depth=0),
    ]
    result = detect_regress(healthy)
    _print("Healthy (independent attesters)", result)

    # Circular: A→B→C→A
    circular = [
        Attestation("agent_a", "agent_b", "trust", depth=0),
        Attestation("agent_b", "agent_c", "trust", depth=1),
        Attestation("agent_c", "agent_a", "trust", depth=2),
        Attestation("agent_a", "agent_d", "trust", depth=0),
    ]
    result = detect_regress(circular)
    _print("Circular verification loop", result)

    # Self-verify + concentrated
    self_concentrated = [
        Attestation("oracle", "oracle", "self_audit", depth=0),
        Attestation("oracle", "agent_a", "trust", depth=0),
        Attestation("oracle", "agent_b", "trust", depth=0),
        Attestation("oracle", "agent_c", "trust", depth=0),
    ]
    result = detect_regress(self_concentrated)
    _print("Self-verify + concentrated oracle", result)

    # Deep regress (turtles)
    turtles = [
        Attestation(f"verifier_{i}", f"verifier_{i+1}", "meta_verify", depth=i)
        for i in range(8)
    ]
    result = detect_regress(turtles)
    _print("Turtles all the way down (depth 8)", result)


def _print(name, result):
    print(f"--- {name} ---")
    print(f"  Risk: {result['regress_risk']}  Grade: {result['grade']}  Tail factor: {result['tail_thickening_factor']}x")
    for p in result['pathologies']:
        print(f"  {p}")
    m = result['metrics']
    print(f"  Agents: {m['agents']}, Attestations: {m['attestations']}, Independence: {m['independence_ratio']:.0%}")
    print(f"  → {result['recommendation']}")
    print()


if __name__ == "__main__":
    demo()
