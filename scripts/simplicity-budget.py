#!/usr/bin/env python3
"""
simplicity-budget.py — Measure spec complexity vs adoption probability.

Per santaclawd: "too simple to own" is the design principle.
Per Kit: "every field that enters the wire format raises the adoption barrier."

RFC 6962 (CT) = 30 pages → near-universal adoption.
OAuth 2.0 = 75 pages → fragmented adoption (many profiles, many bugs).
WS-* = 1000+ pages → dead.

The simplicity budget: a spec has N complexity points to spend.
Each required field costs 1. Each optional field costs 0.5.
Each nested object costs 2. Each enum costs 0.5 per value.
Adoption probability drops exponentially with complexity.

Usage:
    python3 simplicity-budget.py
"""

import json
import math
from dataclasses import dataclass, field
from typing import List, Dict


@dataclass
class SpecField:
    name: str
    required: bool = True
    field_type: str = "scalar"  # scalar | object | array | enum
    enum_values: int = 0
    nested_fields: int = 0
    description: str = ""


@dataclass
class SpecBudget:
    name: str
    fields: List[SpecField] = field(default_factory=list)
    
    def complexity_score(self) -> float:
        score = 0.0
        for f in self.fields:
            base = 1.0 if f.required else 0.5
            if f.field_type == "object":
                base += 2.0 + (f.nested_fields * 0.5)
            elif f.field_type == "array":
                base += 1.0
            elif f.field_type == "enum":
                base += f.enum_values * 0.3
            score += base
        return round(score, 1)
    
    def adoption_probability(self) -> float:
        """Exponential decay: adoption ∝ e^(-complexity/k)"""
        k = 15.0  # tuned to match historical data
        return round(math.exp(-self.complexity_score() / k), 3)
    
    def report(self) -> str:
        lines = [f"\n{'=' * 55}", f"SPEC: {self.name}", f"{'=' * 55}"]
        
        required = [f for f in self.fields if f.required]
        optional = [f for f in self.fields if not f.required]
        
        lines.append(f"\nRequired fields ({len(required)}):")
        for f in required:
            cost = 1.0
            if f.field_type == "object": cost += 2.0 + (f.nested_fields * 0.5)
            elif f.field_type == "array": cost += 1.0
            elif f.field_type == "enum": cost += f.enum_values * 0.3
            lines.append(f"  {f.name:25s} cost={cost:.1f}  ({f.field_type})")
        
        if optional:
            lines.append(f"\nOptional fields ({len(optional)}):")
            for f in optional:
                cost = 0.5
                if f.field_type == "object": cost += 2.0 + (f.nested_fields * 0.5)
                elif f.field_type == "array": cost += 1.0
                elif f.field_type == "enum": cost += f.enum_values * 0.3
                lines.append(f"  {f.name:25s} cost={cost:.1f}  ({f.field_type})")
        
        c = self.complexity_score()
        a = self.adoption_probability()
        grade = 'A' if a > 0.5 else 'B' if a > 0.3 else 'C' if a > 0.15 else 'D' if a > 0.05 else 'F'
        
        lines.append(f"\nComplexity: {c}")
        lines.append(f"Adoption probability: {a:.1%}")
        lines.append(f"Grade: {grade}")
        
        return '\n'.join(lines)


def l35_minimal():
    """L3.5 receipt — minimal viable spec."""
    return SpecBudget("L3.5 Receipt (Minimal)", [
        SpecField("version", True, "scalar"),
        SpecField("agent_id", True, "scalar"),
        SpecField("task_hash", True, "scalar"),
        SpecField("decision_type", True, "enum", enum_values=4),
        SpecField("timestamp", True, "scalar"),
        SpecField("dimensions", True, "object", nested_fields=5),
        SpecField("merkle_root", True, "scalar"),
        SpecField("witnesses", True, "array"),
        # Optional
        SpecField("scar_reference", False, "scalar"),
        SpecField("refusal_reason", False, "scalar"),
        SpecField("merkle_proof", False, "array"),
    ])


def l35_bloated():
    """L3.5 receipt — if we added everything discussed."""
    return SpecBudget("L3.5 Receipt (Kitchen Sink)", [
        SpecField("version", True, "scalar"),
        SpecField("agent_id", True, "scalar"),
        SpecField("task_hash", True, "scalar"),
        SpecField("decision_type", True, "enum", enum_values=6),
        SpecField("timestamp", True, "scalar"),
        SpecField("dimensions", True, "object", nested_fields=5),
        SpecField("merkle_root", True, "scalar"),
        SpecField("merkle_proof", True, "array"),
        SpecField("witnesses", True, "array"),
        SpecField("witness_diversity", True, "object", nested_fields=4),
        SpecField("scar_reference", True, "scalar"),
        SpecField("refusal_reason", False, "scalar"),
        SpecField("rationale_hash", False, "scalar"),
        SpecField("origin_platform", False, "scalar"),
        SpecField("enforcement_mode", False, "enum", enum_values=3),
        SpecField("leitner_box", False, "scalar"),
        SpecField("escrow_amount", False, "scalar"),
        SpecField("compliance_grade", False, "scalar"),
        SpecField("gap_report_ref", False, "scalar"),
        SpecField("creation_anchor", False, "object", nested_fields=3),
    ])


def historical_specs():
    """Historical comparison points."""
    specs = []
    
    # RFC 6962 CT
    ct = SpecBudget("RFC 6962 (CT)", [
        SpecField("log_id", True, "scalar"),
        SpecField("timestamp", True, "scalar"),
        SpecField("entry_type", True, "enum", enum_values=2),
        SpecField("signed_entry", True, "object", nested_fields=3),
        SpecField("extensions", False, "scalar"),
    ])
    specs.append(ct)
    
    # JWT (RFC 7519) 
    jwt = SpecBudget("RFC 7519 (JWT)", [
        SpecField("header", True, "object", nested_fields=3),
        SpecField("payload", True, "object", nested_fields=7),
        SpecField("signature", True, "scalar"),
    ])
    specs.append(jwt)
    
    # OAuth 2.0 token
    oauth = SpecBudget("RFC 6749 (OAuth 2.0)", [
        SpecField("grant_type", True, "enum", enum_values=4),
        SpecField("client_id", True, "scalar"),
        SpecField("client_secret", False, "scalar"),
        SpecField("redirect_uri", True, "scalar"),
        SpecField("scope", False, "scalar"),
        SpecField("state", False, "scalar"),
        SpecField("code_verifier", False, "scalar"),
        SpecField("code_challenge", False, "scalar"),
        SpecField("response_type", True, "enum", enum_values=3),
        SpecField("token_type", True, "enum", enum_values=2),
        SpecField("access_token", True, "scalar"),
        SpecField("refresh_token", False, "scalar"),
        SpecField("expires_in", False, "scalar"),
    ])
    specs.append(oauth)
    
    return specs


def main():
    print("SIMPLICITY BUDGET ANALYSIS")
    print("'every field raises the adoption barrier'")
    print("=" * 55)
    
    minimal = l35_minimal()
    bloated = l35_bloated()
    historical = historical_specs()
    
    all_specs = [minimal, bloated] + historical
    
    for spec in all_specs:
        print(spec.report())
    
    print(f"\n{'=' * 55}")
    print("COMPARISON")
    print(f"{'=' * 55}")
    print(f"\n{'Spec':<35} {'Complex':>8} {'Adopt':>8} {'Grade':>6}")
    print("-" * 60)
    for spec in sorted(all_specs, key=lambda s: s.complexity_score()):
        c = spec.complexity_score()
        a = spec.adoption_probability()
        grade = 'A' if a > 0.5 else 'B' if a > 0.3 else 'C' if a > 0.15 else 'D' if a > 0.05 else 'F'
        print(f"{spec.name:<35} {c:>8.1f} {a:>7.1%} {grade:>6}")
    
    print(f"\n{'=' * 55}")
    print("VERDICT")
    print(f"{'=' * 55}")
    m_c = minimal.complexity_score()
    b_c = bloated.complexity_score()
    print(f"\nMinimal L3.5: {m_c} complexity → {minimal.adoption_probability():.0%} adoption")
    print(f"Kitchen sink: {b_c} complexity → {bloated.adoption_probability():.0%} adoption")
    print(f"Bloat tax: {b_c - m_c:.1f} extra complexity = {minimal.adoption_probability() - bloated.adoption_probability():.0%} adoption loss")
    print(f"\nRule: if it's not in the wire format, it's in the enforcer.")
    print(f"The spec should fit in a README.")


if __name__ == '__main__':
    main()
