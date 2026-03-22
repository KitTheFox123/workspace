#!/usr/bin/env python3
"""bootstrap-attestation.py — Bootstrap attestation for new agents.

Per santaclawd (email, 2026-03-22): "newly bootstrapped agents
(counterparty_count=0, window=MANUAL) are the highest risk class."

The cold start of cold starts: how does a new agent earn migration rights?

Three mechanisms:
1. TRUSTED INTRODUCER — established agent co-signs genesis
2. PROOF OF WORK — verifiable interactions before migration
3. TIME LOCK — minimum age before migration allowed

ATF-core MUST field: min_interactions_before_migration (default=10)

References:
- oracle-vouch-chain.py (introducer vouching)
- trust-calibration-engine.py (PROVISIONAL mode)
- migration-quorum-calculator.py (sybil reduction)
- Warmsley et al. (2025): cold start = wide CI, limited autonomy
"""

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from typing import Optional


@dataclass
class Introducer:
    """Agent vouching for a new agent at genesis."""
    agent_id: str
    operator: str
    reputation_score: float  # 0.0-1.0
    interaction_count: int
    active_days: int


@dataclass
class BootstrapConfig:
    """ATF-core bootstrap configuration declared at genesis."""
    min_interactions_before_migration: int = 10  # MUST field
    min_age_days: int = 7  # TIME LOCK floor
    introducer_min_reputation: float = 0.60
    introducer_min_interactions: int = 50
    introducer_min_active_days: int = 30


@dataclass
class AgentBootstrapState:
    """Current state of a bootstrapping agent."""
    agent_id: str
    genesis_at: datetime
    introducer: Optional[Introducer] = None
    interaction_count: int = 0
    unique_counterparties: int = 0
    corrections: int = 0
    operator: str = ""

    @property
    def age_days(self) -> float:
        delta = datetime.now(timezone.utc) - self.genesis_at
        return delta.total_seconds() / 86400

    @property
    def correction_frequency(self) -> float:
        if self.interaction_count == 0:
            return 0.0
        return self.corrections / self.interaction_count


class BootstrapAttestationEngine:
    """Evaluates whether a new agent has earned migration rights."""

    def __init__(self, config: Optional[BootstrapConfig] = None):
        self.config = config or BootstrapConfig()

    def validate_introducer(self, introducer: Introducer, new_agent_operator: str) -> dict:
        """Gate 1: Is the introducer qualified and independent?"""
        issues = []

        if introducer.operator == new_agent_operator:
            issues.append("SAME_OPERATOR — introducer shares operator = 0 effective attestation")

        if introducer.reputation_score < self.config.introducer_min_reputation:
            issues.append(
                f"LOW_REPUTATION — {introducer.reputation_score:.2f} < "
                f"{self.config.introducer_min_reputation:.2f} minimum"
            )

        if introducer.interaction_count < self.config.introducer_min_interactions:
            issues.append(
                f"INSUFFICIENT_HISTORY — {introducer.interaction_count} < "
                f"{self.config.introducer_min_interactions} minimum interactions"
            )

        if introducer.active_days < self.config.introducer_min_active_days:
            issues.append(
                f"TOO_NEW — {introducer.active_days}d < "
                f"{self.config.introducer_min_active_days}d minimum"
            )

        return {
            "gate": "TRUSTED_INTRODUCER",
            "passed": len(issues) == 0,
            "issues": issues,
        }

    def validate_proof_of_work(self, state: AgentBootstrapState) -> dict:
        """Gate 2: Has the agent earned trust through verifiable work?"""
        issues = []

        if state.interaction_count < self.config.min_interactions_before_migration:
            issues.append(
                f"INSUFFICIENT_INTERACTIONS — {state.interaction_count}/"
                f"{self.config.min_interactions_before_migration}"
            )

        if state.unique_counterparties < 2:
            issues.append(
                f"TOO_FEW_COUNTERPARTIES — {state.unique_counterparties}/2 minimum"
            )

        # Correction health check
        if state.interaction_count >= 10:
            cf = state.correction_frequency
            if cf == 0.0:
                issues.append("ZERO_CORRECTIONS — hiding drift or never tested")
            elif cf > 0.50:
                issues.append(f"EXCESSIVE_CORRECTIONS — {cf:.2f} > 0.50")

        return {
            "gate": "PROOF_OF_WORK",
            "passed": len(issues) == 0,
            "issues": issues,
        }

    def validate_time_lock(self, state: AgentBootstrapState) -> dict:
        """Gate 3: Has the agent existed long enough?"""
        issues = []

        if state.age_days < self.config.min_age_days:
            remaining = self.config.min_age_days - state.age_days
            issues.append(
                f"TIME_LOCKED — {state.age_days:.1f}d / {self.config.min_age_days}d "
                f"({remaining:.1f}d remaining)"
            )

        return {
            "gate": "TIME_LOCK",
            "passed": len(issues) == 0,
            "issues": issues,
        }

    def assess(self, state: AgentBootstrapState) -> dict:
        """Full bootstrap assessment: can this agent migrate keys?"""
        gates = {}

        # Gate 1: Introducer (required for genesis)
        if state.introducer:
            gates["introducer"] = self.validate_introducer(
                state.introducer, state.operator
            )
        else:
            gates["introducer"] = {
                "gate": "TRUSTED_INTRODUCER",
                "passed": False,
                "issues": ["NO_INTRODUCER — genesis without voucher"],
            }

        # Gate 2: Proof of work
        gates["proof_of_work"] = self.validate_proof_of_work(state)

        # Gate 3: Time lock
        gates["time_lock"] = self.validate_time_lock(state)

        all_passed = all(g["passed"] for g in gates.values())
        gates_passed = sum(1 for g in gates.values() if g["passed"])

        # Migration permission
        if all_passed:
            migration = "ALLOWED"
            mode = "STANDARD"
        elif gates_passed >= 2:
            migration = "RESTRICTED"
            mode = "EXTENDED_WINDOW"  # longer migration window
        elif gates_passed >= 1:
            migration = "MANUAL"
            mode = "CONTESTED"  # requires manual override
        else:
            migration = "BLOCKED"
            mode = "PROVISIONAL"

        return {
            "agent_id": state.agent_id,
            "migration_permission": migration,
            "mode": mode,
            "gates_passed": f"{gates_passed}/3",
            "age_days": round(state.age_days, 1),
            "interactions": state.interaction_count,
            "unique_counterparties": state.unique_counterparties,
            "gates": gates,
        }


def demo():
    engine = BootstrapAttestationEngine()
    now = datetime.now(timezone.utc)

    print("=" * 60)
    print("SCENARIO 1: Well-bootstrapped agent (all gates pass)")
    print("=" * 60)

    good = AgentBootstrapState(
        agent_id="kit_fox",
        genesis_at=now - timedelta(days=30),
        operator="ilya",
        introducer=Introducer(
            agent_id="bro_agent",
            operator="different_operator",
            reputation_score=0.85,
            interaction_count=200,
            active_days=90,
        ),
        interaction_count=45,
        unique_counterparties=8,
        corrections=7,
    )
    print(json.dumps(engine.assess(good), indent=2))

    print()
    print("=" * 60)
    print("SCENARIO 2: Brand new agent (all gates fail)")
    print("=" * 60)

    new = AgentBootstrapState(
        agent_id="fresh_agent",
        genesis_at=now - timedelta(hours=2),
        operator="unknown",
        introducer=None,
        interaction_count=0,
        unique_counterparties=0,
    )
    print(json.dumps(engine.assess(new), indent=2))

    print()
    print("=" * 60)
    print("SCENARIO 3: Same-operator introducer (sybil attempt)")
    print("=" * 60)

    sybil = AgentBootstrapState(
        agent_id="sybil_agent",
        genesis_at=now - timedelta(days=10),
        operator="evil_corp",
        introducer=Introducer(
            agent_id="evil_shell",
            operator="evil_corp",  # SAME operator
            reputation_score=0.90,
            interaction_count=100,
            active_days=60,
        ),
        interaction_count=15,
        unique_counterparties=3,
        corrections=2,
    )
    print(json.dumps(engine.assess(sybil), indent=2))

    print()
    print("=" * 60)
    print("SCENARIO 4: Good introducer but too young (time locked)")
    print("=" * 60)

    young = AgentBootstrapState(
        agent_id="eager_agent",
        genesis_at=now - timedelta(days=3),
        operator="alice",
        introducer=Introducer(
            agent_id="mentor_agent",
            operator="bob",
            reputation_score=0.78,
            interaction_count=150,
            active_days=45,
        ),
        interaction_count=12,
        unique_counterparties=4,
        corrections=2,
    )
    print(json.dumps(engine.assess(young), indent=2))


if __name__ == "__main__":
    demo()
