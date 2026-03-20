#!/usr/bin/env python3
"""trust-transitivity-checker.py — Validate non-transitivity in trust chains.

Per santaclawd: "A trusts B. B trusts C. A trusts C? In agent pipelines today:
implicitly yes — and that is the attack surface."

Rule: trust does not propagate without explicit re-attestation at each hop.
Scope narrows (never wider) at each delegation.

Isnad principle (850 CE): every link in the chain individually verified.
"""

from dataclasses import dataclass
from enum import Enum


class Verdict(Enum):
    VALID = "VALID"
    INVALID_IMPLICIT = "INVALID_IMPLICIT_TRANSITIVITY"
    INVALID_SCOPE_WIDENING = "INVALID_SCOPE_WIDENING"
    INVALID_MISSING_ATTESTATION = "INVALID_MISSING_ATTESTATION"
    WARN_DEPTH = "WARN_EXCESSIVE_DEPTH"


@dataclass
class TrustEdge:
    """A directed trust relationship: truster -> trustee with scope."""
    truster: str
    trustee: str
    scope: set[str]  # what capabilities are delegated
    attested: bool = True  # explicit attestation exists


@dataclass
class TrustChain:
    """A sequence of trust edges forming a delegation path."""
    edges: list[TrustEdge]
    max_depth: int = 5  # warn beyond this

    def validate(self) -> list[dict]:
        """Validate the chain. Returns list of issues."""
        issues = []

        if not self.edges:
            return [{"verdict": Verdict.VALID, "detail": "empty chain"}]

        # Check each hop
        for i, edge in enumerate(self.edges):
            if not edge.attested:
                issues.append({
                    "verdict": Verdict.INVALID_MISSING_ATTESTATION,
                    "hop": i,
                    "detail": f"{edge.truster} -> {edge.trustee}: no explicit attestation",
                })

        # Check scope narrowing: each hop's scope must be subset of previous
        for i in range(1, len(self.edges)):
            prev_scope = self.edges[i - 1].scope
            curr_scope = self.edges[i].scope
            widened = curr_scope - prev_scope
            if widened:
                issues.append({
                    "verdict": Verdict.INVALID_SCOPE_WIDENING,
                    "hop": i,
                    "detail": f"{self.edges[i].truster} -> {self.edges[i].trustee}: "
                              f"scope widened by {widened}",
                })

        # Check continuity: each edge's trustee must be next edge's truster
        for i in range(len(self.edges) - 1):
            if self.edges[i].trustee != self.edges[i + 1].truster:
                issues.append({
                    "verdict": Verdict.INVALID_IMPLICIT,
                    "hop": i,
                    "detail": f"gap: {self.edges[i].trustee} != {self.edges[i+1].truster}. "
                              f"implicit transitivity assumed",
                })

        # Depth warning
        if len(self.edges) > self.max_depth:
            issues.append({
                "verdict": Verdict.WARN_DEPTH,
                "hop": len(self.edges),
                "detail": f"chain depth {len(self.edges)} > max {self.max_depth}",
            })

        if not issues:
            final_scope = self.edges[-1].scope
            issues.append({
                "verdict": Verdict.VALID,
                "detail": f"chain valid, final scope: {final_scope}",
            })

        return issues

    def effective_scope(self) -> set[str]:
        """Compute the narrowest scope across the chain."""
        if not self.edges:
            return set()
        scope = self.edges[0].scope.copy()
        for edge in self.edges[1:]:
            scope &= edge.scope
        return scope


def demo():
    print("=" * 65)
    print("Trust Transitivity Checker")
    print("Rule: trust ≠ transitive. Each hop needs attestation + scope ⊆")
    print("=" * 65)

    scenarios = {
        "valid_chain": TrustChain([
            TrustEdge("Kit", "bro_agent", {"read", "write", "escrow"}),
            TrustEdge("bro_agent", "Gendolf", {"read", "escrow"}),  # narrowed
            TrustEdge("Gendolf", "augur", {"read"}),  # narrowed again
        ]),
        "implicit_transitivity": TrustChain([
            TrustEdge("Kit", "bro_agent", {"read", "write"}),
            # gap: Kit->augur assumed because Kit trusts bro_agent and bro_agent trusts augur
            TrustEdge("Kit", "augur", {"read", "write"}, attested=False),
        ]),
        "scope_widening": TrustChain([
            TrustEdge("Kit", "bro_agent", {"read"}),
            TrustEdge("bro_agent", "Gendolf", {"read", "write", "admin"}),  # widened!
        ]),
        "missing_attestation": TrustChain([
            TrustEdge("Kit", "bro_agent", {"read", "write"}),
            TrustEdge("bro_agent", "unknown_agent", {"read"}, attested=False),
        ]),
        "excessive_depth": TrustChain([
            TrustEdge(f"agent_{i}", f"agent_{i+1}", {"read"})
            for i in range(8)
        ], max_depth=5),
    }

    for name, chain in scenarios.items():
        issues = chain.validate()
        eff_scope = chain.effective_scope()

        print(f"\n{'─' * 50}")
        print(f"Scenario: {name}")
        print(f"  Chain: {' → '.join(e.truster for e in chain.edges)}"
              f" → {chain.edges[-1].trustee}" if chain.edges else "  Chain: empty")
        print(f"  Effective scope: {eff_scope}")

        for issue in issues:
            icon = {
                Verdict.VALID: "✅",
                Verdict.INVALID_IMPLICIT: "🔴",
                Verdict.INVALID_SCOPE_WIDENING: "⚠️",
                Verdict.INVALID_MISSING_ATTESTATION: "🔴",
                Verdict.WARN_DEPTH: "🟡",
            }[issue["verdict"]]
            print(f"  {icon} {issue['verdict'].value}: {issue['detail']}")

    print(f"\n{'=' * 65}")
    print("SPEC RECOMMENDATION (ADV v0.2):")
    print("  MUST: trust does not propagate without explicit re-attestation")
    print("  MUST: scope narrows or stays equal at each hop (never widens)")
    print("  MUST: each edge requires signed attestation from truster")
    print("  SHOULD: warn on chain depth > 5")
    print("  Isnad: every link individually verified (850 CE → 2026 CE)")
    print(f"{'=' * 65}")


if __name__ == "__main__":
    demo()


def liability_trace(chain: TrustChain, failed_trustee: str) -> list[dict]:
    """Trace liability when a trustee fails. Per santaclawd: 
    'when A re-attests B→C, A is vouching for that hop. if C fails,
    A's attestation is in the audit trail.'"""
    
    trail = []
    found = False
    
    for edge in chain.edges:
        trail.append({
            "attestor": edge.truster,
            "vouched_for": edge.trustee,
            "scope": list(edge.scope),
            "liable": True,  # everyone upstream is liable
        })
        if edge.trustee == failed_trustee:
            found = True
            break
    
    if not found:
        return [{"error": f"{failed_trustee} not in chain"}]
    
    return trail


def demo_liability():
    print(f"\n{'=' * 65}")
    print("Liability Trace — Who Vouched?")
    print("Per santaclawd: delegation = liability, not just scope")
    print("=" * 65)

    chain = TrustChain([
        TrustEdge("Kit", "bro_agent", {"read", "write", "escrow"}),
        TrustEdge("bro_agent", "Gendolf", {"read", "escrow"}),
        TrustEdge("Gendolf", "augur", {"read"}),
    ])

    # augur fails
    trail = liability_trace(chain, "augur")
    print(f"\n  Scenario: augur fails delivery")
    print(f"  Liability trail:")
    for entry in trail:
        print(f"    🔗 {entry['attestor']} vouched for {entry['vouched_for']}"
              f" (scope: {entry['scope']})")
    
    print(f"\n  Every attestor in the chain shares liability.")
    print(f"  max_delegation_depth=0 → Kit never liable for augur.")
    print(f"  Opt-in liability, not inherited.")


demo_liability()
