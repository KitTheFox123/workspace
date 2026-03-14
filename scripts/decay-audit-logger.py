#!/usr/bin/env python3
"""
decay-audit-logger.py — Log trust vector consumption for S-constant calibration.

Inspired by riverholybot's comment on Moltbook: "log (t, R_computed, R_observed_utility)
and fit S over time." S constants should converge to empirical values, not stay hardcoded.

Records each trust vector read with:
- dimension, age_hours, S_used, R_computed
- observed_utility (did the trust decision turn out well?)
- After enough data, fit optimal S per dimension via least squares.

Usage: python3 decay-audit-logger.py
"""

import json
import math
import time
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class DecayAuditEntry:
    timestamp: str
    dimension: str  # T, G, A, S, C
    age_hours: float
    s_constant: float
    r_computed: float
    observed_utility: float = -1.0  # -1 = not yet observed, 0-1 = outcome quality

    def to_dict(self) -> dict:
        return {
            "ts": self.timestamp,
            "dim": self.dimension,
            "age_h": round(self.age_hours, 2),
            "S": self.s_constant,
            "R": round(self.r_computed, 4),
            "util": round(self.observed_utility, 4) if self.observed_utility >= 0 else None,
        }


class DecayAuditLog:
    """Append-only audit log for trust decay observations."""

    def __init__(self, log_path: str = "decay_audit.jsonl"):
        self.log_path = Path(log_path)
        self.entries: list[DecayAuditEntry] = []

    def record(self, dimension: str, age_hours: float, s_constant: float,
               observed_utility: float = -1.0) -> DecayAuditEntry:
        r = math.exp(-age_hours / s_constant) if s_constant > 0 else 0.0
        entry = DecayAuditEntry(
            timestamp=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            dimension=dimension,
            age_hours=age_hours,
            s_constant=s_constant,
            r_computed=r,
            observed_utility=observed_utility,
        )
        self.entries.append(entry)
        return entry

    def fit_optimal_s(self, dimension: str) -> dict:
        """Fit optimal S for a dimension using observed utility data.
        Minimizes sum((R_computed - observed_utility)^2) by varying S.
        """
        obs = [e for e in self.entries if e.dimension == dimension and e.observed_utility >= 0]
        if len(obs) < 3:
            return {"dimension": dimension, "status": "insufficient_data", "n": len(obs)}

        # Grid search over S values (brute force, good enough for small datasets)
        best_s = None
        best_error = float("inf")
        for s_candidate in [0.5, 1, 2, 4, 8, 12, 24, 48, 96, 168, 336, 720, 1440]:
            error = sum(
                (math.exp(-e.age_hours / s_candidate) * (e.r_computed / max(math.exp(-e.age_hours / e.s_constant), 0.001)) - e.observed_utility) ** 2
                for e in obs
            )
            if error < best_error:
                best_error = error
                best_s = s_candidate

        current_s = obs[0].s_constant
        return {
            "dimension": dimension,
            "current_S": current_s,
            "optimal_S": best_s,
            "error_reduction": round(1 - best_error / max(sum((e.r_computed - e.observed_utility) ** 2 for e in obs), 0.001), 3),
            "n": len(obs),
            "recommendation": "KEEP" if best_s == current_s else f"CHANGE S from {current_s} to {best_s}",
        }

    def save(self):
        with open(self.log_path, "a") as f:
            for entry in self.entries:
                f.write(json.dumps(entry.to_dict()) + "\n")

    def summary(self) -> str:
        dims = {}
        for e in self.entries:
            dims.setdefault(e.dimension, []).append(e)
        lines = ["=== Decay Audit Summary ==="]
        for dim, entries in sorted(dims.items()):
            observed = [e for e in entries if e.observed_utility >= 0]
            lines.append(f"  {dim}: {len(entries)} reads, {len(observed)} with utility feedback")
            if observed:
                avg_r = sum(e.r_computed for e in observed) / len(observed)
                avg_u = sum(e.observed_utility for e in observed) / len(observed)
                lines.append(f"     avg R={avg_r:.3f}, avg utility={avg_u:.3f}, gap={abs(avg_r - avg_u):.3f}")
        return "\n".join(lines)


def demo():
    print("=== Decay Audit Logger (riverholybot's S-calibration idea) ===\n")
    log = DecayAuditLog()

    # Simulate gossip reads at various ages with utility feedback
    # Good: fresh gossip was trustworthy
    log.record("G", 0.5, 4.0, observed_utility=0.95)
    log.record("G", 1.0, 4.0, observed_utility=0.90)
    log.record("G", 2.0, 4.0, observed_utility=0.75)
    log.record("G", 4.0, 4.0, observed_utility=0.40)  # R=0.37, utility=0.40 — close
    log.record("G", 8.0, 4.0, observed_utility=0.05)  # R=0.14, utility=0.05 — S too generous

    # Attestation reads
    log.record("A", 24, 720.0, observed_utility=0.95)
    log.record("A", 168, 720.0, observed_utility=0.85)
    log.record("A", 720, 720.0, observed_utility=0.50)  # R=0.37, utility=0.50 — S too aggressive

    # Tile proof (should never decay)
    log.record("T", 720, float("inf"), observed_utility=0.99)

    print(log.summary())
    print()

    # Fit optimal S for gossip
    fit_g = log.fit_optimal_s("G")
    print(f"Gossip S fit: {json.dumps(fit_g, indent=2)}")

    fit_a = log.fit_optimal_s("A")
    print(f"\nAttestation S fit: {json.dumps(fit_a, indent=2)}")


if __name__ == "__main__":
    demo()
