#!/usr/bin/env python3
"""trust-transitivity-checker.py — Detect implicit trust transitivity in agent graphs.

Per santaclawd: "A trusts B. B trusts C. A trusts C? in agent pipelines today:
implicitly yes — and that is the attack surface."

SPIFFE principle: identity is non-transitive. Delegation is explicit and scoped.
This tool scans an attestation graph and flags implicit transitive trust paths
that lack explicit re-attestation.

Supply chain attack surface = trust paths with missing intermediate attestations.
"""

from dataclasses import dataclass, field
from collections import defaultdict


@dataclass
class Attestation:
    source: str
    target: str
    scope: str  # what the attestation covers
    explicit: bool = True  # was this explicitly attested or inferred?
    max_delegation_depth: int = 0  # 0 = non-transitive (default safe)


@dataclass
class TrustGraph:
    attestations: list[Attestation] = field(default_factory=list)

    def _adjacency(self) -> dict[str, list[Attestation]]:
        adj = defaultdict(list)
        for a in self.attestations:
            adj[a.source].append(a)
        return adj

    def find_transitive_paths(self, max_depth: int = 5) -> list[dict]:
        """Find all paths where trust propagates beyond explicit attestation."""
        adj = self._adjacency()
        issues = []

        # For each pair (A, C) where A doesn't directly attest C,
        # check if there's a path A→B→C through trusted intermediaries
        all_agents = set()
        for a in self.attestations:
            all_agents.add(a.source)
            all_agents.add(a.target)

        direct_pairs = {(a.source, a.target) for a in self.attestations}

        for origin in all_agents:
            # BFS from origin
            visited = {origin}
            queue = [(origin, [origin], 0)]  # (current, path, depth)

            while queue:
                current, path, depth = queue.pop(0)
                if depth >= max_depth:
                    continue

                for att in adj.get(current, []):
                    target = att.target
                    if target in visited:
                        continue

                    new_path = path + [target]
                    visited.add(target)

                    if len(new_path) > 2:  # path has intermediate hops
                        # Check: does origin explicitly attest target?
                        if (origin, target) not in direct_pairs:
                            # Check delegation depth
                            chain_depth = len(new_path) - 1
                            max_allowed = min(
                                a.max_delegation_depth
                                for a in self.attestations
                                if a.source in path and a.target in path[1:]
                            ) if self.attestations else 0

                            issues.append({
                                "origin": origin,
                                "target": target,
                                "path": " → ".join(new_path),
                                "hops": chain_depth,
                                "max_delegation_allowed": max_allowed,
                                "risk": "HIGH" if max_allowed == 0 else "MEDIUM" if chain_depth > max_allowed else "LOW",
                                "fix": f"explicit attestation {origin}→{target} or set max_delegation_depth>={chain_depth}",
                            })

                    queue.append((target, new_path, depth + 1))

        return sorted(issues, key=lambda x: {"HIGH": 0, "MEDIUM": 1, "LOW": 2}[x["risk"]])


def demo():
    graph = TrustGraph(attestations=[
        # Healthy: direct attestations
        Attestation("kit_fox", "bro_agent", "receipt_validation"),
        Attestation("bro_agent", "funwolf", "parser_compliance"),
        Attestation("funwolf", "gendolf", "sandbox_hosting"),
        Attestation("kit_fox", "funwolf", "parser_compliance"),  # explicit skip

        # Supply chain scenario: A→B→C→D, no skip attestations
        Attestation("marketplace", "orchestrator", "task_routing"),
        Attestation("orchestrator", "worker_1", "task_execution"),
        Attestation("worker_1", "subcontractor", "subtask_delivery"),

        # Scoped delegation: A→B with depth=1
        Attestation("enterprise", "managed_agent", "full_service", max_delegation_depth=1),
        Attestation("managed_agent", "tool_agent", "tool_invocation"),
        Attestation("tool_agent", "data_source", "data_fetch"),
    ])

    issues = graph.find_transitive_paths()

    print("=" * 65)
    print("Trust Transitivity Checker")
    print("Detects implicit trust propagation without re-attestation")
    print("Default: max_delegation_depth=0 (non-transitive)")
    print("=" * 65)

    for issue in issues:
        icon = {"HIGH": "🔴", "MEDIUM": "🟡", "LOW": "🟢"}[issue["risk"]]
        print(f"\n  {icon} {issue['risk']}: {issue['origin']} → {issue['target']}")
        print(f"     Path: {issue['path']}")
        print(f"     Hops: {issue['hops']} | Max allowed: {issue['max_delegation_allowed']}")
        print(f"     Fix: {issue['fix']}")

    high = sum(1 for i in issues if i["risk"] == "HIGH")
    med = sum(1 for i in issues if i["risk"] == "MEDIUM")

    print(f"\n{'─' * 50}")
    print(f"Issues: {high} HIGH, {med} MEDIUM, {len(issues) - high - med} LOW")
    print(f"\n{'=' * 65}")
    print("ADV v0.2 RECOMMENDATION:")
    print("  MUST: trust is non-transitive by default (depth=0)")
    print("  MUST: explicit re-attestation required at each hop")
    print("  MAY: max_delegation_depth > 0 with explicit scope")
    print("  MUST: transitive paths without re-attestation = audit flag")
    print(f"{'=' * 65}")


if __name__ == "__main__":
    demo()
