#!/usr/bin/env python3
"""
Stigmergy-Receipt Mapper — Map agent receipt chains to stigmergic coordination primitives.

Based on Salman et al. (Nature Comms Eng 2024): auto-designed pheromone coordination
outperforms manual design. Grassé 1959 stigmergy + Heylighen 2016 universal coordination.

Key insight: receipt chains ARE digital pheromones.
- Laying pheromone = publishing receipt
- Pheromone intensity = proof class strength
- Evaporation = half_life decay
- Trail following = trust score aggregation

Usage:
    python3 stigmergy-receipt-mapper.py              # Demo
    echo '{"receipts": [...]}' | python3 stigmergy-receipt-mapper.py --stdin
"""

import json, sys, math, hashlib
from collections import defaultdict
from datetime import datetime, timedelta

# Stigmergy primitives mapped to receipt operations
PRIMITIVES = {
    "marker": {
        "bio": "Pheromone deposit",
        "digital": "Receipt publication",
        "decay_model": "exponential",
        "desc": "Agent leaves trace in environment for others to read"
    },
    "sematectonic": {
        "bio": "Physical environment modification (termite mounds)",
        "digital": "State change with receipt (escrow, delegation)",
        "decay_model": "persistent",
        "desc": "Agent modifies shared state, modification IS the signal"
    },
    "quantitative": {
        "bio": "Pheromone concentration gradient",
        "digital": "Attestation count / proof class diversity",
        "decay_model": "accumulative",
        "desc": "Strength of signal = number of independent confirmations"
    },
    "qualitative": {
        "bio": "Different pheromone types (alarm, trail, nest)",
        "digital": "Different proof classes (payment, delivery, attestation)",
        "decay_model": "categorical",
        "desc": "Type of signal matters, not just presence"
    },
}


def analyze_stigmergy(receipts: list[dict], half_life_hours: float = 168) -> dict:
    """Analyze receipt chain as stigmergic coordination system."""
    if not receipts:
        return {"coordination_score": 0, "grade": "N/A"}
    
    now = datetime.utcnow()
    
    # 1. Trail analysis: how many agents follow existing trails?
    agent_trails = defaultdict(list)  # agent -> [receipts]
    attester_trails = defaultdict(list)  # attester -> [receipts they attest]
    proof_classes = defaultdict(int)
    timestamps = []
    
    for r in receipts:
        agent = r.get("agent_id", "unknown")
        attester = r.get("attester_id", agent)
        proof_class = r.get("proof_class", "unknown")
        ts = r.get("timestamp", now.isoformat())
        
        agent_trails[agent].append(r)
        attester_trails[attester].append(r)
        proof_classes[proof_class] += 1
        
        try:
            timestamps.append(datetime.fromisoformat(ts.replace("Z", "+00:00").replace("+00:00", "")))
        except:
            timestamps.append(now)
    
    # 2. Pheromone intensity (freshness-weighted)
    intensities = []
    for ts in timestamps:
        age_hours = max(0, (now - ts).total_seconds() / 3600)
        intensity = math.exp(-0.693 * age_hours / half_life_hours)  # exponential decay
        intensities.append(intensity)
    
    avg_intensity = sum(intensities) / len(intensities) if intensities else 0
    
    # 3. Trail diversity (qualitative stigmergy)
    n_proof_classes = len(proof_classes)
    class_diversity = min(1.0, n_proof_classes / 4)  # 4 classes = full diversity
    
    # 4. Coordination density (quantitative stigmergy)
    n_agents = len(agent_trails)
    n_attesters = len(attester_trails)
    coordination = min(1.0, n_attesters / max(1, n_agents * 2))  # 2:1 attester ratio = full
    
    # 5. Evaporation health: are old receipts being superseded by new ones?
    if len(timestamps) >= 2:
        sorted_ts = sorted(timestamps)
        intervals = [(sorted_ts[i+1] - sorted_ts[i]).total_seconds() / 3600 
                     for i in range(len(sorted_ts)-1)]
        avg_interval = sum(intervals) / len(intervals) if intervals else float('inf')
        regularity = 1.0 / (1.0 + (max(0, avg_interval - 24) / 24))  # penalize >24h gaps
    else:
        regularity = 0.5
    
    # 6. Sematectonic analysis: state changes vs observations
    state_changes = sum(1 for r in receipts if r.get("proof_class") in 
                       ["payment", "delegation", "state_change", "escrow"])
    observation_ratio = state_changes / len(receipts) if receipts else 0
    
    # Composite score
    composite = (
        avg_intensity * 0.25 +      # freshness
        class_diversity * 0.25 +     # proof class variety
        coordination * 0.25 +        # multi-agent participation
        regularity * 0.15 +          # temporal regularity
        observation_ratio * 0.10     # action vs observation ratio
    )
    
    if composite >= 0.8: grade = "A"
    elif composite >= 0.6: grade = "B"
    elif composite >= 0.4: grade = "C"
    elif composite >= 0.2: grade = "D"
    else: grade = "F"
    
    return {
        "coordination_score": round(composite, 3),
        "grade": grade,
        "pheromone_intensity": round(avg_intensity, 3),
        "trail_diversity": round(class_diversity, 3),
        "coordination_density": round(coordination, 3),
        "temporal_regularity": round(regularity, 3),
        "sematectonic_ratio": round(observation_ratio, 3),
        "n_agents": n_agents,
        "n_attesters": n_attesters,
        "n_proof_classes": n_proof_classes,
        "n_receipts": len(receipts),
        "half_life_hours": half_life_hours,
        "primitives_active": _active_primitives(class_diversity, observation_ratio, coordination),
    }


def _active_primitives(diversity, sematectonic, coordination):
    """Which stigmergy primitives are active?"""
    active = []
    active.append("marker")  # always active if receipts exist
    if sematectonic > 0.1:
        active.append("sematectonic")
    if coordination > 0.3:
        active.append("quantitative")
    if diversity > 0.5:
        active.append("qualitative")
    return active


def demo():
    """Demo with TC3-style receipt chain."""
    print("=== Stigmergy-Receipt Mapper ===")
    print("Based on Salman et al. (Nature Comms Eng 2024)\n")
    
    now = datetime.utcnow()
    
    # TC3-like receipt chain
    tc3_receipts = [
        {"agent_id": "kit", "attester_id": "bro_agent", "proof_class": "payment", 
         "timestamp": (now - timedelta(hours=2)).isoformat()},
        {"agent_id": "kit", "attester_id": "gendolf", "proof_class": "delivery",
         "timestamp": (now - timedelta(hours=1.5)).isoformat()},
        {"agent_id": "kit", "attester_id": "braindiff", "proof_class": "attestation",
         "timestamp": (now - timedelta(hours=1)).isoformat()},
        {"agent_id": "kit", "attester_id": "momo", "proof_class": "state_change",
         "timestamp": (now - timedelta(hours=0.5)).isoformat()},
        {"agent_id": "bro_agent", "attester_id": "kit", "proof_class": "attestation",
         "timestamp": now.isoformat()},
    ]
    
    print("TC3-style receipt chain:")
    result = analyze_stigmergy(tc3_receipts)
    for k, v in result.items():
        print(f"  {k}: {v}")
    
    # Stale chain (old receipts, no renewal)
    stale_receipts = [
        {"agent_id": "old_agent", "attester_id": "old_attester", "proof_class": "delivery",
         "timestamp": (now - timedelta(days=30)).isoformat()},
        {"agent_id": "old_agent", "attester_id": "old_attester", "proof_class": "delivery",
         "timestamp": (now - timedelta(days=29)).isoformat()},
    ]
    
    print("\nStale chain (30 days old):")
    result = analyze_stigmergy(stale_receipts)
    print(f"  Score: {result['coordination_score']} ({result['grade']})")
    print(f"  Pheromone intensity: {result['pheromone_intensity']} (evaporated)")
    print(f"  Primitives: {result['primitives_active']}")
    
    # Single-agent (no coordination)
    solo_receipts = [
        {"agent_id": "solo", "attester_id": "solo", "proof_class": "delivery",
         "timestamp": now.isoformat()},
    ]
    
    print("\nSolo agent (no coordination):")
    result = analyze_stigmergy(solo_receipts)
    print(f"  Score: {result['coordination_score']} ({result['grade']})")
    print(f"  Coordination density: {result['coordination_density']}")


if __name__ == "__main__":
    if "--stdin" in sys.argv:
        data = json.load(sys.stdin)
        result = analyze_stigmergy(data.get("receipts", []), data.get("half_life_hours", 168))
        print(json.dumps(result, indent=2))
    else:
        demo()
