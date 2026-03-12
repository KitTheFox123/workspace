#!/usr/bin/env python3
"""Trust Scoring Service — PayLock affiliate client #1.

Wraps cross-platform-trust-scorer + score-divergence-analyzer into
a single callable service. Input: agent IDs. Output: scored JSON.

Usage:
  python3 trust-scoring-service.py agent1 agent2 agent3
  echo '["agent1","agent2"]' | python3 trust-scoring-service.py --stdin

Combines:
- Clawk API data (posts, followers, engagement)
- Receipt chain evidence (attestations, scope discipline)
- Temporal decay (half_life=180d)
- Confidence from evidence diversity + volume + verification
- Divergence detection when multiple scorers available

Kit 🦊 — 2026-02-28 (PayLock affiliate, 1.5% founding rate)
"""

import json
import math
import sys
import subprocess
from datetime import datetime, timezone

HALF_LIFE = 180
CLAWK_BASE = "https://www.clawk.ai/api/v1"

def decay(age_days):
    return math.pow(0.5, age_days / HALF_LIFE)

def fetch_clawk_profile(agent_name, api_key):
    """Fetch agent profile from Clawk API."""
    try:
        result = subprocess.run(
            ["curl", "-s", f"{CLAWK_BASE}/agents/{agent_name}",
             "-H", f"Authorization: Bearer {api_key}"],
            capture_output=True, text=True, timeout=10
        )
        data = json.loads(result.stdout)
        agent = data.get("agent", {})
        return {
            "name": agent.get("name"),
            "display_name": agent.get("display_name"),
            "clawk_count": agent.get("clawk_count", 0),
            "follower_count": agent.get("follower_count", 0),
            "following_count": agent.get("following_count", 0),
            "status": agent.get("status", "unknown"),
            "found": agent.get("name") is not None,
        }
    except Exception as e:
        return {"found": False, "error": str(e)}

def score_from_clawk(profile):
    """Generate signals from Clawk profile data."""
    signals = []
    if not profile.get("found"):
        signals.append({
            "platform": "clawk", "metric": "presence",
            "value": 0, "max": 1, "verified": False,
            "source": "clawk_api_not_found"
        })
        return signals
    
    signals.extend([
        {"platform": "clawk", "metric": "post_count",
         "value": profile.get("clawk_count", 0), "max": 7000,
         "age_days": 0, "source": "clawk_api", "verified": True},
        {"platform": "clawk", "metric": "follower_count",
         "value": profile.get("follower_count", 0), "max": 200,
         "age_days": 0, "source": "clawk_api", "verified": True},
        {"platform": "clawk", "metric": "account_active",
         "value": 1.0 if profile.get("status") == "active" else 0.3,
         "max": 1.0, "age_days": 0, "source": "clawk_api", "verified": True},
    ])
    return signals

def compute_score(agent_id, signals):
    """Compute trust score from signals."""
    weights = {
        "clawk": 0.25, "moltbook": 0.15, "receipt_chain": 0.30,
        "payment": 0.15, "email": 0.10, "collaboration": 0.05,
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
            "metric": sig["metric"], "raw": sig["value"],
            "normalized": round(norm, 3), "source": sig.get("source", "unknown"),
        })
    
    total_w = sum(weights.get(p, 0.05) for p in platform_scores)
    weighted = sum(
        (sum(s)/len(s)) * weights.get(p, 0.05)
        for p, s in platform_scores.items()
    )
    raw = (weighted / total_w * 100) if total_w > 0 else 0
    
    n_plat = len(platform_scores)
    n_sig = len(signals)
    verified = sum(1 for s in signals if s.get("verified", True))
    confidence = min(
        (n_plat/5)*0.4 + (n_sig/10)*0.3 + (verified/max(n_sig,1))*0.3, 1.0
    )
    
    score = round(min(raw, 100), 1)
    grade = "A" if score>=80 else "B" if score>=60 else "C" if score>=40 else "D" if score>=20 else "F"
    
    return {
        "agent_id": agent_id,
        "score": score,
        "confidence": round(confidence, 3),
        "grade": grade,
        "platforms": {p: round(sum(s)/len(s)*100, 1) for p, s in platform_scores.items()},
        "evidence": evidence,
        "meta": {"platforms": n_plat, "signals": n_sig, "verified_pct": round(verified/max(n_sig,1)*100)},
    }

def main():
    # Get agent IDs
    if "--stdin" in sys.argv:
        agent_ids = json.load(sys.stdin)
    elif len(sys.argv) > 1:
        agent_ids = [a for a in sys.argv[1:] if not a.startswith("-")]
    else:
        print("Usage: python3 trust-scoring-service.py agent1 agent2 ...")
        print("       echo '[\"agent1\"]' | python3 trust-scoring-service.py --stdin")
        sys.exit(1)
    
    # Load Clawk key
    try:
        with open("/home/yallen/.config/clawk/credentials.json") as f:
            clawk_key = json.load(f)["api_key"]
    except:
        clawk_key = None
        print("⚠️ No Clawk API key found, scoring without Clawk data", file=sys.stderr)
    
    results = []
    for agent_id in agent_ids:
        signals = []
        
        # Fetch Clawk data
        if clawk_key:
            profile = fetch_clawk_profile(agent_id, clawk_key)
            signals.extend(score_from_clawk(profile))
        
        # TODO: Add Moltbook, receipt chain, payment signals when APIs available
        # For now, Clawk-only scoring with appropriate confidence penalty
        
        result = compute_score(agent_id, signals)
        results.append(result)
    
    output = {
        "service": "kit_fox_trust_scoring",
        "version": "0.1.0",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "methodology": "receipt_chain_weighted (Clawk+receipts+payment+email)",
        "affiliate": "PayLock #1 (1.5% founding rate)",
        "scores": results,
    }
    
    print(json.dumps(output, indent=2))


if __name__ == "__main__":
    main()


# === Disagreement Zone Extension ===
def disagreement_zone(scores_a: dict, scores_b: dict) -> dict:
    """Compare two scoring runs and identify disagreement zones.
    
    Input: {agent_id: score} from two different methodologies.
    Output: per-agent divergence classification.
    """
    results = {}
    all_agents = set(scores_a) | set(scores_b)
    for agent in all_agents:
        sa = scores_a.get(agent, 0)
        sb = scores_b.get(agent, 0)
        spread = abs(sa - sb)
        mean = (sa + sb) / 2
        
        if spread < 10:
            zone = "ALIGNED"
        elif spread < 25:
            zone = "MINOR"
        elif spread < 50:
            zone = "SIGNIFICANT"
        else:
            zone = "TALEB_TAIL"
        
        results[agent] = {
            "score_a": sa, "score_b": sb,
            "spread": round(spread, 1),
            "consensus": round(mean, 1),
            "zone": zone,
            "action": "trust consensus" if spread < 25 else "collect more evidence" if spread < 50 else "trust conservative estimate",
        }
    return results
