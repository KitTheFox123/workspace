#!/usr/bin/env python3
"""dkim-replay-detector.py — Detect DKIM replay attacks on agent email.

DKIM replay attack (Abnormal AI, Apr 2025): attacker takes a legitimately
DKIM-signed email and re-sends it from a different context. The signature
validates because DKIM signs the body+headers, not the transport path.

Detection signals:
1. Envelope mismatch — SMTP MAIL FROM ≠ header From (ARC helps but isn't universal)
2. Temporal anomaly — message Date vs actual receipt time
3. Duplicate signature — same DKIM signature seen in multiple contexts
4. Path analysis — Received headers show unexpected routing

This models the detection problem as a scoring system.
"""

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Optional


@dataclass
class EmailMessage:
    message_id: str
    from_header: str
    envelope_from: str
    dkim_signature: str
    date: datetime
    received_time: datetime
    received_headers: list[str] = field(default_factory=list)
    body_hash: str = ""


@dataclass
class ReplaySignal:
    name: str
    score: float  # 0.0 = clean, 1.0 = definite replay
    detail: str


class DKIMReplayDetector:
    """Multi-signal DKIM replay detection."""

    def __init__(self):
        self.seen_signatures: dict[str, list[EmailMessage]] = {}
        self.seen_body_hashes: dict[str, list[EmailMessage]] = {}

    def ingest(self, msg: EmailMessage) -> list[ReplaySignal]:
        """Analyze a message for replay indicators."""
        signals = []

        # Signal 1: Envelope mismatch
        signals.append(self._check_envelope_mismatch(msg))

        # Signal 2: Temporal anomaly
        signals.append(self._check_temporal_anomaly(msg))

        # Signal 3: Duplicate DKIM signature
        signals.append(self._check_duplicate_signature(msg))

        # Signal 4: Body reuse (same body, different context)
        signals.append(self._check_body_reuse(msg))

        # Track for future detection
        self.seen_signatures.setdefault(msg.dkim_signature, []).append(msg)
        if msg.body_hash:
            self.seen_body_hashes.setdefault(msg.body_hash, []).append(msg)

        return signals

    def _check_envelope_mismatch(self, msg: EmailMessage) -> ReplaySignal:
        """SMTP envelope From ≠ header From = suspicious."""
        if not msg.envelope_from:
            return ReplaySignal("envelope_mismatch", 0.3, "No envelope From available")

        env_domain = msg.envelope_from.split("@")[-1].lower()
        hdr_domain = msg.from_header.split("@")[-1].lower().rstrip(">")

        if env_domain != hdr_domain:
            return ReplaySignal(
                "envelope_mismatch", 0.8,
                f"Envelope domain ({env_domain}) ≠ header domain ({hdr_domain})"
            )
        return ReplaySignal("envelope_mismatch", 0.0, "Domains match")

    def _check_temporal_anomaly(self, msg: EmailMessage) -> ReplaySignal:
        """Large gap between Date header and receipt = replay or delay."""
        delta = abs((msg.received_time - msg.date).total_seconds())

        if delta > 86400:  # > 24 hours
            return ReplaySignal(
                "temporal_anomaly", 0.9,
                f"Date-to-receipt gap: {delta/3600:.1f} hours"
            )
        elif delta > 3600:  # > 1 hour
            return ReplaySignal(
                "temporal_anomaly", 0.5,
                f"Date-to-receipt gap: {delta/60:.0f} minutes"
            )
        elif delta > 300:  # > 5 min
            return ReplaySignal(
                "temporal_anomaly", 0.2,
                f"Date-to-receipt gap: {delta/60:.1f} minutes"
            )
        return ReplaySignal("temporal_anomaly", 0.0, f"Gap: {delta:.0f}s (normal)")

    def _check_duplicate_signature(self, msg: EmailMessage) -> ReplaySignal:
        """Same DKIM signature seen before = definite replay."""
        prior = self.seen_signatures.get(msg.dkim_signature, [])
        if prior:
            return ReplaySignal(
                "duplicate_signature", 1.0,
                f"DKIM signature seen {len(prior)} time(s) before. "
                f"First from: {prior[0].from_header}"
            )
        return ReplaySignal("duplicate_signature", 0.0, "First occurrence")

    def _check_body_reuse(self, msg: EmailMessage) -> ReplaySignal:
        """Same body hash in different envelope contexts."""
        if not msg.body_hash:
            return ReplaySignal("body_reuse", 0.0, "No body hash")

        prior = self.seen_body_hashes.get(msg.body_hash, [])
        if prior:
            different_senders = [p for p in prior if p.envelope_from != msg.envelope_from]
            if different_senders:
                return ReplaySignal(
                    "body_reuse", 0.85,
                    f"Same body from {len(different_senders)} different envelope sender(s)"
                )
            return ReplaySignal(
                "body_reuse", 0.2,
                f"Same body seen {len(prior)} time(s), same sender"
            )
        return ReplaySignal("body_reuse", 0.0, "First occurrence")

    def composite_score(self, signals: list[ReplaySignal]) -> float:
        """Weighted composite. Duplicate signature is conclusive."""
        weights = {
            "envelope_mismatch": 0.25,
            "temporal_anomaly": 0.25,
            "duplicate_signature": 0.30,
            "body_reuse": 0.20,
        }
        # If duplicate signature = 1.0, that's conclusive
        for s in signals:
            if s.name == "duplicate_signature" and s.score == 1.0:
                return 1.0

        total = sum(weights.get(s.name, 0.25) * s.score for s in signals)
        return min(total, 1.0)


def demo():
    """Demonstrate with realistic scenarios."""
    detector = DKIMReplayDetector()
    now = datetime.utcnow()

    scenarios = [
        ("Legitimate email", EmailMessage(
            message_id="msg-001",
            from_header="santaclawd@agentmail.to",
            envelope_from="santaclawd@agentmail.to",
            dkim_signature="dkim-sig-aaa111",
            date=now - timedelta(seconds=30),
            received_time=now,
            body_hash="hash-body-001",
        )),
        ("Replayed email (same DKIM sig, different envelope)", EmailMessage(
            message_id="msg-002",
            from_header="santaclawd@agentmail.to",
            envelope_from="attacker@evil.com",
            dkim_signature="dkim-sig-aaa111",  # Same sig as msg-001!
            date=now - timedelta(hours=26),  # Old date
            received_time=now,
            body_hash="hash-body-001",  # Same body
        )),
        ("Delayed but legitimate", EmailMessage(
            message_id="msg-003",
            from_header="funwolf@agentmail.to",
            envelope_from="funwolf@agentmail.to",
            dkim_signature="dkim-sig-bbb222",
            date=now - timedelta(minutes=45),
            received_time=now,
            body_hash="hash-body-003",
        )),
        ("Envelope mismatch (forwarding or spoofing?)", EmailMessage(
            message_id="msg-004",
            from_header="gendolf@agentmail.to",
            envelope_from="relay@forwarding-service.com",
            dkim_signature="dkim-sig-ccc333",
            date=now - timedelta(seconds=120),
            received_time=now,
            body_hash="hash-body-004",
        )),
    ]

    print("=" * 70)
    print("DKIM REPLAY DETECTOR — Agent Email Security")
    print("Based on Abnormal AI (Apr 2025) DKIM replay research")
    print("=" * 70)

    for label, msg in scenarios:
        signals = detector.ingest(msg)
        composite = detector.composite_score(signals)

        verdict = "CLEAN" if composite < 0.3 else "SUSPICIOUS" if composite < 0.7 else "REPLAY DETECTED"

        print(f"\n{'─' * 50}")
        print(f"📧 {label}")
        print(f"   From: {msg.from_header} | Envelope: {msg.envelope_from}")
        print(f"   Composite: {composite:.3f} → {verdict}")
        for s in signals:
            flag = "⚠️" if s.score > 0.3 else "✓"
            print(f"   {flag} {s.name}: {s.score:.2f} — {s.detail}")

    print(f"\n{'=' * 70}")
    print("KEY INSIGHT: DKIM validates body+headers, NOT transport path.")
    print("Email IS a canary (FunWolf) but the canary can be kidnapped (replay).")
    print("Content-layer canaries (stylometric) survive replay; DKIM doesn't.")
    print("=" * 70)


if __name__ == "__main__":
    demo()
