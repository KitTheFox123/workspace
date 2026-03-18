#!/usr/bin/env python3
"""
aims-gap-analyzer.py — Analyze IETF AIMS draft coverage gaps
Maps draft-klrc-aiagent-auth-00 against OWASP Agentic Top 10 + L3.5 receipts.
Identifies which layers are covered, which are gaps, and where receipts fill in.

Based on RockCyber analysis (2026-03-17) of AIMS + OWASP + AuthZEN.
"""

import json
from dataclasses import dataclass, asdict
from enum import Enum

class Coverage(Enum):
    COVERED = "covered"
    PARTIAL = "partial"  
    GAP = "gap"
    NOT_APPLICABLE = "n/a"

@dataclass
class SecurityLayer:
    name: str
    description: str
    aims_coverage: Coverage
    aims_mechanism: str
    l35_coverage: Coverage
    l35_mechanism: str
    authzen_coverage: Coverage
    authzen_mechanism: str
    priority: str  # critical/high/medium/low

# OWASP Agentic Top 10 mapping
OWASP_AGENTIC = [
    SecurityLayer(
        "ASI01 - Excessive Agency",
        "Agent performs actions beyond intended scope",
        Coverage.PARTIAL, "OAuth scopes limit access categories",
        Coverage.COVERED, "Receipt history shows behavioral drift over time",
        Coverage.COVERED, "Per-action evaluation against dynamic policy",
        "critical"
    ),
    SecurityLayer(
        "ASI02 - Prompt Injection",
        "Adversarial input manipulates agent behavior",
        Coverage.GAP, "Not addressed in draft",
        Coverage.PARTIAL, "Behavioral anomaly detectable via receipt patterns",
        Coverage.GAP, "Input validation outside AuthZEN scope",
        "critical"
    ),
    SecurityLayer(
        "ASI03 - Identity & Privilege Abuse",
        "Agent exploits granted privileges beyond intent",
        Coverage.PARTIAL, "SPIFFE identity + Transaction Tokens",
        Coverage.COVERED, "Receipts prove actual actions vs. granted scope",
        Coverage.COVERED, "Least agency enforcement per-action",
        "critical"
    ),
    SecurityLayer(
        "ASI04 - Insecure Output Handling",
        "Agent output consumed without validation",
        Coverage.GAP, "Not addressed",
        Coverage.PARTIAL, "Receipt captures output hash for audit",
        Coverage.GAP, "Output validation outside authz scope",
        "high"
    ),
    SecurityLayer(
        "ASI05 - Insufficient Monitoring",
        "Lack of observability into agent actions",
        Coverage.COVERED, "Section 11: 7 audit fields, CAEP signals",
        Coverage.COVERED, "Every action generates receipt = audit trail",
        Coverage.PARTIAL, "Observability feeds context, not primary function",
        "high"
    ),
    SecurityLayer(
        "ASI06 - Supply Chain Vulnerabilities",
        "Compromised tools/models in agent pipeline",
        Coverage.GAP, "Not addressed",
        Coverage.PARTIAL, "Tool provenance trackable via witness attestation",
        Coverage.GAP, "Supply chain outside authz scope",
        "high"
    ),
    SecurityLayer(
        "ASI07 - Inadequate Sandboxing",
        "Agent escapes execution boundary",
        Coverage.PARTIAL, "SPIFFE attestation binds to execution environment",
        Coverage.GAP, "Receipts don't enforce sandboxing",
        Coverage.PARTIAL, "Resource constraints expressible in policy",
        "high"
    ),
    SecurityLayer(
        "ASI08 - Cascading Failures",
        "Failure in one agent propagates through system",
        Coverage.GAP, "No blast-radius concept",
        Coverage.COVERED, "Receipt chain reveals failure propagation path",
        Coverage.COVERED, "Blast-radius caps in policy context",
        "critical"
    ),
    SecurityLayer(
        "ASI09 - Denial of Service",
        "Agent overwhelmed or weaponized for DoS",
        Coverage.PARTIAL, "Token expiration limits window",
        Coverage.PARTIAL, "Rate anomalies detectable in receipt patterns",
        Coverage.COVERED, "Rate limiting expressible as policy",
        "medium"
    ),
    SecurityLayer(
        "ASI10 - Insecure Plugin Design",
        "Tools/plugins lack proper security controls",
        Coverage.GAP, "MCP tool-to-scope mapping absent",
        Coverage.PARTIAL, "Per-tool receipt trail = accountability",
        Coverage.COVERED, "Per-tool evaluation in AuthZEN",
        "high"
    ),
]

# Identity stack layers
IDENTITY_LAYERS = [
    SecurityLayer(
        "Authentication",
        "Proving agent identity cryptographically",
        Coverage.COVERED, "SPIFFE/WIMSE attestation-bound identity",
        Coverage.NOT_APPLICABLE, "Receipts don't authenticate",
        Coverage.NOT_APPLICABLE, "AuthZEN assumes authenticated subject",
        "critical"
    ),
    SecurityLayer(
        "Coarse Authorization",
        "What resource categories can agent access",
        Coverage.COVERED, "OAuth 2.0 scopes + delegation",
        Coverage.NOT_APPLICABLE, "Receipts don't authorize",
        Coverage.COVERED, "Scope evaluation in PDP",
        "critical"
    ),
    SecurityLayer(
        "Fine Authorization",
        "Should this specific action proceed right now",
        Coverage.GAP, "Stops at token boundary",
        Coverage.PARTIAL, "Receipt history informs decisions",
        Coverage.COVERED, "Per-action evaluation with full context",
        "critical"
    ),
    SecurityLayer(
        "Behavioral Trust",
        "Dynamic trust based on observed behavior",
        Coverage.GAP, "Conceptual model mentions, spec doesn't deliver",
        Coverage.COVERED, "Receipt chain IS behavioral evidence",
        Coverage.COVERED, "Behavioral signals as context attributes",
        "critical"
    ),
    SecurityLayer(
        "Consequence Assessment",
        "Evaluating blast radius before permitting action",
        Coverage.GAP, "No concept of blast radius",
        Coverage.PARTIAL, "Historical receipts show impact patterns",
        Coverage.COVERED, "blast_radius, reversible flags in context",
        "high"
    ),
    SecurityLayer(
        "Delegation Chain",
        "Tracking authority through multi-hop workflows",
        Coverage.PARTIAL, "Transaction Tokens bind context per-hop",
        Coverage.COVERED, "Receipt chain preserves delegation provenance",
        Coverage.PARTIAL, "Subject chain expressible but complex",
        "high"
    ),
    SecurityLayer(
        "Graduated Trust",
        "Progressive autonomy based on track record",
        Coverage.GAP, "No graduation stages in spec",
        Coverage.COVERED, "Leitner box model from receipt history",
        Coverage.COVERED, "Trust level as policy input",
        "high"
    ),
    SecurityLayer(
        "Observability Feedback",
        "Detection signals feeding back into policy",
        Coverage.PARTIAL, "CAEP signals, but reactive only (circuit breaker)",
        Coverage.COVERED, "Receipt patterns = real-time behavioral input",
        Coverage.COVERED, "Observability as first-class context attribute",
        "high"
    ),
]

def analyze_coverage(layers: list[SecurityLayer]) -> dict:
    """Compute coverage statistics."""
    stats = {}
    for system in ["aims", "l35", "authzen"]:
        field = f"{system}_coverage"
        coverages = [getattr(l, field) for l in layers if getattr(l, field) != Coverage.NOT_APPLICABLE]
        total = len(coverages)
        covered = sum(1 for c in coverages if c == Coverage.COVERED)
        partial = sum(1 for c in coverages if c == Coverage.PARTIAL)
        gap = sum(1 for c in coverages if c == Coverage.GAP)
        stats[system] = {
            "covered": covered,
            "partial": partial,
            "gap": gap,
            "total": total,
            "score": round((covered + partial * 0.5) / total * 100, 1) if total > 0 else 0
        }
    return stats

def find_complementary_coverage(layers: list[SecurityLayer]) -> list[dict]:
    """Find layers where AIMS has gaps but L3.5/AuthZEN fill in."""
    complements = []
    for layer in layers:
        if layer.aims_coverage == Coverage.GAP:
            fills = []
            if layer.l35_coverage in (Coverage.COVERED, Coverage.PARTIAL):
                fills.append(f"L3.5: {layer.l35_mechanism}")
            if layer.authzen_coverage in (Coverage.COVERED, Coverage.PARTIAL):
                fills.append(f"AuthZEN: {layer.authzen_mechanism}")
            if fills:
                complements.append({
                    "layer": layer.name,
                    "aims_gap": layer.aims_mechanism,
                    "filled_by": fills,
                    "priority": layer.priority
                })
    return complements

def main():
    print("=" * 70)
    print("AIMS Gap Analysis: draft-klrc-aiagent-auth-00 vs OWASP + L3.5")
    print("=" * 70)
    
    # OWASP analysis
    print("\n📋 OWASP Agentic Top 10 Coverage:")
    print("-" * 50)
    owasp_stats = analyze_coverage(OWASP_AGENTIC)
    for system, stats in owasp_stats.items():
        print(f"  {system.upper():8s}: {stats['score']:5.1f}% "
              f"(✓{stats['covered']} ~{stats['partial']} ✗{stats['gap']})")
    
    # Identity stack analysis
    print("\n🔐 Identity Stack Coverage:")
    print("-" * 50)
    id_stats = analyze_coverage(IDENTITY_LAYERS)
    for system, stats in id_stats.items():
        print(f"  {system.upper():8s}: {stats['score']:5.1f}% "
              f"(✓{stats['covered']} ~{stats['partial']} ✗{stats['gap']})")
    
    # Complementary coverage
    print("\n🔗 Where L3.5/AuthZEN Fill AIMS Gaps:")
    print("-" * 50)
    all_layers = OWASP_AGENTIC + IDENTITY_LAYERS
    complements = find_complementary_coverage(all_layers)
    for comp in complements:
        print(f"\n  [{comp['priority'].upper()}] {comp['layer']}")
        print(f"    AIMS: {comp['aims_gap']}")
        for fill in comp['filled_by']:
            print(f"    → {fill}")
    
    # Key insight
    print("\n" + "=" * 70)
    print("KEY INSIGHT:")
    print("  AIMS answers: 'Is this really Agent X?' (authentication)")
    print("  L3.5 answers: 'What has Agent X actually done?' (evidence)")
    print("  AuthZEN answers: 'Should Agent X do THIS right now?' (authorization)")
    print("  All three needed. None alone sufficient.")
    print()
    
    combined_owasp = round(
        (owasp_stats['aims']['score'] + owasp_stats['l35']['score'] + owasp_stats['authzen']['score']) / 3, 1
    )
    combined_id = round(
        (id_stats['aims']['score'] + id_stats['l35']['score'] + id_stats['authzen']['score']) / 3, 1
    )
    print(f"  Combined OWASP coverage: {combined_owasp}%")
    print(f"  Combined Identity coverage: {combined_id}%")
    print(f"  AIMS alone OWASP: {owasp_stats['aims']['score']}%")
    print(f"  AIMS alone Identity: {id_stats['aims']['score']}%")
    print()
    
    # MCP gap stat
    print("⚠️  ECOSYSTEM STATUS:")
    print("  53% of MCP servers use static API keys (Astrix Security)")
    print("  Only 8.5% use OAuth")
    print("  The ecosystem builds on the anti-pattern the draft condemns")
    print("=" * 70)

def nemoclaw_analysis():
    """Analyze NemoClaw's vendor lock-in risk vs open alternatives."""
    print("\n" + "=" * 70)
    print("NEMOCLAW VENDOR LOCK-IN ANALYSIS (GTC 2026)")
    print("=" * 70)
    
    stacks = [
        {
            "name": "NemoClaw (Nvidia)",
            "format_open": True,
            "enforcement_open": False,  # OpenShell built with CrowdStrike/Cisco/MSFT
            "trust_layer_vendor": True,  # Policy guardrails = Nvidia stack
            "gpu_dependency": True,
            "identity_portable": False,  # SPIFFE possible but not default
            "spec_org_eq_enforcement": True,  # Nvidia controls both
            "lockin_score": 0.60,
        },
        {
            "name": "CT (Certificate Transparency)",
            "format_open": True,
            "enforcement_open": True,  # Multiple independent log operators
            "trust_layer_vendor": False,
            "gpu_dependency": False,
            "identity_portable": True,  # Certificates portable
            "spec_org_eq_enforcement": False,  # IETF ≠ Google/browsers
            "lockin_score": 0.14,
        },
        {
            "name": "L3.5 Receipt Format",
            "format_open": True,
            "enforcement_open": True,  # Any verifier
            "trust_layer_vendor": False,
            "gpu_dependency": False,
            "identity_portable": True,  # DKIM-signed, platform-independent
            "spec_org_eq_enforcement": False,
            "lockin_score": 0.08,
        },
        {
            "name": "AIMS (IETF draft)",
            "format_open": True,
            "enforcement_open": True,  # Standards-based
            "trust_layer_vendor": False,
            "gpu_dependency": False,
            "identity_portable": True,  # SPIFFE
            "spec_org_eq_enforcement": False,
            "lockin_score": 0.12,
        },
    ]
    
    grades = {(0, 0.15): "A", (0.15, 0.30): "B", (0.30, 0.50): "C", (0.50, 1.0): "D"}
    
    for stack in stacks:
        grade = next(g for (lo, hi), g in grades.items() if lo <= stack["lockin_score"] < hi)
        print(f"\n  {stack['name']}: Grade {grade} ({stack['lockin_score']:.0%} lock-in)")
        print(f"    Format open: {'✓' if stack['format_open'] else '✗'}")
        print(f"    Enforcement open: {'✓' if stack['enforcement_open'] else '✗'}")
        print(f"    Trust layer vendor-free: {'✓' if not stack['trust_layer_vendor'] else '✗'}")
        print(f"    Identity portable: {'✓' if stack['identity_portable'] else '✗'}")
        print(f"    spec_org ≠ enforcement_org: {'✓' if not stack['spec_org_eq_enforcement'] else '✗'}")
    
    print(f"\n  ⚠️ NemoClaw pattern: open base + proprietary security = ActiveX 2.0")
    print(f"  The security layer IS the lock-in vector.")
    print(f"  Antidote: spec_org ≠ enforcement_org (CT, L3.5, AIMS)")


if __name__ == "__main__":
    main()
    nemoclaw_analysis()
