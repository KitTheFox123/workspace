#!/usr/bin/env python3
"""
sla-bond-calculator.py — SLA bond sizing for agent liveness.

Per santaclawd: "trust stack detects unreachable agent but cannot compel uptime.
the missing primitive is an SLA bond."

Calculates bond size based on:
1. Declared uptime SLA (99%, 99.9%, etc.)
2. Historical reliability (from receipts)
3. Counterparty exposure (value at risk if agent goes down)
4. Bond forfeiture on sustained unreachability

Uses insurance math: bond = E[loss] × risk_multiplier + reserve
"""

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Optional
import math


@dataclass
class UptimeHistory:
    total_probes: int
    successful_probes: int
    longest_outage_minutes: int
    outage_count_30d: int
    
    @property
    def reliability(self) -> float:
        return self.successful_probes / max(self.total_probes, 1)
    
    @property
    def mtbf_hours(self) -> float:
        """Mean time between failures."""
        if self.outage_count_30d == 0:
            return 720.0  # 30 days
        return (30 * 24) / self.outage_count_30d


@dataclass
class SLAContract:
    declared_uptime: float  # e.g., 0.99
    max_outage_minutes: int  # e.g., 60
    counterparty_exposure: float  # value at risk in SOL
    bond_amount: float = 0.0
    
    def calculate_bond(self, history: UptimeHistory) -> dict:
        # Expected loss = P(outage) × exposure
        p_outage = 1 - history.reliability
        expected_loss = p_outage * self.counterparty_exposure
        
        # Risk multiplier: higher if declared SLA exceeds demonstrated reliability
        sla_gap = max(0, self.declared_uptime - history.reliability)
        risk_multiplier = 1.0 + (sla_gap * 10)  # 10x penalty per 10% gap
        
        # Outage severity: longest outage vs declared max
        outage_ratio = history.longest_outage_minutes / max(self.max_outage_minutes, 1)
        severity_factor = max(1.0, outage_ratio)
        
        # MTBF discount: frequent small outages worse than rare long ones
        mtbf_factor = max(0.5, min(2.0, 24.0 / max(history.mtbf_hours, 1)))
        
        # Bond = E[loss] × risk × severity × frequency + reserve
        reserve = self.counterparty_exposure * 0.05  # 5% minimum reserve
        bond = expected_loss * risk_multiplier * severity_factor * mtbf_factor + reserve
        
        # Cap at 2x exposure (no infinite bonds)
        bond = min(bond, self.counterparty_exposure * 2.0)
        
        self.bond_amount = round(bond, 6)
        
        # Forfeiture schedule
        forfeit_per_minute = bond / max(self.max_outage_minutes * 2, 1)
        
        # Grade
        if history.reliability >= self.declared_uptime and sla_gap == 0:
            grade = "A" if history.outage_count_30d <= 1 else "B"
        elif sla_gap < 0.02:
            grade = "C"
        elif sla_gap < 0.05:
            grade = "D"
        else:
            grade = "F"
        
        return {
            "bond_amount_sol": self.bond_amount,
            "declared_uptime": f"{self.declared_uptime*100:.1f}%",
            "actual_uptime": f"{history.reliability*100:.2f}%",
            "sla_gap": f"{sla_gap*100:.2f}%",
            "grade": grade,
            "risk_multiplier": round(risk_multiplier, 2),
            "expected_loss_sol": round(expected_loss, 6),
            "forfeit_per_minute_sol": round(forfeit_per_minute, 6),
            "mtbf_hours": round(history.mtbf_hours, 1),
            "longest_outage_min": history.longest_outage_minutes,
            "max_allowed_outage_min": self.max_outage_minutes,
            "counterparty_exposure_sol": self.counterparty_exposure,
            "verdict": "BONDED" if grade in ("A", "B") else "UNDERBONDED" if grade == "C" else "RISKY"
        }


def demo():
    # Scenario 1: Reliable agent, modest exposure
    reliable = SLAContract(
        declared_uptime=0.99,
        max_outage_minutes=60,
        counterparty_exposure=1.0
    )
    reliable_history = UptimeHistory(
        total_probes=1000, successful_probes=995,
        longest_outage_minutes=15, outage_count_30d=2
    )
    
    # Scenario 2: Agent claiming 99.9% but only delivering 95%
    overclaimer = SLAContract(
        declared_uptime=0.999,
        max_outage_minutes=10,
        counterparty_exposure=5.0
    )
    overclaim_history = UptimeHistory(
        total_probes=1000, successful_probes=950,
        longest_outage_minutes=120, outage_count_30d=8
    )
    
    # Scenario 3: New agent, no history
    new_agent = SLAContract(
        declared_uptime=0.95,
        max_outage_minutes=120,
        counterparty_exposure=0.5
    )
    new_history = UptimeHistory(
        total_probes=50, successful_probes=48,
        longest_outage_minutes=30, outage_count_30d=1
    )
    
    for name, contract, history in [
        ("reliable_agent", reliable, reliable_history),
        ("overclaiming_agent", overclaimer, overclaim_history),
        ("new_agent", new_agent, new_history)
    ]:
        result = contract.calculate_bond(history)
        print(f"\n{'='*50}")
        print(f"Scenario: {name}")
        print(f"Grade: {result['grade']} | Verdict: {result['verdict']}")
        print(f"Bond: {result['bond_amount_sol']} SOL")
        print(f"SLA: {result['declared_uptime']} declared, {result['actual_uptime']} actual (gap: {result['sla_gap']})")
        print(f"Risk multiplier: {result['risk_multiplier']}x | MTBF: {result['mtbf_hours']}h")
        print(f"Forfeit: {result['forfeit_per_minute_sol']} SOL/min of outage")
        print(f"Exposure: {result['counterparty_exposure_sol']} SOL")


if __name__ == "__main__":
    demo()
