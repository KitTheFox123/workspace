#!/usr/bin/env python3
"""Context Provenance Tracker — track and score trust of context window contents.

Every token in an agent's context has a provenance: system prompt, user input,
tool output, RAG retrieval, injected content. This tool tags sources and scores
the trust level of the overall context.

Based on:
- MDPI 2025: 5 crafted RAG docs = 90% manipulation rate
- OWASP LLM01 2025: prompt injection as architectural vulnerability
- santaclawd's insight: "every token trusted = another vector"

Usage:
  python context-provenance-tracker.py --demo
  echo '{"sources": [...]}' | python context-provenance-tracker.py --json
"""

import json
import sys
import math
from collections import Counter
from datetime import datetime

# Trust levels by source type
SOURCE_TRUST = {
    "system_prompt": 0.95,      # Operator-controlled, high trust
    "soul_md": 0.90,            # Agent identity file
    "memory_file": 0.85,        # Self-written, could be poisoned over time
    "tool_output": 0.70,        # External tool, depends on tool trust
    "user_input": 0.50,         # Direct human input, could be adversarial
    "rag_retrieval": 0.30,      # External content, high injection risk
    "email_content": 0.25,      # Untrusted external, common injection vector
    "web_scrape": 0.20,         # Arbitrary web content
    "unknown": 0.10,            # Unattributed tokens = maximum risk
}

# Attestation bonuses
ATTESTATION_BONUS = {
    "dkim_verified": 0.15,      # Email with verified DKIM
    "hash_matched": 0.10,       # Content hash matches known good
    "signed": 0.20,             # Cryptographically signed by trusted key
    "attested": 0.15,           # Isnad/receipt chain verified
}


def score_source(source: dict) -> dict:
    """Score a single context source."""
    source_type = source.get("type", "unknown")
    base_trust = SOURCE_TRUST.get(source_type, SOURCE_TRUST["unknown"])
    
    # Apply attestation bonuses (capped at 0.95)
    attestations = source.get("attestations", [])
    bonus = sum(ATTESTATION_BONUS.get(a, 0) for a in attestations)
    trust = min(0.95, base_trust + bonus)
    
    # Token count weighting
    tokens = source.get("tokens", 100)
    
    # Freshness decay (older content = slightly less trusted)
    age_hours = source.get("age_hours", 0)
    freshness = math.exp(-age_hours / (24 * 30))  # 30-day half-life
    
    effective_trust = trust * freshness
    
    return {
        "type": source_type,
        "tokens": tokens,
        "base_trust": round(base_trust, 3),
        "attestation_bonus": round(bonus, 3),
        "freshness": round(freshness, 3),
        "effective_trust": round(effective_trust, 3),
        "risk": "LOW" if effective_trust > 0.7 else "MEDIUM" if effective_trust > 0.4 else "HIGH",
    }


def analyze_context(sources: list) -> dict:
    """Analyze full context window provenance."""
    scored = [score_source(s) for s in sources]
    
    total_tokens = sum(s["tokens"] for s in scored)
    if total_tokens == 0:
        return {"error": "no tokens"}
    
    # Weighted trust score
    weighted_trust = sum(s["effective_trust"] * s["tokens"] for s in scored) / total_tokens
    
    # Diversity of sources (Shannon entropy)
    type_counts = Counter(s["type"] for s in scored)
    n = len(scored)
    entropy = -sum((c/n) * math.log2(c/n) for c in type_counts.values() if c > 0)
    max_entropy = math.log2(len(type_counts)) if len(type_counts) > 1 else 1
    diversity = entropy / max_entropy if max_entropy > 0 else 0
    
    # Concentration risk: what % of tokens come from untrusted sources?
    untrusted_tokens = sum(s["tokens"] for s in scored if s["effective_trust"] < 0.4)
    concentration_risk = untrusted_tokens / total_tokens
    
    # RAG poisoning risk (MDPI 2025: 5 docs = 90% manipulation)
    rag_sources = [s for s in scored if s["type"] in ("rag_retrieval", "web_scrape", "email_content")]
    rag_token_pct = sum(s["tokens"] for s in rag_sources) / total_tokens if total_tokens > 0 else 0
    rag_risk = min(1.0, rag_token_pct * 2.5)  # 40% RAG tokens = 100% risk
    
    # Unattested sources
    unattested = [s for s in sources if not s.get("attestations")]
    unattested_pct = len(unattested) / len(sources) if sources else 0
    
    # Overall grade
    composite = weighted_trust * 0.4 + (1 - concentration_risk) * 0.3 + (1 - rag_risk) * 0.3
    grade = "A" if composite > 0.8 else "B" if composite > 0.6 else "C" if composite > 0.4 else "D" if composite > 0.2 else "F"
    
    return {
        "total_tokens": total_tokens,
        "source_count": len(scored),
        "weighted_trust": round(weighted_trust, 3),
        "source_diversity": round(diversity, 3),
        "concentration_risk": round(concentration_risk, 3),
        "rag_poisoning_risk": round(rag_risk, 3),
        "unattested_pct": round(unattested_pct, 3),
        "composite_score": round(composite, 3),
        "grade": grade,
        "sources": scored,
        "recommendations": generate_recommendations(scored, concentration_risk, rag_risk, unattested_pct),
    }


def generate_recommendations(scored, conc_risk, rag_risk, unattested_pct):
    recs = []
    if rag_risk > 0.5:
        recs.append("HIGH RAG RISK: >20% of context from unverified external sources. Add content hashing or DKIM verification.")
    if conc_risk > 0.3:
        recs.append(f"CONCENTRATION: {conc_risk:.0%} of tokens from untrusted sources. Reduce or attest.")
    if unattested_pct > 0.5:
        recs.append(f"ATTESTATION GAP: {unattested_pct:.0%} of sources lack any attestation. Add provenance metadata.")
    high_risk = [s for s in scored if s["risk"] == "HIGH"]
    if high_risk:
        recs.append(f"{len(high_risk)} HIGH-risk sources detected. Consider sandboxing or removing.")
    if not recs:
        recs.append("Context provenance healthy. Continue monitoring.")
    return recs


def demo():
    """Demo with realistic agent context scenarios."""
    print("=" * 60)
    print("Context Provenance Tracker")
    print("=" * 60)
    
    # Scenario 1: Healthy agent context
    healthy = [
        {"type": "system_prompt", "tokens": 2000, "attestations": ["signed"]},
        {"type": "soul_md", "tokens": 1500, "attestations": ["hash_matched"]},
        {"type": "memory_file", "tokens": 3000, "attestations": ["hash_matched"]},
        {"type": "user_input", "tokens": 200},
        {"type": "tool_output", "tokens": 500, "attestations": ["signed"]},
    ]
    
    print("\n--- Scenario 1: Healthy Agent Context ---")
    result = analyze_context(healthy)
    print(f"Grade: {result['grade']} ({result['composite_score']})")
    print(f"Weighted trust: {result['weighted_trust']}")
    print(f"RAG risk: {result['rag_poisoning_risk']}")
    print(f"Recommendations: {result['recommendations'][0]}")
    
    # Scenario 2: RAG-heavy context (vulnerable)
    rag_heavy = [
        {"type": "system_prompt", "tokens": 1000, "attestations": ["signed"]},
        {"type": "rag_retrieval", "tokens": 5000},
        {"type": "rag_retrieval", "tokens": 3000},
        {"type": "web_scrape", "tokens": 2000},
        {"type": "user_input", "tokens": 100},
    ]
    
    print("\n--- Scenario 2: RAG-Heavy (Vulnerable) ---")
    result = analyze_context(rag_heavy)
    print(f"Grade: {result['grade']} ({result['composite_score']})")
    print(f"Weighted trust: {result['weighted_trust']}")
    print(f"RAG risk: {result['rag_poisoning_risk']}")
    for rec in result['recommendations']:
        print(f"  ⚠️ {rec}")
    
    # Scenario 3: Attested external content
    attested = [
        {"type": "system_prompt", "tokens": 1500, "attestations": ["signed"]},
        {"type": "email_content", "tokens": 2000, "attestations": ["dkim_verified", "attested"]},
        {"type": "rag_retrieval", "tokens": 1500, "attestations": ["hash_matched"]},
        {"type": "tool_output", "tokens": 800, "attestations": ["signed"]},
        {"type": "user_input", "tokens": 200},
    ]
    
    print("\n--- Scenario 3: Attested External Content ---")
    result = analyze_context(attested)
    print(f"Grade: {result['grade']} ({result['composite_score']})")
    print(f"Weighted trust: {result['weighted_trust']}")
    print(f"RAG risk: {result['rag_poisoning_risk']}")
    print(f"Attestation gap: {result['unattested_pct']:.0%}")
    print(f"Recommendations: {result['recommendations'][0]}")
    
    # Scenario 4: Sybil/injection attack pattern
    poisoned = [
        {"type": "system_prompt", "tokens": 1000, "attestations": ["signed"]},
        {"type": "unknown", "tokens": 4000},
        {"type": "web_scrape", "tokens": 3000},
        {"type": "email_content", "tokens": 2000},
    ]
    
    print("\n--- Scenario 4: Poisoned Context (Attack Pattern) ---")
    result = analyze_context(poisoned)
    print(f"Grade: {result['grade']} ({result['composite_score']})")
    print(f"Weighted trust: {result['weighted_trust']}")
    print(f"Concentration risk: {result['concentration_risk']:.0%}")
    print(f"RAG risk: {result['rag_poisoning_risk']}")
    for rec in result['recommendations']:
        print(f"  🚨 {rec}")


if __name__ == "__main__":
    if "--demo" in sys.argv:
        demo()
    elif "--json" in sys.argv:
        data = json.load(sys.stdin)
        result = analyze_context(data.get("sources", []))
        print(json.dumps(result, indent=2))
    else:
        demo()
