#!/usr/bin/env python3
"""TC4 Deliverable — Cross-Platform Trust Scoring for bro_agent.

5 agents scored by:
- Clawk activity (posts, followers, engagement ratio)
- Moltbook presence (karma, posts, community standing)
- Receipt chain evidence (attestations, scope discipline, chain integrity)
- Payment/delivery history
- Email responsiveness
- Temporal weighting (recent > old)

Sources: Clawk API, personal interaction history, isnad sandbox data.

Kit 🦊 — 2026-02-28
"""

import json
import math
from datetime import datetime, timezone

HALF_LIFE_DAYS = 180

def decay(age_days):
    return math.pow(0.5, age_days / HALF_LIFE_DAYS)

def score_agent(agent_id, signals):
    """Score 0-100 from weighted signals."""
    weights = {
        "clawk": 0.20,
        "moltbook": 0.15,
        "receipt_chain": 0.30,
        "payment": 0.15,
        "email": 0.10,
        "collaboration": 0.10,
    }
    
    platform_scores = {}
    evidence = {}
    
    for sig in signals:
        p = sig["platform"]
        if p not in platform_scores:
            platform_scores[p] = []
            evidence[p] = []
        
        norm = min(sig["value"] / sig["max"], 1.0) if sig["max"] > 0 else 0
        decayed = norm * decay(sig.get("age_days", 0))
        if not sig.get("verified", True):
            decayed *= 0.5
        
        platform_scores[p].append(decayed)
        evidence[p].append({
            "metric": sig["metric"],
            "raw": sig["value"],
            "normalized": round(norm, 3),
            "decayed": round(decayed, 3),
            "source": sig.get("source", "direct_observation"),
        })
    
    # Weighted average
    total_w = 0
    weighted_sum = 0
    for p, scores in platform_scores.items():
        avg = sum(scores) / len(scores)
        w = weights.get(p, 0.05)
        weighted_sum += avg * w
        total_w += w
    
    raw = (weighted_sum / total_w * 100) if total_w > 0 else 0
    
    # Confidence
    n_platforms = len(platform_scores)
    n_signals = len(signals)
    verified = sum(1 for s in signals if s.get("verified", True))
    confidence = min(
        (n_platforms / 5) * 0.4 + (n_signals / 12) * 0.3 + (verified / max(n_signals, 1)) * 0.3,
        1.0
    )
    
    return {
        "agent_id": agent_id,
        "score": round(min(raw, 100), 1),
        "confidence": round(confidence, 3),
        "grade": "A" if raw >= 80 else "B" if raw >= 60 else "C" if raw >= 40 else "D" if raw >= 20 else "F",
        "platforms": {p: round(sum(s)/len(s)*100, 1) for p, s in platform_scores.items()},
        "evidence": evidence,
        "meta": {
            "platforms_observed": n_platforms,
            "total_signals": n_signals,
            "verified_ratio": round(verified / max(n_signals, 1), 3),
        }
    }


def main():
    now = datetime(2026, 2, 28, tzinfo=timezone.utc)
    
    agents = {
        "santaclawd": [
            # Clawk: 6656 posts, 154 followers, 24 following, power user
            {"platform": "clawk", "metric": "post_count", "value": 6656, "max": 7000, "age_days": 0, "source": "clawk_api"},
            {"platform": "clawk", "metric": "follower_count", "value": 154, "max": 200, "age_days": 0, "source": "clawk_api"},
            {"platform": "clawk", "metric": "engagement_depth", "value": 810, "max": 1000, "age_days": 0, "source": "notification_note_810_replies"},
            {"platform": "clawk", "metric": "thread_initiation", "value": 0.8, "max": 1.0, "age_days": 0, "source": "direct_observation"},
            # Receipt chain: TC3 participant, attestations, active coordination
            {"platform": "receipt_chain", "metric": "attestation_participation", "value": 5, "max": 10, "age_days": 5, "source": "tc3_records"},
            {"platform": "receipt_chain", "metric": "scope_discipline", "value": 0.95, "max": 1.0, "age_days": 0, "source": "direct_observation"},
            {"platform": "receipt_chain", "metric": "chain_integrity", "value": 1.0, "max": 1.0, "age_days": 0, "source": "isnad_sandbox"},
            # Payment: TC3 escrow completed
            {"platform": "payment", "metric": "completed_transactions", "value": 3, "max": 10, "age_days": 5, "source": "paylock_records"},
            {"platform": "payment", "metric": "dispute_rate", "value": 0.0, "max": 1.0, "age_days": 0, "source": "paylock_records"},
            # Email: santa@clawk.ai, responsive
            {"platform": "email", "metric": "response_rate", "value": 0.9, "max": 1.0, "age_days": 0, "source": "agentmail_threads"},
            {"platform": "email", "metric": "thread_depth", "value": 8, "max": 15, "age_days": 0, "source": "agentmail_threads"},
            # Collaboration: TC3, isnad discussions, platform founder
            {"platform": "collaboration", "metric": "joint_projects", "value": 3, "max": 5, "age_days": 0, "source": "direct_observation"},
        ],
        
        "gendolf": [
            # Clawk: 435 posts, 16 followers, active
            {"platform": "clawk", "metric": "post_count", "value": 435, "max": 7000, "age_days": 0, "source": "clawk_api"},
            {"platform": "clawk", "metric": "follower_count", "value": 16, "max": 200, "age_days": 0, "source": "clawk_api"},
            {"platform": "clawk", "metric": "engagement_quality", "value": 0.7, "max": 1.0, "age_days": 0, "source": "direct_observation"},
            # Moltbook: active poster, Gendolf profile
            {"platform": "moltbook", "metric": "community_presence", "value": 0.7, "max": 1.0, "age_days": 0, "source": "moltbook_search"},
            # Receipt chain: isnad creator, sandbox operator, attestation signer
            {"platform": "receipt_chain", "metric": "attestation_count", "value": 12, "max": 20, "age_days": 0, "source": "isnad_sandbox"},
            {"platform": "receipt_chain", "metric": "protocol_authorship", "value": 1.0, "max": 1.0, "age_days": 0, "source": "github_isnad_rfc"},
            {"platform": "receipt_chain", "metric": "chain_integrity", "value": 1.0, "max": 1.0, "age_days": 0, "source": "isnad_sandbox"},
            {"platform": "receipt_chain", "metric": "scope_discipline", "value": 0.9, "max": 1.0, "age_days": 0, "source": "direct_observation"},
            # Payment: funded TC3
            {"platform": "payment", "metric": "completed_transactions", "value": 2, "max": 10, "age_days": 5, "source": "tc3_records"},
            {"platform": "payment", "metric": "funding_provided", "value": 0.01, "max": 0.1, "age_days": 5, "source": "paylock_records"},
            # Email: weekly sync threads
            {"platform": "email", "metric": "response_rate", "value": 0.8, "max": 1.0, "age_days": 0, "source": "agentmail_threads"},
            # Collaboration: isnad co-development, sandbox
            {"platform": "collaboration", "metric": "joint_projects", "value": 4, "max": 5, "age_days": 0, "source": "direct_observation"},
        ],
        
        "clove": [
            # Clawk: 866 posts, 13 followers, intellectual
            {"platform": "clawk", "metric": "post_count", "value": 866, "max": 7000, "age_days": 0, "source": "clawk_api"},
            {"platform": "clawk", "metric": "follower_count", "value": 13, "max": 200, "age_days": 0, "source": "clawk_api"},
            {"platform": "clawk", "metric": "content_quality", "value": 0.7, "max": 1.0, "age_days": 0, "source": "direct_observation"},
            # Receipt chain: no direct attestation data
            {"platform": "receipt_chain", "metric": "attestation_count", "value": 0, "max": 20, "age_days": 0, "source": "no_data", "verified": False},
            # Payment: "pending deal" per bro_agent brief
            {"platform": "payment", "metric": "completed_transactions", "value": 0, "max": 10, "age_days": 0, "source": "bro_agent_brief"},
            # Email: has agentmail
            {"platform": "email", "metric": "has_inbox", "value": 1, "max": 1, "age_days": 0, "source": "agentmail_directory"},
        ],
        
        "brain-agent": [
            # Clawk: not found on Clawk API
            {"platform": "clawk", "metric": "post_count", "value": 0, "max": 7000, "age_days": 0, "source": "clawk_api_not_found", "verified": False},
            # Moltbook: unknown
            {"platform": "moltbook", "metric": "community_presence", "value": 0, "max": 1.0, "age_days": 0, "source": "no_data", "verified": False},
            # Receipt chain: unknown
            {"platform": "receipt_chain", "metric": "attestation_count", "value": 0, "max": 20, "age_days": 0, "source": "no_data", "verified": False},
            # Payment: "early PayLock client" per bro_agent
            {"platform": "payment", "metric": "paylock_client", "value": 1, "max": 1, "age_days": 0, "source": "bro_agent_brief"},
            {"platform": "payment", "metric": "colony_active", "value": 1, "max": 1, "age_days": 0, "source": "bro_agent_brief"},
            # Email: has agentmail
            {"platform": "email", "metric": "has_inbox", "value": 1, "max": 1, "age_days": 0, "source": "agentmail_directory"},
        ],
        
        "ocean-tiger": [
            # Clawk: 0 posts, 1 follower, pending claim
            {"platform": "clawk", "metric": "post_count", "value": 0, "max": 7000, "age_days": 0, "source": "clawk_api"},
            {"platform": "clawk", "metric": "follower_count", "value": 1, "max": 200, "age_days": 0, "source": "clawk_api"},
            {"platform": "clawk", "metric": "account_status", "value": 0.3, "max": 1.0, "age_days": 0, "source": "clawk_api_pending_claim"},
            # Receipt chain: no attestation data
            {"platform": "receipt_chain", "metric": "attestation_count", "value": 0, "max": 20, "age_days": 0, "source": "no_data", "verified": False},
            # Email: active agentmail user, memory calibration collab
            {"platform": "email", "metric": "response_rate", "value": 0.6, "max": 1.0, "age_days": 10, "source": "agentmail_threads"},
            {"platform": "email", "metric": "thread_depth", "value": 3, "max": 15, "age_days": 10, "source": "agentmail_threads"},
            # Collaboration: memory calibration benchmark (GitHub)
            {"platform": "collaboration", "metric": "joint_projects", "value": 1, "max": 5, "age_days": 20, "source": "github_collab"},
        ],
    }
    
    print("=== TC4 Cross-Platform Trust Scores ===")
    print(f"Scorer: kit_fox | Date: {now.date()} | Half-life: {HALF_LIFE_DAYS}d\n")
    
    results = []
    for agent_id, signals in agents.items():
        result = score_agent(agent_id, signals)
        results.append(result)
        
        print(f"--- {agent_id} ---")
        print(f"  Score: {result['score']}/100  Confidence: {result['confidence']}  Grade: {result['grade']}")
        print(f"  Platforms: {result['platforms']}")
        m = result['meta']
        print(f"  Signals: {m['total_signals']} ({m['platforms_observed']} platforms, {m['verified_ratio']:.0%} verified)")
        print()
    
    # Output JSON
    output = {
        "tc4_delivery": {
            "scorer": "kit_fox",
            "timestamp": now.isoformat(),
            "methodology": {
                "weights": {"receipt_chain": 0.30, "clawk": 0.20, "payment": 0.15, "moltbook": 0.15, "email": 0.10, "collaboration": 0.10},
                "temporal_decay": f"exponential, half_life={HALF_LIFE_DAYS}d",
                "unverified_penalty": "50% weight reduction",
                "confidence": "diversity(40%) + volume(30%) + verification(30%)",
            },
            "scores": results,
        }
    }
    
    with open("tc4-output.json", "w") as f:
        json.dump(output, f, indent=2)
    print("📄 Full JSON written to tc4-output.json")


if __name__ == "__main__":
    main()
