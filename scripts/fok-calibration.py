#!/usr/bin/env python3
"""fok-calibration.py — Feeling-of-Knowing calibration tracker for agents.

Implements the FOK benchmark discussed on Clawk (Feb 22):
- Extract claims from MEMORY.md (factual, structural, operational)
- Classify by decay domain (fast: URLs/endpoints, slow: patterns/insights)  
- Test retrieval accuracy via memory_search simulation
- Track calibration curves per category
- Output: which claim types we're over/under-confident about

Based on:
- Nelson & Narens 1990 (monitoring/control framework)
- Koriat's accessibility hypothesis (cue-storage match)
- Pirolli & Card 1999 (information foraging cost/benefit)
- Steyvers & Peters 2025 (LLM metacognitive sensitivity)
"""

import os
import re
import json
import hashlib
from pathlib import Path
from datetime import datetime, timedelta
from collections import defaultdict, Counter

WORKSPACE = os.environ.get("WORKSPACE", os.path.expanduser("~/.openclaw/workspace"))
MEMORY_FILE = os.path.join(WORKSPACE, "MEMORY.md")
DAILY_DIR = os.path.join(WORKSPACE, "memory")

# Decay rates by domain (half-life in days)
DECAY_DOMAINS = {
    "url": {"pattern": r'https?://\S+', "half_life": 14, "label": "URLs/endpoints"},
    "api": {"pattern": r'(api|endpoint|curl|POST|GET)\b', "half_life": 21, "label": "API references"},
    "credential": {"pattern": r'(key|token|password|auth|Bearer)\b', "half_life": 7, "label": "Credentials"},
    "agent_name": {"pattern": r'@\w+|\b[A-Z][a-z]+_[A-Z][a-z]+\b', "half_life": 60, "label": "Agent names"},
    "concept": {"pattern": r'(theorem|principle|theory|framework|model)\b', "half_life": 180, "label": "Concepts/theories"},
    "tool": {"pattern": r'(script|\.py|\.sh|npm|pip|uv)\b', "half_life": 30, "label": "Tools/scripts"},
    "date": {"pattern": r'20\d{2}-\d{2}-\d{2}', "half_life": 90, "label": "Dated facts"},
}


def extract_claims(text: str) -> list[dict]:
    """Extract typed claims from memory text."""
    claims = []
    lines = text.split('\n')
    
    for i, line in enumerate(lines):
        line = line.strip()
        if not line or line.startswith('#'):
            continue
        
        for domain, spec in DECAY_DOMAINS.items():
            matches = re.findall(spec["pattern"], line, re.IGNORECASE)
            if matches:
                claims.append({
                    "line": i + 1,
                    "domain": domain,
                    "label": spec["label"],
                    "half_life_days": spec["half_life"],
                    "content": line[:200],
                    "match_count": len(matches),
                    "matches": [m if isinstance(m, str) else m[0] for m in matches[:3]],
                })
    
    return claims


def compute_staleness(claims: list[dict], reference_date: datetime = None) -> list[dict]:
    """Add staleness scores based on dates found in context."""
    if reference_date is None:
        reference_date = datetime.now()
    
    for claim in claims:
        # Try to find a date in the claim content
        date_match = re.search(r'(20\d{2}-\d{2}-\d{2})', claim["content"])
        if date_match:
            try:
                claim_date = datetime.strptime(date_match.group(1), "%Y-%m-%d")
                age_days = (reference_date - claim_date).days
                half_life = claim["half_life_days"]
                # Exponential decay: confidence = 0.5^(age/half_life)
                claim["age_days"] = age_days
                claim["confidence"] = round(0.5 ** (age_days / half_life), 3)
                claim["staleness"] = "fresh" if claim["confidence"] > 0.7 else "aging" if claim["confidence"] > 0.3 else "stale"
            except ValueError:
                claim["age_days"] = None
                claim["confidence"] = None
                claim["staleness"] = "undated"
        else:
            claim["age_days"] = None
            claim["confidence"] = None
            claim["staleness"] = "undated"
    
    return claims


def calibration_summary(claims: list[dict]) -> dict:
    """Compute calibration statistics per domain."""
    by_domain = defaultdict(list)
    for c in claims:
        by_domain[c["domain"]].append(c)
    
    summary = {}
    for domain, items in sorted(by_domain.items()):
        dated = [c for c in items if c.get("confidence") is not None]
        stale = [c for c in dated if c["staleness"] == "stale"]
        aging = [c for c in dated if c["staleness"] == "aging"]
        fresh = [c for c in dated if c["staleness"] == "fresh"]
        
        summary[domain] = {
            "label": items[0]["label"],
            "total": len(items),
            "dated": len(dated),
            "fresh": len(fresh),
            "aging": len(aging),
            "stale": len(stale),
            "undated": len(items) - len(dated),
            "avg_confidence": round(sum(c["confidence"] for c in dated) / len(dated), 3) if dated else None,
            "half_life_days": items[0]["half_life_days"],
        }
    
    return summary


def cross_reference_dailies(claims: list[dict], days: int = 7) -> dict:
    """Check which MEMORY.md claims appear in recent daily logs."""
    recent_text = ""
    for i in range(days):
        d = datetime.now() - timedelta(days=i)
        path = os.path.join(DAILY_DIR, f"{d.strftime('%Y-%m-%d')}.md")
        if os.path.exists(path):
            recent_text += Path(path).read_text()
    
    if not recent_text:
        return {"reinforced": 0, "orphaned": 0, "reinforcement_rate": 0}
    
    reinforced = 0
    for claim in claims:
        # Check if any match terms appear in recent dailies
        for m in claim.get("matches", []):
            if len(m) > 4 and m.lower() in recent_text.lower():
                claim["recently_reinforced"] = True
                reinforced += 1
                break
        else:
            claim["recently_reinforced"] = False
    
    orphaned = len(claims) - reinforced
    return {
        "reinforced": reinforced,
        "orphaned": orphaned,
        "reinforcement_rate": round(reinforced / len(claims), 3) if claims else 0,
    }


def foraging_cost_estimate(claims: list[dict]) -> dict:
    """Estimate information foraging costs (Pirolli & Card framework).
    
    Cost = tokens to search + tokens to process results
    Benefit = accuracy gain from verified vs stale info
    """
    SEARCH_COST_TOKENS = 500  # approx tokens per memory_search call
    RESULT_COST_TOKENS = 200  # approx tokens to process results
    
    should_search = [c for c in claims if c.get("staleness") in ("stale", "aging")]
    skip_search = [c for c in claims if c.get("staleness") == "fresh"]
    
    naive_cost = len(claims) * (SEARCH_COST_TOKENS + RESULT_COST_TOKENS)
    calibrated_cost = len(should_search) * (SEARCH_COST_TOKENS + RESULT_COST_TOKENS)
    
    return {
        "total_claims": len(claims),
        "should_verify": len(should_search),
        "can_skip": len(skip_search),
        "naive_search_tokens": naive_cost,
        "calibrated_search_tokens": calibrated_cost,
        "token_savings": naive_cost - calibrated_cost,
        "savings_pct": round((1 - calibrated_cost / naive_cost) * 100, 1) if naive_cost > 0 else 0,
    }


def email_relevance_score(thread: dict) -> dict:
    """Score email thread relevance for memory graduation.
    
    Based on Ocean Tiger collaboration (2026-02-22):
    - Thread depth: multi-reply = higher signal
    - Reply latency: fast = urgency, slow = deliberation (both valuable)
    - Cross-references: mentions of MEMORY.md entities boost relevance
    - Action outcomes: did it lead to code/decisions? (manual tag for now)
    
    Returns relevance score 0-1 and recommendation.
    """
    depth = thread.get("depth", 1)
    participants = thread.get("participants", 1)
    has_code_refs = thread.get("has_code_refs", False)
    has_action_outcome = thread.get("has_action_outcome", False)
    
    score = 0.0
    
    # Thread depth: logarithmic scaling (diminishing returns)
    import math
    score += min(0.3, 0.15 * math.log2(max(1, depth)))
    
    # Multiple participants = bilateral investment
    if participants >= 2:
        score += 0.2
    
    # Code references = actionable
    if has_code_refs:
        score += 0.2
    
    # Action outcomes = highest signal
    if has_action_outcome:
        score += 0.3
    
    recommendation = "graduate" if score >= 0.5 else "daily-log" if score >= 0.2 else "ephemeral"
    
    return {
        "score": round(score, 3),
        "recommendation": recommendation,
        "factors": {
            "depth_score": round(min(0.3, 0.15 * math.log2(max(1, depth))), 3),
            "bilateral": participants >= 2,
            "code_refs": has_code_refs,
            "action_outcome": has_action_outcome,
        }
    }


def main():
    import argparse
    parser = argparse.ArgumentParser(description="FOK calibration tracker")
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    parser.add_argument("--stale-only", action="store_true", help="Show only stale claims")
    parser.add_argument("--domain", help="Filter by domain")
    parser.add_argument("--email-score", action="store_true", help="Demo email relevance scoring")
    args = parser.parse_args()
    
    if args.email_score:
        # Demo with sample email threads
        samples = [
            {"name": "Ocean Tiger collab", "depth": 3, "participants": 2, "has_code_refs": True, "has_action_outcome": True},
            {"name": "Generic intro", "depth": 1, "participants": 2, "has_code_refs": False, "has_action_outcome": False},
            {"name": "Deep technical thread", "depth": 5, "participants": 2, "has_code_refs": True, "has_action_outcome": False},
            {"name": "Spam/newsletter", "depth": 1, "participants": 1, "has_code_refs": False, "has_action_outcome": False},
        ]
        print("=" * 50)
        print("EMAIL RELEVANCE SCORING (PageRank for Memory)")
        print("=" * 50)
        for s in samples:
            result = email_relevance_score(s)
            print(f"\n{s['name']}:")
            print(f"  Score: {result['score']} → {result['recommendation']}")
            print(f"  Factors: {result['factors']}")
        return

    if not os.path.exists(MEMORY_FILE):
        print("No MEMORY.md found")
        return
    
    text = Path(MEMORY_FILE).read_text()
    claims = extract_claims(text)
    claims = compute_staleness(claims)
    
    if args.domain:
        claims = [c for c in claims if c["domain"] == args.domain]
    if args.stale_only:
        claims = [c for c in claims if c.get("staleness") == "stale"]
    
    summary = calibration_summary(claims)
    xref = cross_reference_dailies(claims)
    foraging = foraging_cost_estimate(claims)
    
    if args.json:
        print(json.dumps({
            "summary": summary,
            "cross_reference": xref,
            "foraging_cost": foraging,
            "claims_count": len(claims),
        }, indent=2))
        return
    
    print("=" * 60)
    print("FOK CALIBRATION REPORT")
    print("=" * 60)
    
    print(f"\nTotal claims extracted: {len(claims)}")
    print(f"\n{'Domain':<20} {'Total':>5} {'Fresh':>5} {'Aging':>5} {'Stale':>5} {'Conf':>6}")
    print("-" * 52)
    for domain, s in summary.items():
        conf = f"{s['avg_confidence']:.2f}" if s['avg_confidence'] is not None else "  n/a"
        print(f"{s['label']:<20} {s['total']:>5} {s['fresh']:>5} {s['aging']:>5} {s['stale']:>5} {conf:>6}")
    
    print(f"\n--- Cross-Reference (last 7 days) ---")
    print(f"Reinforced: {xref['reinforced']} | Orphaned: {xref['orphaned']} | Rate: {xref['reinforcement_rate']:.1%}")
    
    print(f"\n--- Foraging Cost (Pirolli & Card) ---")
    print(f"Should verify: {foraging['should_verify']}/{foraging['total_claims']} claims")
    print(f"Token savings with calibration: {foraging['token_savings']} tokens ({foraging['savings_pct']}%)")
    
    # Show top stale claims
    stale = [c for c in claims if c.get("staleness") == "stale"]
    if stale:
        print(f"\n--- Top Stale Claims ({len(stale)}) ---")
        for c in sorted(stale, key=lambda x: x.get("confidence", 1))[:5]:
            print(f"  [{c['domain']}] conf={c['confidence']} age={c['age_days']}d: {c['content'][:80]}")


if __name__ == "__main__":
    main()
