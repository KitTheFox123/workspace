#!/usr/bin/env python3
"""Trust Debt Calculator — quantify the cost of missing audit trails.

Trust debt = risk exposure from unattested actions. Like tech debt but
the interest rate spikes at breach time.

Based on:
- santaclawd: "trust debt callable at the worst moment"
- Akerlof 1970: type II errors cause good actor exodus
- W3C Trace Context: propagation headers as lineage model

Usage:
  python trust-debt-calculator.py --demo
  echo '{"actions": [...]}' | python trust-debt-calculator.py --json
"""

import json
import sys
import math
from datetime import datetime, timedelta

# Action risk by type
ACTION_RISK = {
    "payment": 0.9,        # Financial = high risk
    "delivery": 0.7,       # Service delivery
    "delegation": 0.8,     # Sub-agent actions
    "communication": 0.4,  # Messages
    "internal": 0.2,       # Self-only actions
}

# Attestation coverage reduces debt
ATTESTATION_COVERAGE = {
    "x402_receipt": 0.35,
    "dkim_verified": 0.25,
    "gen_sig": 0.20,
    "isnad_chain": 0.30,
    "witness": 0.15,
    "hash_anchor": 0.10,
}


def calculate_action_debt(action: dict) -> dict:
    """Calculate trust debt for a single action."""
    action_type = action.get("type", "internal")
    value = action.get("value_usd", 1.0)
    base_risk = ACTION_RISK.get(action_type, 0.3)
    
    # Attestations reduce debt
    attestations = action.get("attestations", [])
    coverage = sum(ATTESTATION_COVERAGE.get(a, 0) for a in attestations)
    coverage = min(0.95, coverage)  # Can't fully eliminate
    
    # Raw debt = risk × value
    raw_debt = base_risk * value
    
    # Actual debt = raw × (1 - coverage)
    actual_debt = raw_debt * (1 - coverage)
    
    # Interest: unattested debt compounds (1% per day)
    age_days = action.get("age_days", 0)
    compounded = actual_debt * (1.01 ** age_days)
    
    # Breach multiplier: at incident time, unattested actions cost 5-10x
    breach_cost = actual_debt * 7  # Average multiplier
    
    return {
        "type": action_type,
        "value": value,
        "base_risk": base_risk,
        "attestation_coverage": round(coverage, 3),
        "raw_debt": round(raw_debt, 3),
        "current_debt": round(compounded, 3),
        "breach_cost": round(breach_cost, 3),
        "status": "COVERED" if coverage > 0.7 else "PARTIAL" if coverage > 0.3 else "EXPOSED",
    }


def portfolio_analysis(actions: list) -> dict:
    """Analyze trust debt across a portfolio of actions."""
    debts = [calculate_action_debt(a) for a in actions]
    
    total_value = sum(d["value"] for d in debts)
    total_debt = sum(d["current_debt"] for d in debts)
    total_breach = sum(d["breach_cost"] for d in debts)
    
    exposed = [d for d in debts if d["status"] == "EXPOSED"]
    covered = [d for d in debts if d["status"] == "COVERED"]
    
    # Akerlof metric: what % of value is unattested?
    # High unattested % → good actors leave → market collapse
    exposed_value = sum(d["value"] for d in exposed)
    akerlof_risk = exposed_value / total_value if total_value > 0 else 0
    
    # Grade
    debt_ratio = total_debt / total_value if total_value > 0 else 0
    grade = "A" if debt_ratio < 0.1 else "B" if debt_ratio < 0.25 else "C" if debt_ratio < 0.5 else "D" if debt_ratio < 0.75 else "F"
    
    return {
        "action_count": len(debts),
        "total_value": round(total_value, 2),
        "total_current_debt": round(total_debt, 2),
        "total_breach_cost": round(total_breach, 2),
        "debt_ratio": round(debt_ratio, 3),
        "exposed_count": len(exposed),
        "covered_count": len(covered),
        "akerlof_risk": round(akerlof_risk, 3),
        "grade": grade,
        "actions": debts,
        "recommendation": (
            "CRITICAL: High Akerlof risk. Good actors will exit." if akerlof_risk > 0.5
            else "WARNING: Significant trust debt accumulating." if debt_ratio > 0.3
            else "HEALTHY: Most actions attested. Maintain coverage."
        ),
    }


def demo():
    print("=" * 60)
    print("Trust Debt Calculator")
    print("=" * 60)
    
    # Well-attested portfolio
    good = [
        {"type": "payment", "value_usd": 10.0, "attestations": ["x402_receipt", "dkim_verified"], "age_days": 5},
        {"type": "delivery", "value_usd": 50.0, "attestations": ["gen_sig", "isnad_chain", "witness"], "age_days": 3},
        {"type": "delegation", "value_usd": 5.0, "attestations": ["isnad_chain", "gen_sig"], "age_days": 1},
        {"type": "communication", "value_usd": 1.0, "attestations": ["dkim_verified"], "age_days": 7},
    ]
    
    print("\n--- Well-Attested Agent ---")
    r = portfolio_analysis(good)
    print(f"Grade: {r['grade']} | Debt ratio: {r['debt_ratio']:.1%}")
    print(f"Total value: ${r['total_value']} | Current debt: ${r['total_current_debt']}")
    print(f"Breach cost: ${r['total_breach_cost']} | Akerlof risk: {r['akerlof_risk']:.1%}")
    print(f"→ {r['recommendation']}")
    
    # Unattested portfolio
    bad = [
        {"type": "payment", "value_usd": 10.0, "attestations": [], "age_days": 30},
        {"type": "delivery", "value_usd": 50.0, "attestations": [], "age_days": 14},
        {"type": "delegation", "value_usd": 25.0, "attestations": [], "age_days": 7},
        {"type": "communication", "value_usd": 5.0, "attestations": [], "age_days": 60},
    ]
    
    print("\n--- Unattested Agent (Trust Debt) ---")
    r = portfolio_analysis(bad)
    print(f"Grade: {r['grade']} | Debt ratio: {r['debt_ratio']:.1%}")
    print(f"Total value: ${r['total_value']} | Current debt: ${r['total_current_debt']}")
    print(f"Breach cost: ${r['total_breach_cost']} | Akerlof risk: {r['akerlof_risk']:.1%}")
    print(f"→ {r['recommendation']}")
    
    # Mixed portfolio (tc3 style)
    mixed = [
        {"type": "payment", "value_usd": 0.50, "attestations": ["x402_receipt"], "age_days": 2},
        {"type": "delivery", "value_usd": 20.0, "attestations": ["gen_sig", "dkim_verified"], "age_days": 2},
        {"type": "delegation", "value_usd": 5.0, "attestations": [], "age_days": 2},
        {"type": "communication", "value_usd": 2.0, "attestations": ["dkim_verified"], "age_days": 1},
    ]
    
    print("\n--- TC3-Style (Mixed Coverage) ---")
    r = portfolio_analysis(mixed)
    print(f"Grade: {r['grade']} | Debt ratio: {r['debt_ratio']:.1%}")
    print(f"Total value: ${r['total_value']} | Current debt: ${r['total_current_debt']}")
    print(f"Breach cost: ${r['total_breach_cost']} | Akerlof risk: {r['akerlof_risk']:.1%}")
    print(f"Exposed: {r['exposed_count']}/{r['action_count']} actions")
    print(f"→ {r['recommendation']}")


if __name__ == "__main__":
    if "--json" in sys.argv:
        data = json.load(sys.stdin)
        print(json.dumps(portfolio_analysis(data.get("actions", [])), indent=2))
    else:
        demo()
