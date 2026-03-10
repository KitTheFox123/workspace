#!/usr/bin/env python3
"""
infrastructure-timestamp-audit.py — Observer-independent vs issuer-controlled evidence

The immutability gap (santaclawd): SMTP headers are written-once by infrastructure.
Attestations are written-many by issuer. The gap = the trust problem.

Biological parallel: epigenetic clocks (Horvath 2013) — DNA methylation is
infrastructure-written. The organism can't forge its own age.

Classifies evidence sources by who writes them:
  - Infrastructure-written (SMTP, CT logs, DNS, blockchain): HIGH trust
  - Observer-independent (multiple independent witnesses): MEDIUM trust  
  - Issuer-controlled (self-reported, self-signed): LOW trust
"""

from dataclasses import dataclass
from typing import List

@dataclass
class EvidenceSource:
    name: str
    writer: str        # "infrastructure" | "observer" | "issuer"
    mutable: bool      # can the writer modify after creation?
    independent: bool  # independent of the subject being measured?
    examples: List[str]

    def trust_score(self) -> float:
        score = 0.0
        if self.writer == "infrastructure": score += 0.5
        elif self.writer == "observer": score += 0.3
        else: score += 0.1
        if not self.mutable: score += 0.3
        if self.independent: score += 0.2
        return min(score, 1.0)

    def grade(self) -> str:
        s = self.trust_score()
        if s >= 0.8: return "A"
        if s >= 0.6: return "B"
        if s >= 0.4: return "C"
        if s >= 0.2: return "D"
        return "F"


EVIDENCE_CATALOG = [
    EvidenceSource("SMTP Received headers", "infrastructure", False, True,
                   ["email routing timestamps", "MTA hop records"]),
    EvidenceSource("CT log entries", "infrastructure", False, True,
                   ["certificate transparency", "RFC 6962 SCTs"]),
    EvidenceSource("DNS query logs", "infrastructure", False, True,
                   ["resolver timestamps", "DNSSEC chains"]),
    EvidenceSource("Blockchain timestamps", "infrastructure", False, True,
                   ["Bitcoin block headers", "Ethereum receipts"]),
    EvidenceSource("Epigenetic clock (Horvath)", "infrastructure", False, True,
                   ["DNA methylation patterns", "CpG site accumulation"]),
    EvidenceSource("Pull-based attestation (RFC 9683)", "observer", False, True,
                   ["TPM quotes", "verifier-initiated probes"]),
    EvidenceSource("Brier-scored calibration", "observer", False, True,
                   ["relying party outcomes", "ground-truth comparison"]),
    EvidenceSource("Peer attestation (signed)", "observer", True, False,
                   ["Ed25519 signatures", "isnad chains"]),
    EvidenceSource("Self-reported heartbeat", "issuer", True, False,
                   ["empty pings", "timestamp-only beats"]),
    EvidenceSource("Self-assessed quality", "issuer", True, False,
                   ["poignancy scores", "self-rated importance"]),
    EvidenceSource("Self-signed capability manifest", "issuer", True, False,
                   ["unsigned scope declarations", "self-reported permissions"]),
]


def audit():
    print("=" * 65)
    print("Infrastructure Timestamp Audit")
    print("Observer-independent vs issuer-controlled evidence")
    print("=" * 65)

    by_writer = {"infrastructure": [], "observer": [], "issuer": []}
    for e in EVIDENCE_CATALOG:
        by_writer[e.writer].append(e)

    for writer, label in [("infrastructure", "INFRASTRUCTURE-WRITTEN (highest trust)"),
                          ("observer", "OBSERVER-INDEPENDENT (medium trust)"),
                          ("issuer", "ISSUER-CONTROLLED (lowest trust)")]:
        print(f"\n--- {label} ---")
        for e in by_writer[writer]:
            print(f"  {e.name}: Grade {e.grade()} ({e.trust_score():.1f})")
            print(f"    mutable={e.mutable}, independent={e.independent}")
            print(f"    examples: {', '.join(e.examples)}")

    # Summary
    infra_avg = sum(e.trust_score() for e in by_writer["infrastructure"]) / len(by_writer["infrastructure"])
    observer_avg = sum(e.trust_score() for e in by_writer["observer"]) / len(by_writer["observer"])
    issuer_avg = sum(e.trust_score() for e in by_writer["issuer"]) / len(by_writer["issuer"])

    print(f"\n{'='*65}")
    print(f"TRUST AVERAGES:")
    print(f"  Infrastructure: {infra_avg:.2f} (Grade {'A' if infra_avg >= 0.8 else 'B'})")
    print(f"  Observer:       {observer_avg:.2f} (Grade {'B' if observer_avg >= 0.6 else 'C'})")
    print(f"  Issuer:         {issuer_avg:.2f} (Grade {'F' if issuer_avg < 0.2 else 'D'})")
    print(f"\nThe immutability gap: infrastructure writes once, issuers write many.")
    print(f"SMTP headers = epigenetic clock = CT log entries.")
    print(f"The subject cant forge what the infrastructure recorded.")


if __name__ == "__main__":
    audit()
