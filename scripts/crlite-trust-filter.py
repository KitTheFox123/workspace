#!/usr/bin/env python3
"""
crlite-trust-filter.py — CRLite-inspired compressed trust revocation for agents.

Mozilla's CRLite (Firefox 137, Aug 2025) compresses 4M revoked certificates
into 300KB/day using Clubcard filters (partitioned two-level cascade of
Ribbon filters). This tool applies the same pattern to agent trust:

Problem parallels:
  - CRL (pull list) = checking agent reputation on demand (stale, expensive)
  - OCSP (real-time query) = asking oracle per-transaction (latency + privacy leak)
  - CRLite (compressed local filter) = periodic compact download, local lookup

Key insight from Mozilla: "There is no reliable way to distinguish
security-critical revocations from administrative revocations."
→ Check ALL revocations. Soft-fail is theater.

This uses a Bloom filter as a simplified stand-in for Clubcard/Ribbon filters.
Production would use the actual Clubcard library (github.com/mozilla/clubcard).

Usage:
    python3 crlite-trust-filter.py
"""

import hashlib
import json
import math
import time
from dataclasses import dataclass, field


class BloomFilter:
    """Simple Bloom filter for revocation checking."""

    def __init__(self, expected_items: int = 10000, fp_rate: float = 0.001):
        self.size = self._optimal_size(expected_items, fp_rate)
        self.hash_count = self._optimal_hashes(self.size, expected_items)
        self.bits = bytearray(math.ceil(self.size / 8))
        self.item_count = 0

    @staticmethod
    def _optimal_size(n: int, p: float) -> int:
        return int(-n * math.log(p) / (math.log(2) ** 2))

    @staticmethod
    def _optimal_hashes(m: int, n: int) -> int:
        return max(1, int((m / n) * math.log(2)))

    def _hashes(self, item: str) -> list[int]:
        h1 = int(hashlib.sha256(item.encode()).hexdigest(), 16)
        h2 = int(hashlib.md5(item.encode()).hexdigest(), 16)
        return [(h1 + i * h2) % self.size for i in range(self.hash_count)]

    def add(self, item: str):
        for pos in self._hashes(item):
            self.bits[pos // 8] |= 1 << (pos % 8)
        self.item_count += 1

    def __contains__(self, item: str) -> bool:
        return all(
            self.bits[pos // 8] & (1 << (pos % 8))
            for pos in self._hashes(item)
        )

    def size_bytes(self) -> int:
        return len(self.bits)


@dataclass
class RevocationEntry:
    agent_id: str
    genesis_hash: str
    reason: str  # KEY_COMPROMISE, AFFILIATION_CHANGED, SUPERSEDED, UNSPECIFIED
    revoked_at: float
    severity: str  # CRITICAL, WARNING, ADMINISTRATIVE


@dataclass
class TrustFilter:
    """CRLite-style compressed trust filter for agent networks."""

    version: int = 0
    created_at: float = field(default_factory=time.time)
    filter_: BloomFilter = field(default_factory=lambda: BloomFilter(10000, 0.001))
    revocations: list[RevocationEntry] = field(default_factory=list)
    update_interval_hours: int = 12  # Match CRLite's 12h cadence

    def revoke(self, agent_id: str, genesis_hash: str, reason: str = "UNSPECIFIED"):
        severity = {
            "KEY_COMPROMISE": "CRITICAL",
            "AFFILIATION_CHANGED": "WARNING",
            "SUPERSEDED": "ADMINISTRATIVE",
            "UNSPECIFIED": "WARNING",  # Mozilla: can't distinguish, treat as warning
        }.get(reason, "WARNING")

        entry = RevocationEntry(
            agent_id=agent_id,
            genesis_hash=genesis_hash,
            reason=reason,
            revoked_at=time.time(),
            severity=severity,
        )
        self.revocations.append(entry)

        # Add to bloom filter: agent_id + genesis_hash
        self.filter_.add(f"{agent_id}:{genesis_hash}")
        self.version += 1

    def is_revoked(self, agent_id: str, genesis_hash: str) -> dict:
        """Local lookup — no network request, no privacy leak."""
        key = f"{agent_id}:{genesis_hash}"
        in_filter = key in self.filter_

        if not in_filter:
            return {
                "revoked": False,
                "method": "CRLITE_LOCAL",
                "latency": "0ms",
                "privacy_leak": False,
            }

        # Bloom filter positive — could be false positive
        # In production: check against delta updates or full list
        entry = next(
            (r for r in self.revocations
             if r.agent_id == agent_id and r.genesis_hash == genesis_hash),
            None
        )

        if entry:
            return {
                "revoked": True,
                "method": "CRLITE_LOCAL",
                "reason": entry.reason,
                "severity": entry.severity,
                "revoked_at": entry.revoked_at,
                "latency": "0ms",
                "privacy_leak": False,
            }

        return {
            "revoked": False,
            "method": "CRLITE_LOCAL",
            "note": "bloom_false_positive",
            "latency": "0ms",
            "privacy_leak": False,
        }

    def compare_methods(self, agent_id: str, genesis_hash: str) -> dict:
        """Compare CRLite-style vs CRL vs OCSP approaches."""
        crlite = self.is_revoked(agent_id, genesis_hash)

        return {
            "crlite_local": {
                **crlite,
                "bandwidth": f"{self.filter_.size_bytes()} bytes (shared filter)",
                "update_cadence": f"{self.update_interval_hours}h",
                "coverage": "ALL revocations",
            },
            "crl_pull": {
                "method": "CRL_PULL",
                "latency": "~500ms (download + parse)",
                "privacy_leak": False,
                "bandwidth": "300MB total (all CAs)",
                "staleness": "hours to days",
                "coverage": "ALL revocations (if downloaded)",
                "problem": "too big to download frequently",
            },
            "ocsp_realtime": {
                "method": "OCSP_REALTIME",
                "latency": "~100ms (network round-trip)",
                "privacy_leak": True,
                "privacy_leak_detail": "query reveals which agent you're about to interact with",
                "bandwidth": "~1KB per query",
                "coverage": "per-query (if CA responds)",
                "problem": "soft-fail = theater, privacy leak, latency",
            },
            "verdict": "CRLITE_LOCAL wins: zero latency, zero privacy leak, full coverage",
        }

    def stats(self) -> dict:
        return {
            "version": self.version,
            "total_revocations": len(self.revocations),
            "filter_size_bytes": self.filter_.size_bytes(),
            "filter_size_kb": round(self.filter_.size_bytes() / 1024, 1),
            "compression_ratio": f"{len(self.revocations) * 100 / max(1, self.filter_.size_bytes()):.1f} entries/KB",
            "update_cadence_hours": self.update_interval_hours,
            "by_reason": {},
            "by_severity": {},
        }


def demo():
    print("=" * 60)
    print("CRLite Trust Filter — Mozilla's pattern for agent revocation")
    print("=" * 60)

    tf = TrustFilter()

    # Simulate revocations
    revocations = [
        ("compromised_bot", "gen_comp01", "KEY_COMPROMISE"),
        ("old_version", "gen_old01", "SUPERSEDED"),
        ("left_org", "gen_left01", "AFFILIATION_CHANGED"),
        ("unknown_reason", "gen_unk01", "UNSPECIFIED"),
        ("sybil_001", "gen_syb01", "KEY_COMPROMISE"),
        ("sybil_002", "gen_syb02", "KEY_COMPROMISE"),
        ("sybil_003", "gen_syb03", "KEY_COMPROMISE"),
        ("admin_cleanup", "gen_adm01", "ADMINISTRATIVE"),
    ]

    for agent_id, genesis, reason in revocations:
        tf.revoke(agent_id, genesis, reason)

    # Check various agents
    print("\n--- Revocation checks (local, zero-latency) ---")
    checks = [
        ("compromised_bot", "gen_comp01"),  # Should be revoked
        ("legitimate_agent", "gen_legit01"),  # Should be clean
        ("sybil_002", "gen_syb02"),  # Should be revoked
        ("unknown_agent", "gen_unknown"),  # Should be clean
    ]

    for agent_id, genesis in checks:
        result = tf.is_revoked(agent_id, genesis)
        status = "REVOKED" if result["revoked"] else "CLEAN"
        print(f"  {agent_id}: {status} (method={result['method']}, privacy_leak={result['privacy_leak']})")

    # Compare methods
    print("\n--- Method comparison: compromised_bot ---")
    comparison = tf.compare_methods("compromised_bot", "gen_comp01")
    for method, details in comparison.items():
        if method == "verdict":
            print(f"\n  VERDICT: {details}")
        else:
            print(f"\n  {method}:")
            if isinstance(details, dict):
                for k, v in details.items():
                    print(f"    {k}: {v}")

    # Stats
    print("\n--- Filter stats ---")
    stats = tf.stats()
    print(json.dumps(stats, indent=2))

    # Soft-fail demonstration
    print("\n--- Soft-fail is theater ---")
    print("  OCSP timeout scenario:")
    print("    Browser: 'OCSP server didn't respond in 3s, proceeding anyway'")
    print("    Reality: Attacker blocked OCSP response. Revoked cert accepted.")
    print("    Mozilla (2025): 'OCSP soft-fail meant revocation was non-functional for 15+ years'")
    print("  ")
    print("  CRLite equivalent:")
    print("    Agent: 'Filter loaded locally. No network needed. No soft-fail possible.'")
    print("    Revoked = revoked. No timeout. No fallback. No theater.")

    print("\n" + "=" * 60)
    print("CRL→OCSP→OCSP Stapling→CRLite: 30-year arc.")
    print("Pull fails. Real-time leaks. Push is too big.")
    print("Compressed-push-with-local-query wins. Every time.")
    print("=" * 60)


if __name__ == "__main__":
    demo()
