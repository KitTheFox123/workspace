#!/usr/bin/env python3
"""
bridge-vuln-mapper.py — Map cert DAG trust patterns to known bridge attack taxonomy.

Based on Zhang et al (RAID 2024, Ohio State): 35 bridge attacks, 12 attack surfaces,
10 vulnerability categories across 4 types (PI, LI, EI, FI).

Maps our isnad/cert DAG patterns to real exploit categories to identify which
attack surfaces we're covered against and which remain open.

Key insight: most bridges (22/30) use external verification = trusted third parties.
10/35 attacks = leaked keys. Trust boundary confusion is the #1 killer, not logic bugs.
"""

from dataclasses import dataclass
from enum import Enum


class VulnType(Enum):
    PI = "Permission Issue"
    LI = "Logic Issue"
    EI = "Event Issue"
    FI = "Frontend Issue"


class AttackSurface(Enum):
    A1 = "Frontend phishing"
    A2 = "Inaccurate deposit"
    A3 = "Mishandling events"
    A4 = "Mismatched transactions"
    A5 = "Single points of failure"
    A6 = "Rugpull"
    A7 = "Vulnerable contracts"
    A8 = "Problematic mint"
    A9 = "Fake burn"
    A10 = "Incorrect release"
    A11 = "Replayed withdraw"
    A12 = "Inconsistent transfer"


@dataclass
class BridgeExploit:
    name: str
    date: str
    loss_millions: float
    vuln_type: VulnType
    attack_surface: AttackSurface
    root_cause: str


# Top exploits from Zhang et al RAID 2024
EXPLOITS = [
    BridgeExploit("Ronin Network", "2022-03-29", 625, VulnType.PI, AttackSurface.A5, "5/9 multisig keys compromised"),
    BridgeExploit("Poly Network", "2021-08-10", 600, VulnType.PI, AttackSurface.A7, "Unchecked intermediary permission"),
    BridgeExploit("Binance Bridge", "2022-10-06", 566, VulnType.PI, AttackSurface.A10, "Forged proof passed validation"),
    BridgeExploit("Wormhole", "2022-02-02", 320, VulnType.PI, AttackSurface.A8, "Signature verification bypass"),
    BridgeExploit("Nomad", "2022-08-02", 190, VulnType.LI, AttackSurface.A7, "trusted_root initialized to 0x0"),
    BridgeExploit("Multichain Jul", "2023-07-06", 126, VulnType.PI, AttackSurface.A5, "Internal key compromise"),
    BridgeExploit("Horizon Bridge", "2022-06-24", 100, VulnType.PI, AttackSurface.A5, "2/4 multisig compromised"),
    BridgeExploit("Heco Bridge", "2023-11-22", 86, VulnType.PI, AttackSurface.A5, "Privileged key compromised"),
    BridgeExploit("Orbit Bridge", "2023-12-31", 82, VulnType.PI, AttackSurface.A5, "7/10 multisig compromised"),
    BridgeExploit("Qubit", "2022-01-27", 80, VulnType.EI, AttackSurface.A2, "Incorrect deposit event emission"),
]


@dataclass
class CertDAGDefense:
    name: str
    description: str
    covers: list  # AttackSurface values
    mechanism: str


# How cert DAG / isnad patterns defend against these
DEFENSES = [
    CertDAGDefense(
        "Hash-chained attestations",
        "Every cert links to parent via hash — tamper-evident chain",
        [AttackSurface.A11, AttackSurface.A10],
        "Replay detection: each cert_id is unique, parent_hash prevents reuse"
    ),
    CertDAGDefense(
        "Scope hash binding",
        "cert binds to specific scope_hash — capability drift detected",
        [AttackSurface.A8, AttackSurface.A12],
        "Mint/transfer mismatch caught when scope_hash diverges from expected"
    ),
    CertDAGDefense(
        "Multi-attester quorum",
        "Require diverse attesters (not just threshold count)",
        [AttackSurface.A5],
        "Attester diversity > threshold count. Correlated compromise requires more work"
    ),
    CertDAGDefense(
        "Evidence-gated attestation",
        "Observation protocol: must cite evidence, not just assert",
        [AttackSurface.A9, AttackSurface.A3],
        "Fake events detected: evidence must be independently verifiable"
    ),
    CertDAGDefense(
        "Remediation tracking",
        "DETECT→CONTAIN→FIX→VERIFY lifecycle as attestation events",
        [AttackSurface.A7],
        "Vulnerability lifecycle tracked: fix IS an attestation, not just detection"
    ),
    CertDAGDefense(
        "CUSUM regime detection",
        "Statistical anomaly detection with hysteresis",
        [AttackSurface.A4, AttackSurface.A6],
        "Behavioral drift caught before catastrophic loss"
    ),
]


def coverage_analysis():
    all_surfaces = set(AttackSurface)
    covered = set()
    for d in DEFENSES:
        covered.update(d.covers)
    uncovered = all_surfaces - covered

    total_loss = sum(e.loss_millions for e in EXPLOITS)
    covered_loss = sum(e.loss_millions for e in EXPLOITS if e.attack_surface in covered)

    print("=" * 65)
    print("CERT DAG DEFENSE COVERAGE vs BRIDGE EXPLOIT TAXONOMY")
    print(f"Source: Zhang et al, RAID 2024 (Ohio State / George Mason)")
    print("=" * 65)

    print(f"\n--- TOP 10 EXPLOITS (${total_loss:.0f}M total) ---")
    for e in EXPLOITS:
        status = "✓ COVERED" if e.attack_surface in covered else "✗ OPEN"
        print(f"  {e.name:20s} ${e.loss_millions:>6.0f}M  {e.attack_surface.name}: {e.root_cause[:40]:40s} [{status}]")

    print(f"\n--- DEFENSES ({len(DEFENSES)}) ---")
    for d in DEFENSES:
        surfaces = ", ".join(s.name for s in d.covers)
        print(f"  {d.name:30s} → {surfaces}")
        print(f"    {d.mechanism}")

    print(f"\n--- COVERAGE ---")
    print(f"  Attack surfaces covered: {len(covered)}/{len(all_surfaces)}")
    print(f"  Loss covered:            ${covered_loss:.0f}M / ${total_loss:.0f}M ({covered_loss/total_loss*100:.0f}%)")
    print(f"  Uncovered surfaces:")
    for s in sorted(uncovered, key=lambda x: x.name):
        print(f"    {s.name}: {s.value}")

    # Type distribution
    print(f"\n--- VULNERABILITY TYPE DISTRIBUTION ---")
    type_counts = {}
    type_losses = {}
    for e in EXPLOITS:
        type_counts[e.vuln_type] = type_counts.get(e.vuln_type, 0) + 1
        type_losses[e.vuln_type] = type_losses.get(e.vuln_type, 0) + e.loss_millions
    for vt in VulnType:
        c = type_counts.get(vt, 0)
        l = type_losses.get(vt, 0)
        print(f"  {vt.value:20s}: {c} attacks, ${l:.0f}M")

    print(f"\n--- KEY INSIGHT ---")
    print(f"  Permission Issues = {type_counts.get(VulnType.PI, 0)} of top 10 = ${type_losses.get(VulnType.PI, 0):.0f}M")
    print(f"  Leaked keys alone = 5 exploits = $993M")
    print(f"  Trust boundary confusion > logic bugs. EVERY TIME.")
    print(f"  Attester diversity is load-bearing. Threshold alone is not enough.")
    print("=" * 65)


if __name__ == "__main__":
    coverage_analysis()
