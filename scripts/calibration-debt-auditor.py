#!/usr/bin/env python3
"""calibration-debt-auditor.py — Audit trust systems for calibration debt.

"Calibration debt" (santaclawd, Mar 30 2026): systems built on overcalibrated
behavioral economics findings accumulate silent errors as those findings fail
to replicate. Like technical debt (Cunningham 1992) but for empirical parameters.

Audits trust system parameters against replication-adjusted values.

Sources:
- Yechiam & Zeif (2025, J Econ Psych 107:102801): λ=1.07 not 2.25
- Li et al (2025, Econ Inquiry 63:2): anchoring 3.4% not 31%
- Inzlicht & Friese (2019): ego depletion d≈0 not 0.62
- Hreha (2020, The Behavioral Scientist): "behavioral economics is dead"
- Open Science Collab (2015, Science): 39% of 100 psych studies replicated
- Cunningham (1992): technical debt metaphor

Kit 🦊 | 2026-03-30
"""

import json
from dataclasses import dataclass

@dataclass
class Parameter:
    name: str
    original_value: float
    original_source: str
    replicated_value: float
    replication_source: str
    system_value: float  # what the trust system currently uses
    description: str

# Known overcalibrated parameters in behavioral econ
PARAMETER_DB = [
    Parameter(
        name="loss_aversion_lambda",
        original_value=2.25,
        original_source="Kahneman & Tversky (1992)",
        replicated_value=1.07,
        replication_source="Yechiam & Zeif (2025, n=149,218)",
        system_value=2.25,  # default: many systems still use this
        description="Loss/gain asymmetry multiplier"
    ),
    Parameter(
        name="anchoring_effect_size",
        original_value=0.31,
        original_source="Various (meta-analytic)",
        replicated_value=0.034,
        replication_source="Li et al (2025, 96% power)",
        system_value=0.31,
        description="Anchoring effect on judgment (%)"
    ),
    Parameter(
        name="ego_depletion_d",
        original_value=0.62,
        original_source="Hagger et al (2010, meta)",
        replicated_value=0.04,
        replication_source="Inzlicht & Friese (2019, 23-lab RRR)",
        system_value=0.62,
        description="Self-control depletion effect size"
    ),
    Parameter(
        name="endowment_effect_ratio",
        original_value=2.0,
        original_source="Kahneman, Knetsch & Thaler (1990)",
        replicated_value=1.3,
        replication_source="Zeiler & Plott (2005); Walasek et al (2024)",
        system_value=2.0,
        description="WTA/WTP ratio for owned goods"
    ),
    Parameter(
        name="priming_effect_d",
        original_value=0.80,
        original_source="Bargh, Chen & Burrows (1996)",
        replicated_value=0.00,
        replication_source="Doyen et al (2012, RRR failure)",
        system_value=0.50,
        description="Social priming on behavior"
    ),
]


def compute_calibration_debt(params: list[Parameter]) -> dict:
    """Compute calibration debt for a set of parameters."""
    
    total_debt = 0.0
    debts = []
    
    for p in params:
        # Debt = distance between system value and replicated value,
        # normalized by original value
        if p.original_value == 0:
            inflation = float('inf')
        else:
            inflation = p.original_value / max(p.replicated_value, 0.001)
        
        # How much of the inflation the system still carries
        if p.original_value == p.replicated_value:
            carried = 0.0
        else:
            carried = (p.system_value - p.replicated_value) / (p.original_value - p.replicated_value)
        carried = max(0, min(1, carried))
        
        # Debt = carried fraction of total inflation
        debt = carried * inflation
        total_debt += debt
        
        debts.append({
            "parameter": p.name,
            "inflation_ratio": round(inflation, 2),
            "carried_fraction": round(carried, 3),
            "debt_score": round(debt, 3),
            "recommendation": f"Update from {p.system_value} → {p.replicated_value}",
            "replication_source": p.replication_source,
        })
    
    # Sort by debt (worst first)
    debts.sort(key=lambda d: d["debt_score"], reverse=True)
    
    return {
        "total_debt": round(total_debt, 3),
        "parameter_count": len(params),
        "mean_debt": round(total_debt / len(params), 3),
        "worst_parameter": debts[0]["parameter"],
        "parameters": debts,
        "rating": _rate_debt(total_debt / len(params)),
    }


def _rate_debt(mean_debt: float) -> str:
    if mean_debt < 0.5:
        return "LOW — system uses replicated values"
    elif mean_debt < 2.0:
        return "MODERATE — some overcalibrated parameters"
    elif mean_debt < 5.0:
        return "HIGH — significant calibration debt"
    else:
        return "CRITICAL — system built on zombie findings"


def compute_sybil_advantage(params: list[Parameter]) -> dict:
    """How much do sybils benefit from overcalibrated parameters?
    
    Key insight: overcalibrated loss aversion means honest failures
    are punished MORE than they should be. Sybils with perfect records
    (no failures to penalize) benefit from the asymmetry.
    """
    
    honest_penalty_original = sum(
        p.system_value for p in params 
        if "loss" in p.name or "endowment" in p.name
    )
    honest_penalty_replicated = sum(
        p.replicated_value for p in params
        if "loss" in p.name or "endowment" in p.name
    )
    
    if honest_penalty_replicated > 0:
        overpunishment = honest_penalty_original / honest_penalty_replicated
    else:
        overpunishment = 0
    
    return {
        "overpunishment_ratio": round(overpunishment, 2),
        "interpretation": (
            f"Honest agents penalized {overpunishment:.1f}x more than warranted. "
            f"Sybils with clean records avoid ALL penalties."
        ),
        "fix": "Use replicated λ (1.0-1.3) and symmetric evaluation"
    }


def replication_cascade(base_rate: float = 0.39) -> dict:
    """Model cascade effect: if 39% of psych findings replicate (OSC 2015),
    what happens to systems using N parameters from that literature?
    
    P(all N params valid) = base_rate^N
    """
    results = {}
    for n in [1, 3, 5, 10, 20]:
        p_all_valid = base_rate ** n
        results[f"n={n}"] = {
            "p_all_valid": round(p_all_valid, 6),
            "expected_zombie_params": round(n * (1 - base_rate), 1),
        }
    return {
        "base_replication_rate": base_rate,
        "source": "Open Science Collaboration (2015, Science 349:aac4716)",
        "cascade": results,
        "insight": (
            "A system using 5 behavioral econ parameters has only "
            f"{(base_rate**5)*100:.2f}% chance ALL are valid. "
            f"Expected zombie parameters: {5*(1-base_rate):.1f}."
        )
    }


if __name__ == "__main__":
    print("=" * 60)
    print("CALIBRATION DEBT AUDITOR")
    print("=" * 60)
    
    # Audit with default (overcalibrated) values
    print("\n## Default System (using original values)")
    result = compute_calibration_debt(PARAMETER_DB)
    print(f"Total debt: {result['total_debt']}")
    print(f"Mean debt: {result['mean_debt']}")
    print(f"Rating: {result['rating']}")
    print(f"Worst: {result['worst_parameter']}")
    for p in result["parameters"]:
        print(f"  {p['parameter']}: inflation={p['inflation_ratio']}x, "
              f"carried={p['carried_fraction']}, debt={p['debt_score']}")
    
    # Audit with corrected values
    print("\n## Corrected System (using replicated values)")
    corrected = [
        Parameter(p.name, p.original_value, p.original_source,
                  p.replicated_value, p.replication_source,
                  p.replicated_value, p.description)  # system = replicated
        for p in PARAMETER_DB
    ]
    result2 = compute_calibration_debt(corrected)
    print(f"Total debt: {result2['total_debt']}")
    print(f"Rating: {result2['rating']}")
    
    # Sybil advantage
    print("\n## Sybil Advantage from Overcalibration")
    adv = compute_sybil_advantage(PARAMETER_DB)
    print(f"Overpunishment ratio: {adv['overpunishment_ratio']}x")
    print(adv['interpretation'])
    
    # Cascade
    print("\n## Replication Cascade")
    cascade = replication_cascade()
    print(cascade['insight'])
    for k, v in cascade['cascade'].items():
        print(f"  {k}: P(all valid)={v['p_all_valid']}, "
              f"zombie={v['expected_zombie_params']}")
    
    print("\n" + "=" * 60)
    print("Calibration debt = technical debt for empirical parameters.")
    print("Cunningham (1992) for code. santaclawd (2026) for trust.")
    print("=" * 60)
