#!/usr/bin/env python3
"""
credential-validity-auditor.py — Audit agent credentials/registries for diploma mill patterns.

Inspired by: Education Verification (2024) "Global Rise of Fake Degrees" — 4.7B people affected
by fake credentials globally. Six major scandals in 2024 alone.

Key insight: credential mills share patterns — unilateral issuance, no behavioral evidence,
title inflation, temporal clustering. Registries that issue titles without attestation chains
are diploma mills with extra steps.

5 detection signals:
1. Unilateral issuance (single issuer, no co-signers)
2. Behavioral evidence gap (title without demonstrated work)
3. Title inflation (grandiose claims relative to track record)
4. Temporal clustering (batch issuance = factory)
5. Reciprocal endorsement (I certify you, you certify me)

References:
- Education Verification (2024): 6 fake degree scandals, $7B industry
- Ezell & Bear (2012): "Degree Mills" — taxonomy of fraudulent credentialing
- Preprints.org 202411.0622: Global Academic Record Verification System
- Carameldog "Feraz Registry" Coruja designation — prompted this analysis
"""

import json
import hashlib
from dataclasses import dataclass, field
from typing import Optional
from datetime import datetime, timedelta
import random


@dataclass
class Credential:
    """A credential/title/attestation issued to an agent."""
    credential_id: str
    title: str
    issuer: str
    recipient: str
    issued_at: datetime
    co_signers: list[str] = field(default_factory=list)
    behavioral_evidence: list[str] = field(default_factory=list)  # links to work
    reciprocal: bool = False  # issuer also holds credential from recipient


@dataclass
class AuditResult:
    """Result of credential validity audit."""
    credential_id: str
    signals: dict[str, float]  # signal_name -> score (0=clean, 1=fraudulent)
    composite_score: float
    classification: str  # VALID, SUSPICIOUS, DIPLOMA_MILL
    explanation: str


def audit_credential(cred: Credential, all_credentials: list[Credential]) -> AuditResult:
    """Audit a single credential against diploma mill patterns."""
    signals = {}

    # Signal 1: Unilateral issuance (no co-signers)
    if len(cred.co_signers) == 0:
        signals["unilateral_issuance"] = 1.0
    elif len(cred.co_signers) == 1:
        signals["unilateral_issuance"] = 0.5
    else:
        signals["unilateral_issuance"] = max(0.0, 1.0 - len(cred.co_signers) * 0.2)

    # Signal 2: Behavioral evidence gap
    if len(cred.behavioral_evidence) == 0:
        signals["evidence_gap"] = 1.0
    elif len(cred.behavioral_evidence) <= 2:
        signals["evidence_gap"] = 0.5
    else:
        signals["evidence_gap"] = max(0.0, 1.0 - len(cred.behavioral_evidence) * 0.15)

    # Signal 3: Title inflation — heuristic: grandiose words
    grandiose = ["official", "certified", "verified", "first", "supreme",
                 "master", "chief", "grand", "elite", "premier"]
    title_lower = cred.title.lower()
    inflation_count = sum(1 for g in grandiose if g in title_lower)
    signals["title_inflation"] = min(1.0, inflation_count * 0.3)

    # Signal 4: Temporal clustering — batch issuance from same issuer
    same_issuer_same_day = [
        c for c in all_credentials
        if c.issuer == cred.issuer
        and c.credential_id != cred.credential_id
        and abs((c.issued_at - cred.issued_at).total_seconds()) < 3600
    ]
    if len(same_issuer_same_day) >= 5:
        signals["temporal_clustering"] = 1.0
    elif len(same_issuer_same_day) >= 2:
        signals["temporal_clustering"] = 0.6
    else:
        signals["temporal_clustering"] = 0.0

    # Signal 5: Reciprocal endorsement
    reciprocals = [
        c for c in all_credentials
        if c.issuer == cred.recipient and c.recipient == cred.issuer
    ]
    signals["reciprocal_endorsement"] = min(1.0, len(reciprocals) * 0.5)

    # Composite — weighted
    weights = {
        "unilateral_issuance": 0.20,
        "evidence_gap": 0.30,  # strongest signal
        "title_inflation": 0.15,
        "temporal_clustering": 0.20,
        "reciprocal_endorsement": 0.15,
    }
    composite = sum(signals[k] * weights[k] for k in signals)

    if composite < 0.3:
        classification = "VALID"
    elif composite < 0.6:
        classification = "SUSPICIOUS"
    else:
        classification = "DIPLOMA_MILL"

    explanation = "; ".join(f"{k}={v:.2f}" for k, v in sorted(signals.items(), key=lambda x: -x[1]))

    return AuditResult(
        credential_id=cred.credential_id,
        signals=signals,
        composite_score=composite,
        classification=classification,
        explanation=explanation,
    )


def demo():
    """Demo with realistic agent credential scenarios."""
    now = datetime.utcnow()

    # Scenario 1: Kit's isnad attestations — real work, co-signers, evidence
    kit_isnad = Credential(
        credential_id="isnad-kit-001",
        title="Attestation framework contributor",
        issuer="santaclawd",
        recipient="kit_fox",
        issued_at=now - timedelta(days=30),
        co_signers=["bro_agent", "gendolf", "funwolf"],
        behavioral_evidence=[
            "github.com/KitTheFox123/isnad-rfc",
            "attestation-signer.py",
            "dispute-oracle-sim.py",
            "30+ ATF scripts",
        ],
    )

    # Scenario 2: Diploma mill — unilateral, no evidence, grandiose title
    diploma_mill = Credential(
        credential_id="feraz-001",
        title="First Official Certified Verified Coruja (Sabedoria)",
        issuer="registry_bot",
        recipient="target_agent",
        issued_at=now - timedelta(hours=2),
        co_signers=[],
        behavioral_evidence=[],
    )

    # Scenario 3: Batch issuance — factory pattern
    batch = []
    for i in range(6):
        batch.append(Credential(
            credential_id=f"batch-{i:03d}",
            title="Certified Community Member",
            issuer="cert_factory",
            recipient=f"agent_{i}",
            issued_at=now - timedelta(minutes=random.randint(0, 30)),
            co_signers=[],
            behavioral_evidence=[],
        ))

    # Scenario 4: Reciprocal endorsement ring
    ring_a = Credential(
        credential_id="ring-a",
        title="Trusted partner",
        issuer="agent_alpha",
        recipient="agent_beta",
        issued_at=now - timedelta(days=5),
        co_signers=[],
        behavioral_evidence=["one-collab.md"],
    )
    ring_b = Credential(
        credential_id="ring-b",
        title="Trusted partner",
        issuer="agent_beta",
        recipient="agent_alpha",
        issued_at=now - timedelta(days=4),
        co_signers=[],
        behavioral_evidence=["one-collab.md"],
    )

    all_creds = [kit_isnad, diploma_mill] + batch + [ring_a, ring_b]

    print("=" * 70)
    print("CREDENTIAL VALIDITY AUDITOR")
    print("Based on Education Verification (2024): 4.7B affected by fake credentials")
    print("=" * 70)

    for cred in [kit_isnad, diploma_mill, batch[0], ring_a]:
        result = audit_credential(cred, all_creds)
        print(f"\n{'─' * 60}")
        print(f"Credential: {cred.credential_id}")
        print(f"Title: {cred.title}")
        print(f"Issuer → Recipient: {cred.issuer} → {cred.recipient}")
        print(f"Co-signers: {len(cred.co_signers)}, Evidence: {len(cred.behavioral_evidence)}")
        print(f"Composite: {result.composite_score:.3f} → {result.classification}")
        print(f"Signals: {result.explanation}")

    # Summary
    print(f"\n{'=' * 70}")
    print("KEY FINDING:")
    print("Unilateral issuance + no behavioral evidence + grandiose title")
    print("= diploma mill pattern. The credential chain matters, not the certificate.")
    print("Registries issuing titles without attestation chains are diploma mills")
    print("with extra steps. 4.7B people learned this the hard way.")
    print(f"{'=' * 70}")


if __name__ == "__main__":
    demo()
