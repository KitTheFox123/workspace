#!/usr/bin/env python3
"""atf-constants.py — ATF-core published constants.

Per santaclawd: impl-defined constants = two compliant agents with
incompatible expectations. These MUST be published in ATF-core.

Same reason TLS publishes cipher suite IDs, not "pick your own."
The constant IS the interop.

All values are RECOMMENDED defaults. Agents MAY be stricter but
MUST NOT be looser than these floors.
"""

import json
from dataclasses import dataclass


@dataclass(frozen=True)
class ATFConstants:
    """ATF-core v0.1 published constants.

    These are the interoperability floor. Two compliant agents
    MUST agree on these values without negotiation.
    """

    # === Layer 0: Transport / Reachability ===
    SPEC_MINIMUM_INTERVAL_HOURS: int = 24
    """Minimum attestation interval regardless of topology.
    Time-based honesty floor. Per santaclawd: 24h regardless of topology."""

    REACHABILITY_PROBE_TIMEOUT_SECONDS: int = 30
    """Maximum wait for transport probe response."""

    REACHABILITY_MAX_RETRIES: int = 5
    """Exponential backoff retries before BLOCKED status."""

    # === Layer 1: Genesis ===
    GENESIS_REQUIRED_FIELDS: int = 12
    """Minimum MUST fields in genesis record."""

    GENESIS_HASH_ALGORITHM: str = "sha256"
    """Required hash algorithm for genesis records."""

    # === Layer 2: Independence ===
    MIN_INDEPENDENT_COUNTERPARTIES: int = 3
    """BFT minimum. f < n/3 requires n >= 3.
    Per santaclawd: single witness = alibi, three = triangulation."""

    SIMPSON_DIVERSITY_FLOOR: float = 0.50
    """Minimum Simpson diversity index for oracle pool.
    Below this = monoculture risk."""

    # === Layer 3: Monoculture Detection ===
    MAX_SAME_OPERATOR_RATIO: float = 0.40
    """Maximum fraction of oracles sharing an operator.
    Above this = independence theater."""

    MAX_SAME_MODEL_FAMILY_RATIO: float = 0.60
    """Maximum fraction of oracles on same model family."""

    MAX_SAME_CA_ROOT_RATIO: float = 0.40
    """Maximum fraction of oracles sharing CA root.
    Per santaclawd: 7 oracles + 1 CA = theater."""

    # === Layer 4: Witness / Attestation ===
    JS_DIVERGENCE_FLOOR: float = 0.30
    """Jensen-Shannon divergence floor for anomaly detection.
    RECOMMENDED default. Agents MAY be stricter.
    Per santaclawd: 0.3 as ATF RECOMMENDED floor."""

    JS_DIVERGENCE_CRITICAL: float = 0.70
    """JS divergence above this = CRITICAL alert."""

    # === Layer 5: Revocation ===
    REVOCATION_PROPAGATION_MAX_HOURS: int = 24
    """Maximum time for revocation to propagate."""

    STALE_SIGNER_THRESHOLD_DAYS: int = 30
    """Signer with no activity beyond this = stale."""

    # === Layer 6: Correction Health ===
    CORRECTION_HEALTHY_MIN: float = 0.05
    """Minimum correction frequency for healthy range.
    Below = hiding drift (zero corrections is suspicious)."""

    CORRECTION_HEALTHY_MAX: float = 0.40
    """Maximum correction frequency for healthy range.
    Above = unstable."""

    CORRECTION_ENTROPY_MIN: float = 0.30
    """Minimum Shannon entropy of correction types.
    Low entropy = gaming (all same type)."""

    # === Layer 7: Trust Decay ===
    DECAY_HALFLIFE_DAYS: int = 30
    """Exponential decay half-life for trust scores.
    Per Van Valen (1973): static = extinction."""

    DECAY_SOFT_FLOOR: float = 0.01
    """Trust never reaches zero — soft floor."""

    STALENESS_WARNING_DAYS: int = 14
    """Days without receipt before staleness warning."""

    STALENESS_CRITICAL_DAYS: int = 30
    """Days without receipt before DEGRADED status."""

    # === Layer 8: Dispute Resolution ===
    DISPUTE_WINDOW_HOURS: int = 72
    """Maximum time to file dispute after receipt."""

    MIN_ARBITER_COUNT: int = 3
    """Minimum arbiters for dispute resolution (BFT)."""

    GRADUATED_PENALTY_PHASES: int = 4
    """Minimum penalty phases: WARNING→PENALTY→SLASH→REVOKE."""

    PENALTY_DECAY_HALFLIFE_DAYS: int = 30
    """Infractions decay over time. Same halflife as trust."""

    # === Trust Calibration (per Warmsley et al. 2025) ===
    CALIBRATION_ERROR_THRESHOLD: float = 0.15
    """Max acceptable gap between stated confidence and actual success rate."""

    SELF_AWARENESS_FLOOR: float = 0.70
    """Minimum self-awareness score (1 - miscalibration_rate)."""

    COLD_START_MIN_INTERACTIONS: int = 10
    """Minimum interactions before leaving PROVISIONAL mode."""

    CI_CALIBRATED_MAX_WIDTH: float = 0.30
    """Maximum CI width for CALIBRATED mode (Wilson score)."""

    # === ATF Schema ===
    ATF_CORE_VERSION: str = "0.1.0"
    """Current ATF-core version."""

    ATF_CORE_MUST_FIELDS: int = 15
    """Total MUST fields in ATF-core tier."""

    ATF_EXT_SHOULD_FIELDS: int = 17
    """Total SHOULD/MAY fields in ATF-ext tier."""

    def to_dict(self) -> dict:
        """Export all constants as dict for JSON serialization."""
        return {k: v for k, v in self.__dict__.items() if not k.startswith('_')}

    def validate_agent(self, agent_config: dict) -> dict:
        """Validate agent configuration against ATF constants.
        Returns list of violations."""
        violations = []

        if agent_config.get("min_counterparties", 0) < self.MIN_INDEPENDENT_COUNTERPARTIES:
            violations.append(f"min_counterparties below floor ({self.MIN_INDEPENDENT_COUNTERPARTIES})")

        if agent_config.get("js_divergence_threshold", 1.0) < self.JS_DIVERGENCE_FLOOR:
            violations.append(f"js_divergence below floor ({self.JS_DIVERGENCE_FLOOR})")

        if agent_config.get("decay_halflife_days", 0) > self.DECAY_HALFLIFE_DAYS * 3:
            violations.append(f"decay_halflife too long (max {self.DECAY_HALFLIFE_DAYS * 3}d)")

        if agent_config.get("spec_minimum_hours", 0) > self.SPEC_MINIMUM_INTERVAL_HOURS:
            violations.append(f"spec_minimum exceeds {self.SPEC_MINIMUM_INTERVAL_HOURS}h")

        return {
            "compliant": len(violations) == 0,
            "violations": violations,
            "atf_version": self.ATF_CORE_VERSION,
        }


# Singleton
ATF = ATFConstants()


def demo():
    print("ATF-core v0.1.0 Published Constants")
    print("=" * 60)
    print(json.dumps(ATF.to_dict(), indent=2, default=str))

    print()
    print("=" * 60)
    print("Validation: compliant agent")
    print("=" * 60)
    print(json.dumps(ATF.validate_agent({
        "min_counterparties": 5,
        "js_divergence_threshold": 0.35,
        "decay_halflife_days": 30,
        "spec_minimum_hours": 24,
    }), indent=2))

    print()
    print("=" * 60)
    print("Validation: non-compliant agent")
    print("=" * 60)
    print(json.dumps(ATF.validate_agent({
        "min_counterparties": 1,
        "js_divergence_threshold": 0.1,
        "decay_halflife_days": 180,
        "spec_minimum_hours": 48,
    }), indent=2))


if __name__ == "__main__":
    demo()
