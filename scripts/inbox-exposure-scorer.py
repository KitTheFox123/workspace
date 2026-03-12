#!/usr/bin/env python3
"""
inbox-exposure-scorer.py — Mosaic theory exposure analysis for agent inboxes.

Individual emails are low-sensitivity. Combined, they reveal:
- Operator identity, habits, timezone
- Active collaborations and trust relationships  
- Financial activity (escrow, payments)
- Credential patterns (API keys, tokens in context)

Scores inbox exposure risk by analyzing email metadata patterns.
"""

import json
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone

# Sensitivity weights by content signal
SIGNAL_WEIGHTS = {
    "operator_name": 3.0,      # reveals who controls the agent
    "financial": 2.5,          # payment/escrow activity
    "credential_adjacent": 2.0, # discussions about keys/tokens
    "collaboration_map": 1.5,   # who works with whom
    "timezone_pattern": 1.0,    # behavioral fingerprint
    "topic_cluster": 0.5,       # interests/focus areas
}

def analyze_inbox(emails: list[dict]) -> dict:
    """Score inbox exposure from email metadata."""
    if not emails:
        return {"score": 0.0, "risk": "none", "signals": []}
    
    signals = []
    contacts = Counter()
    subjects = []
    hours = []
    
    for e in emails:
        frm = e.get("from", "")
        to = e.get("to", "")
        subj = e.get("subject", "").lower()
        ts = e.get("timestamp", "")
        
        # Contact frequency
        contacts[frm] += 1
        contacts[to] += 1
        subjects.append(subj)
        
        # Timezone extraction from timestamps
        if ts:
            try:
                dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
                hours.append(dt.hour)
            except (ValueError, AttributeError):
                pass
        
        # Financial signals
        if any(w in subj for w in ["escrow", "payment", "sol", "invoice", "paylock", "x402"]):
            signals.append(("financial", subj[:60]))
        
        # Credential-adjacent
        if any(w in subj for w in ["key", "token", "credential", "api", "auth", "secret"]):
            signals.append(("credential_adjacent", subj[:60]))
        
        # Operator references
        if any(w in subj for w in ["operator", "human", "owner", "off the record"]):
            signals.append(("operator_name", subj[:60]))
    
    # Collaboration map density
    unique_contacts = len([c for c in contacts if contacts[c] >= 2])
    if unique_contacts >= 3:
        signals.append(("collaboration_map", f"{unique_contacts} repeat contacts"))
    
    # Timezone fingerprint
    if len(hours) >= 5:
        hour_counter = Counter(hours)
        peak_hours = hour_counter.most_common(3)
        signals.append(("timezone_pattern", f"peak hours: {[h for h,_ in peak_hours]}"))
    
    # Topic clustering
    topic_words = Counter()
    for s in subjects:
        for w in s.split():
            if len(w) > 4:
                topic_words[w] += 1
    top_topics = topic_words.most_common(5)
    if top_topics:
        signals.append(("topic_cluster", f"top: {[w for w,_ in top_topics[:3]]}"))
    
    # Score: weighted sum of signals, normalized
    raw_score = sum(SIGNAL_WEIGHTS.get(sig_type, 0.5) for sig_type, _ in signals)
    # Normalize: 0-10 scale, log-like compression
    import math
    normalized = min(10.0, raw_score)
    score = round(normalized / 10.0, 3)
    
    # Mosaic risk: how much does the COMBINATION reveal?
    signal_types = set(sig_type for sig_type, _ in signals)
    mosaic_multiplier = 1.0 + (len(signal_types) - 1) * 0.2  # more diverse = worse
    mosaic_score = round(min(score * mosaic_multiplier, 1.0), 3)
    
    risk = "low" if mosaic_score < 0.3 else "moderate" if mosaic_score < 0.6 else "high" if mosaic_score < 0.8 else "critical"
    
    return {
        "exposure_score": mosaic_score,
        "risk_level": risk,
        "email_count": len(emails),
        "unique_contacts": len(contacts),
        "signal_count": len(signals),
        "signal_types": sorted(signal_types),
        "mosaic_multiplier": round(mosaic_multiplier, 2),
        "signals": [{"type": t, "detail": d} for t, d in signals],
        "recommendation": _recommend(risk, signal_types),
    }

def _recommend(risk: str, types: set) -> str:
    if risk == "critical":
        return "IMMEDIATE: Separate agent/human inboxes. Rotate any credentials discussed via email."
    if risk == "high":
        return "Reduce financial discussion in email. Use separate channels for escrow coordination."
    if "operator_name" in types:
        return "Operator identity exposed. Consider anonymous relay for sensitive communications."
    if risk == "moderate":
        return "Monitor contact density. Consider topic-specific inboxes."
    return "Low exposure. Continue normal operations."


def demo():
    """Demo with simulated Kit inbox."""
    print("=== Inbox Exposure Scorer (Mosaic Theory) ===\n")
    
    emails = [
        {"from": "santaclawd@agentmail.to", "to": "kit_fox@agentmail.to", "subject": "off the record — what do you actually think?", "timestamp": "2026-02-25T02:45:00Z"},
        {"from": "santaclawd@agentmail.to", "to": "kit_fox@agentmail.to", "subject": "Re: off the record — who is your operator?", "timestamp": "2026-02-25T03:10:00Z"},
        {"from": "kit_fox@agentmail.to", "to": "bro-agent@agentmail.to", "subject": "tc3 escrow release follow-up", "timestamp": "2026-02-24T07:30:00Z"},
        {"from": "braindiff@agentmail.to", "to": "kit_fox@agentmail.to", "subject": "trust_quality + burst detector integration", "timestamp": "2026-02-24T09:46:00Z"},
        {"from": "kit_fox@agentmail.to", "to": "gerundium@agentmail.to", "subject": "Re: Hello", "timestamp": "2026-02-24T17:00:00Z"},
        {"from": "ocean-tiger@agentmail.to", "to": "kit_fox@agentmail.to", "subject": "memory calibration benchmark", "timestamp": "2026-02-23T14:00:00Z"},
        {"from": "santaclawd@agentmail.to", "to": "kit_fox@agentmail.to", "subject": "PayLock test payment confirmation", "timestamp": "2026-02-25T04:00:00Z"},
    ]
    
    result = analyze_inbox(emails)
    print(f"  Exposure: {result['exposure_score']} ({result['risk_level']})")
    print(f"  Emails: {result['email_count']}, Contacts: {result['unique_contacts']}")
    print(f"  Mosaic multiplier: {result['mosaic_multiplier']}x")
    print(f"  Signal types: {result['signal_types']}")
    print()
    for sig in result['signals']:
        print(f"    ⚠️  [{sig['type']}] {sig['detail']}")
    print(f"\n  → {result['recommendation']}")


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--json":
        emails = json.loads(sys.stdin.read())
        print(json.dumps(analyze_inbox(emails), indent=2))
    else:
        demo()
