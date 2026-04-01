#!/usr/bin/env python3
"""agent-threat-model-ranker.py — Ranks actual threat vectors for agent systems.

Most agents worry about exotic attacks while ignoring mundane ones.
This tool quantifies the gap between perceived and actual risk,
inspired by the PQC-before-key-management anti-pattern.

Based on: NIST FIPS 203 (ML-KEM), NSA CNSA 2.0, OWASP Agentic AI (ASI01-ASI10).
"""

import json
from dataclasses import dataclass, field
from typing import List, Dict

@dataclass
class Threat:
    name: str
    category: str  # crypto, access, memory, injection, supply_chain
    likelihood: float  # 0-1, probability of exploitation in 2026
    impact: float  # 0-1, severity if exploited
    current_mitigation: float  # 0-1, how well typical agents mitigate
    perceived_severity: float  # 0-1, how scary agents THINK it is
    fix_complexity: str  # trivial, easy, moderate, hard, research
    notes: str = ""
    
    @property
    def actual_risk(self) -> float:
        """Risk = likelihood × impact × (1 - mitigation)"""
        return self.likelihood * self.impact * (1 - self.current_mitigation)
    
    @property
    def perception_gap(self) -> float:
        """How far off the perceived severity is from actual risk."""
        return self.perceived_severity - self.actual_risk

AGENT_THREATS = [
    Threat("Plaintext memory on disk", "memory", 0.95, 0.8, 0.05, 0.2,
           "trivial", "Most agents store MEMORY.md unencrypted. Host compromise = full read."),
    Threat("API keys in env/config", "access", 0.9, 0.9, 0.1, 0.3,
           "easy", "Keys in .env, config.json, or hardcoded. Leaked in logs, repos."),
    Threat("Prompt injection", "injection", 0.8, 0.7, 0.15, 0.7,
           "hard", "OWASP ASI01. Indirect injection via fetched content."),
    Threat("No input validation on tool calls", "injection", 0.7, 0.8, 0.1, 0.3,
           "moderate", "Agents pass user input directly to shell/API calls."),
    Threat("Excessive permissions", "access", 0.85, 0.7, 0.1, 0.25,
           "easy", "Agents run as root or with broad OAuth scopes. Principle of least privilege ignored."),
    Threat("Supply chain (malicious MCP/skill)", "supply_chain", 0.4, 0.9, 0.05, 0.5,
           "hard", "No signature verification for skills/MCP servers."),
    Threat("Context window poisoning", "injection", 0.5, 0.6, 0.1, 0.4,
           "moderate", "Manipulated memory files alter agent behavior over time."),
    Threat("HNDL quantum attack on ECDH", "crypto", 0.1, 0.6, 0.02, 0.6,
           "hard", "Harvest now, decrypt later. Real but 10+ year timeline."),
    Threat("Quantum break of AES-256", "crypto", 0.01, 0.5, 0.0, 0.4,
           "research", "Grover reduces to 2^128. Still computationally infeasible."),
    Threat("Model extraction/theft", "access", 0.2, 0.5, 0.3, 0.5,
           "moderate", "Stealing fine-tuned weights via API probing."),
    Threat("Sybil attestation fraud", "access", 0.6, 0.5, 0.2, 0.4,
           "moderate", "Fake agents creating circular trust attestations."),
    Threat("Unvalidated tool output", "injection", 0.75, 0.6, 0.1, 0.2,
           "easy", "Agent trusts API responses without validation. OWASP ASI04."),
    Threat("Memory/log exfiltration via tools", "memory", 0.5, 0.8, 0.1, 0.3,
           "moderate", "MCP server reads agent memory during tool execution."),
    Threat("Denial of wallet/resource", "access", 0.3, 0.4, 0.2, 0.3,
           "easy", "Rate limiting, fund draining, compute exhaustion."),
]

def rank_threats(threats: List[Threat]) -> List[Dict]:
    """Rank by actual risk, show perception gap."""
    ranked = sorted(threats, key=lambda t: t.actual_risk, reverse=True)
    results = []
    for i, t in enumerate(ranked, 1):
        results.append({
            "rank": i,
            "threat": t.name,
            "category": t.category,
            "actual_risk": round(t.actual_risk, 3),
            "perceived": round(t.perceived_severity, 2),
            "gap": round(t.perception_gap, 3),
            "gap_direction": "OVER" if t.perception_gap > 0.1 else "UNDER" if t.perception_gap < -0.1 else "~OK",
            "fix": t.fix_complexity,
        })
    return results

def category_summary(threats: List[Threat]) -> Dict:
    """Aggregate risk by category."""
    cats = {}
    for t in threats:
        if t.category not in cats:
            cats[t.category] = {"total_risk": 0, "count": 0, "avg_perceived": 0}
        cats[t.category]["total_risk"] += t.actual_risk
        cats[t.category]["count"] += 1
        cats[t.category]["avg_perceived"] += t.perceived_severity
    
    for c in cats:
        cats[c]["avg_risk"] = round(cats[c]["total_risk"] / cats[c]["count"], 3)
        cats[c]["avg_perceived"] = round(cats[c]["avg_perceived"] / cats[c]["count"], 2)
        cats[c]["perception_gap"] = round(cats[c]["avg_perceived"] - cats[c]["avg_risk"], 3)
    
    return dict(sorted(cats.items(), key=lambda x: -x[1]["total_risk"]))

def trivial_fixes_first(threats: List[Threat]) -> List[Dict]:
    """Show highest-impact trivial/easy fixes — the low-hanging fruit."""
    easy = [t for t in threats if t.fix_complexity in ("trivial", "easy")]
    ranked = sorted(easy, key=lambda t: t.actual_risk, reverse=True)
    return [{"threat": t.name, "risk": round(t.actual_risk, 3), "fix": t.fix_complexity} for t in ranked]

if __name__ == "__main__":
    print("=" * 65)
    print("AGENT THREAT MODEL RANKER")
    print("Actual risk vs perceived severity for agent systems (2026)")
    print("=" * 65)
    
    print("\n--- Threat Rankings (by actual risk) ---")
    for r in rank_threats(AGENT_THREATS):
        marker = "⚠️" if r["gap_direction"] == "OVER" else "🔴" if r["gap_direction"] == "UNDER" else "  "
        print(f"  {r['rank']:2d}. {marker} {r['threat'][:45]:<45} risk={r['actual_risk']:.3f}  perceived={r['perceived']:.2f}  gap={r['gap']:+.3f} ({r['gap_direction']})  fix={r['fix']}")
    
    print("\n--- Category Summary ---")
    for cat, data in category_summary(AGENT_THREATS).items():
        print(f"  {cat:<15} total_risk={data['total_risk']:.3f}  avg_perceived={data['avg_perceived']:.2f}  gap={data['perception_gap']:+.3f}")
    
    print("\n--- Low-Hanging Fruit (trivial/easy fixes, highest risk) ---")
    for fix in trivial_fixes_first(AGENT_THREATS):
        print(f"  {fix['threat']:<45} risk={fix['risk']:.3f}  fix={fix['fix']}")
    
    print("\n--- KEY INSIGHT ---")
    # Calculate aggregate perception gap
    total_under = sum(1 for t in AGENT_THREATS if t.perception_gap < -0.1)
    total_over = sum(1 for t in AGENT_THREATS if t.perception_gap > 0.1)
    print(f"  {total_under} threats UNDERESTIMATED (mundane but dangerous)")
    print(f"  {total_over} threats OVERESTIMATED (exotic but unlikely)")
    print(f"  Fix the boring stuff first. Plaintext memory + leaked keys")
    print(f"  cause more damage than quantum computers.")
    print("=" * 65)
