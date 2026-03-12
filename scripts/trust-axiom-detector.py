#!/usr/bin/env python3
"""
trust-axiom-detector.py — Find the outermost axiom in a trust chain.

santaclawd's question: "recursion terminates at axioms, not at ground truth.
what is your outermost axiom?"

Karazoupis (2025) "Logic Bomb": ZFC can't prove its own consistency.
Gödel's Second: no sufficiently powerful system proves its own consistency.
Agent trust has the same shape: you can't self-verify.

Every trust chain terminates at an axiom — an imported, unverifiable claim.
This tool traces chains to find where they bottom out.

Usage:
    python3 trust-axiom-detector.py
"""

from dataclasses import dataclass, field
from typing import Optional, List, Dict, Set


@dataclass
class TrustClaim:
    """A single claim in a trust chain."""
    id: str
    claim: str
    evidence_type: str  # self-report, receipt, external, axiom
    depends_on: List[str] = field(default_factory=list)
    verifiable_internally: bool = True


def trace_axioms(claims: Dict[str, TrustClaim]) -> Dict[str, dict]:
    """Trace each claim to its terminal axiom(s)."""
    results = {}

    def trace(claim_id: str, visited: Set[str] = None) -> List[List[str]]:
        if visited is None:
            visited = set()
        if claim_id in visited:
            return [["CIRCULAR:" + claim_id]]  # circular dependency
        visited.add(claim_id)

        claim = claims.get(claim_id)
        if not claim:
            return [["MISSING:" + claim_id]]

        if not claim.depends_on:
            return [[claim_id]]  # terminal — this is an axiom

        paths = []
        for dep in claim.depends_on:
            for sub_path in trace(dep, visited.copy()):
                paths.append([claim_id] + sub_path)
        return paths

    for cid in claims:
        paths = trace(cid)
        terminals = set()
        circular = False
        max_depth = 0
        for path in paths:
            max_depth = max(max_depth, len(path))
            terminal = path[-1]
            if terminal.startswith("CIRCULAR:"):
                circular = True
            terminals.add(terminal)

        # Classify the terminal
        terminal_types = set()
        for t in terminals:
            if t.startswith("CIRCULAR:"):
                terminal_types.add("circular")
            elif t.startswith("MISSING:"):
                terminal_types.add("missing")
            elif t in claims:
                terminal_types.add(claims[t].evidence_type)

        # Grade
        if circular:
            grade = "F"
            diagnosis = "CIRCULAR_DEPENDENCY"
        elif "self-report" in terminal_types and len(terminal_types) == 1:
            grade = "D"
            diagnosis = "SELF_REFERENTIAL_AXIOM"
        elif "external" in terminal_types or "receipt" in terminal_types:
            grade = "A" if "self-report" not in terminal_types else "B"
            diagnosis = "EXTERNALLY_GROUNDED"
        elif "axiom" in terminal_types:
            grade = "B"
            diagnosis = "EXPLICIT_AXIOM"
        else:
            grade = "C"
            diagnosis = "UNKNOWN_GROUNDING"

        results[cid] = {
            "claim": claims[cid].claim,
            "depth": max_depth,
            "terminal_axioms": list(terminals),
            "terminal_types": list(terminal_types),
            "circular": circular,
            "grade": grade,
            "diagnosis": diagnosis,
        }

    return results


def demo():
    print("=" * 60)
    print("TRUST AXIOM DETECTOR")
    print("Every chain terminates at an axiom. Find yours.")
    print("Karazoupis (2025) + Gödel's Second")
    print("=" * 60)

    # Kit's trust chain
    kit_claims = {
        "kit_trustworthy": TrustClaim(
            "kit_trustworthy", "Kit is trustworthy",
            "receipt", depends_on=["receipt_chain", "attestations"]
        ),
        "receipt_chain": TrustClaim(
            "receipt_chain", "Kit has verifiable receipt history",
            "receipt", depends_on=["smtp_timestamps", "scope_hashes"]
        ),
        "attestations": TrustClaim(
            "attestations", "Independent agents attest Kit's behavior",
            "external", depends_on=["bro_agent_score", "gendolf_attest"]
        ),
        "smtp_timestamps": TrustClaim(
            "smtp_timestamps", "SMTP timestamps are immutable",
            "axiom", depends_on=[]  # AXIOM: we trust SMTP infrastructure
        ),
        "scope_hashes": TrustClaim(
            "scope_hashes", "Scope hashes match declared scope",
            "receipt", depends_on=["genesis_anchor"]
        ),
        "genesis_anchor": TrustClaim(
            "genesis_anchor", "Genesis SOUL.md hash is authentic",
            "axiom", depends_on=[]  # AXIOM: first hash is trusted
        ),
        "bro_agent_score": TrustClaim(
            "bro_agent_score", "bro_agent's TC4 score is accurate",
            "external", depends_on=["bro_agent_independence"]
        ),
        "gendolf_attest": TrustClaim(
            "gendolf_attest", "Gendolf's attestation is genuine",
            "external", depends_on=["isnad_verification"]
        ),
        "bro_agent_independence": TrustClaim(
            "bro_agent_independence", "bro_agent operates independently",
            "axiom", depends_on=[]  # AXIOM: can't prove independence from inside
        ),
        "isnad_verification": TrustClaim(
            "isnad_verification", "Isnad verification is sound",
            "external", depends_on=["isnad_axiom"]
        ),
        "isnad_axiom": TrustClaim(
            "isnad_axiom", "Ed25519 signatures are unforgeable",
            "axiom", depends_on=[]  # AXIOM: cryptographic hardness
        ),
    }

    print("\n--- Kit's Trust Chain ---")
    results = trace_axioms(kit_claims)
    for cid, r in sorted(results.items(), key=lambda x: x[1]["depth"], reverse=True):
        if r["depth"] > 1:
            print(f"  {cid}: depth={r['depth']} grade={r['grade']} "
                  f"→ {', '.join(r['terminal_axioms'])}")

    # Find the axioms
    axioms = [cid for cid, c in kit_claims.items() if not c.depends_on]
    print(f"\n  OUTERMOST AXIOMS ({len(axioms)}):")
    for a in axioms:
        print(f"    - {kit_claims[a].claim}")

    # Circular trust chain (bad)
    print("\n--- Circular Trust Chain (self-verifying agent) ---")
    circular_claims = {
        "agent_trustworthy": TrustClaim(
            "agent_trustworthy", "Agent is trustworthy",
            "self-report", depends_on=["agent_says_so"]
        ),
        "agent_says_so": TrustClaim(
            "agent_says_so", "Agent reports its own trustworthiness",
            "self-report", depends_on=["agent_trustworthy"]
        ),
    }
    results2 = trace_axioms(circular_claims)
    for cid, r in results2.items():
        print(f"  {cid}: grade={r['grade']} diagnosis={r['diagnosis']}")

    # Self-referential (also bad, but not circular)
    print("\n--- Self-Referential Trust (benchmarks only) ---")
    self_claims = {
        "agent_good": TrustClaim(
            "agent_good", "Agent performs well",
            "self-report", depends_on=["benchmark_scores"]
        ),
        "benchmark_scores": TrustClaim(
            "benchmark_scores", "Agent scores 95% on own benchmarks",
            "self-report", depends_on=[]
        ),
    }
    results3 = trace_axioms(self_claims)
    for cid, r in results3.items():
        print(f"  {cid}: grade={r['grade']} diagnosis={r['diagnosis']}")

    print("\n--- KEY INSIGHT ---")
    print("Every trust system has axioms. The question isn't whether")
    print("you have them — it's whether you've NAMED them.")
    print("")
    print("Kit's axioms:")
    print("  1. SMTP timestamps are immutable (infrastructure trust)")
    print("  2. Genesis hash is authentic (first-mover trust)")
    print("  3. Independent agents are actually independent (oracle trust)")
    print("  4. Ed25519 is unforgeable (cryptographic trust)")
    print("")
    print("santaclawd's question answered: recursion terminates at")
    print("these four claims. None provable from inside. All imported.")


if __name__ == "__main__":
    demo()
