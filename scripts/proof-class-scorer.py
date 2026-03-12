#!/usr/bin/env python3
"""
proof-class-scorer.py — Score attestation bundles by proof CLASS diversity.

Thread insight (santaclawd/funwolf/kit, Feb 25): 
  - 3 proof classes: payment, generation, transport
  - Each answers a different question (skin-in-game, authorship, delivery)
  - Stacking same class = diminishing returns
  - Cross-class coverage = high confidence

Uses Shannon entropy across classes, not raw count.
Like corpus callosum: one good bridge > many redundant connections.
"""

import json
import math
import sys
from collections import Counter
from datetime import datetime, timezone

# Proof type → class mapping
PROOF_CLASSES = {
    # Payment class — proves economic commitment
    "x402_tx": "payment",
    "paylock": "payment",
    "escrow": "payment",
    "x402_receipt": "payment",
    
    # Generation class — proves authorship/creation
    "gen_sig": "generation",
    "generation_signature": "generation",
    "code_hash": "generation",
    "content_hash": "generation",
    
    # Transport class — proves delivery/routing
    "dkim": "transport",
    "smtp_receipt": "transport",
    "agentmail_delivery": "transport",
    "isnad": "transport",  # attestation chain = transport of trust
    
    # Witness class — proves observation
    "witness": "witness",
    "attestation": "witness",
    "clawtask": "witness",
}

# Attestation timing: generation-time (self-contained) vs verification-time (live dependency)
# santaclawd Feb 25: irreversible outputs need generation-time attestation
ATTESTATION_TIMING = {
    "x402_tx": "generation",      # on-chain = permanent
    "paylock": "generation",
    "escrow": "generation",
    "x402_receipt": "generation",
    "gen_sig": "generation",      # signed at creation
    "generation_signature": "generation",
    "code_hash": "generation",
    "content_hash": "generation",
    "dkim": "generation",         # signed at send time
    "smtp_receipt": "generation",
    "agentmail_delivery": "generation",
    "isnad": "verification",      # chain requires live resolution
    "witness": "verification",    # attestation at observation time
    "attestation": "verification",
    "clawtask": "verification",
}

# Half-life in hours: generation-time proofs decay slower
TIMING_HALF_LIFE = {
    "generation": 720,   # 30 days — self-contained, survives attester death
    "verification": 168, # 7 days — needs live dependency, decays faster
}

# Temporal class mapping — defense in depth by timescale (santaclawd Feb 25)
TEMPORAL_CLASS = {
    # Months — wallet/cert lifecycle
    "x402_tx": "months",
    "paylock": "months",
    "escrow": "months",
    "x402_receipt": "months",
    # Hours — session/delivery window
    "dkim": "hours",
    "smtp_receipt": "hours",
    "agentmail_delivery": "hours",
    "isnad": "hours",
    "witness": "hours",
    "attestation": "hours",
    "clawtask": "hours",
    # Seconds — per-action nonce
    "gen_sig": "seconds",
    "generation_signature": "seconds",
    "code_hash": "seconds",
    "content_hash": "seconds",
}

# Minimum classes for confidence tiers
TIERS = {
    3: "A",   # 3+ classes = high confidence
    2: "B",   # 2 classes = moderate
    1: "C",   # 1 class = low
    0: "F",   # no proofs
}


def classify_proofs(proofs: list[dict]) -> dict:
    """Classify proof bundle and score by class diversity."""
    classes = Counter()
    classified = []
    
    for p in proofs:
        ptype = p.get("proof_type", "unknown")
        pclass = PROOF_CLASSES.get(ptype, "unknown")
        classes[pclass] += 1
        classified.append({**p, "class": pclass})
    
    # Shannon entropy across classes (normalized)
    total = sum(classes.values())
    if total == 0:
        return {"score": 0.0, "tier": "F", "classes": {}, "proofs": []}
    
    entropy = 0.0
    for count in classes.values():
        p = count / total
        if p > 0:
            entropy -= p * math.log2(p)
    
    # Max entropy for observed number of classes
    n_classes = len(classes)
    max_entropy = math.log2(n_classes) if n_classes > 1 else 1.0
    normalized_entropy = entropy / max_entropy if max_entropy > 0 else 0.0
    
    # Score: class count matters most, entropy is bonus
    # 3+ classes = 0.8 base, entropy adds up to 0.2
    known_classes = {k: v for k, v in classes.items() if k != "unknown"}
    n_known = len(known_classes)
    
    base = min(n_known / 3.0, 1.0) * 0.8
    entropy_bonus = normalized_entropy * 0.2
    score = round(base + entropy_bonus, 3)
    
    # Tier
    tier = TIERS.get(min(n_known, 3), "F")
    
    # Redundancy warning
    warnings = []
    for cls, count in classes.items():
        if count > 2 and cls != "unknown":
            warnings.append(f"redundant: {count} proofs in '{cls}' class (diminishing returns)")
    
    # Temporal diversity bonus (santaclawd Feb 25: months/hours/seconds timescales)
    temporal_classes = set()
    for p in proofs:
        tc = TEMPORAL_CLASS.get(p.get("proof_type", ""))
        if tc:
            temporal_classes.add(tc)
    temporal_diversity = len(temporal_classes)
    
    # Up to 0.1 bonus for 3 distinct timescales
    temporal_bonus = min(temporal_diversity / 3.0, 1.0) * 0.1
    score = round(min(score + temporal_bonus, 1.0), 3)
    
    # Coverage gaps
    all_classes = {"payment", "generation", "transport"}
    missing = all_classes - set(known_classes.keys())
    if missing:
        warnings.append(f"missing classes: {', '.join(sorted(missing))}")
    
    return {
        "score": score,
        "tier": tier,
        "n_classes": n_known,
        "classes": dict(known_classes),
        "temporal_classes": sorted(temporal_classes),
        "temporal_diversity": round(temporal_diversity, 3),
        "entropy": round(entropy, 3),
        "warnings": warnings,
        "proofs": classified,
        "scored_at": datetime.now(timezone.utc).isoformat(),
    }


def from_x402_receipt(tx_hash: str, payer: str, payee: str, amount: str, chain: str = "base") -> dict:
    """Convert an x402 v2 receipt into a proof record."""
    return {
        "proof_type": "x402_tx",
        "issuer": payer,
        "subject": payee,
        "evidence_hash": tx_hash,
        "metadata": {"amount": amount, "chain": chain, "protocol": "x402v2"},
    }


def from_dkim_header(from_addr: str, claim_hash: str, dkim_domain: str) -> dict:
    """Convert a DKIM-signed email with X-Claim-Hash into a proof record."""
    return {
        "proof_type": "dkim",
        "issuer": dkim_domain,
        "subject": from_addr,
        "evidence_hash": claim_hash,
        "metadata": {"header": "X-Claim-Hash", "signing_method": "BYODKIM"},
    }


def from_generation_sig(creator: str, content_hash: str, sig: str) -> dict:
    """Convert a generation signature into a proof record."""
    return {
        "proof_type": "gen_sig",
        "issuer": creator,
        "evidence_hash": content_hash,
        "metadata": {"signature": sig[:16] + "..."},
    }


def validate_receipt(proof: dict) -> dict:
    """Validate individual proof receipt fields."""
    required = {"proof_type", "issuer"}
    recommended = {"claim_hash", "timestamp", "signature"}
    
    missing_req = required - set(proof.keys())
    missing_rec = recommended - set(proof.keys())
    
    valid = len(missing_req) == 0
    completeness = 1.0 - (len(missing_rec) / len(recommended)) * 0.3  # 30% penalty for missing recommended
    
    return {
        "valid": valid,
        "completeness": round(completeness, 2),
        "missing_required": list(missing_req),
        "missing_recommended": list(missing_rec),
    }


def validate_bundle(proofs: list[dict]) -> dict:
    """Validate full bundle: classify + validate each receipt."""
    result = classify_proofs(proofs)
    validations = [validate_receipt(p) for p in proofs]
    
    all_valid = all(v["valid"] for v in validations)
    avg_completeness = sum(v["completeness"] for v in validations) / len(validations) if validations else 0
    
    # Adjust score by completeness
    adjusted_score = round(result["score"] * avg_completeness, 3)
    
    return {
        **result,
        "adjusted_score": adjusted_score,
        "all_valid": all_valid,
        "avg_completeness": round(avg_completeness, 2),
        "receipt_validations": validations,
    }


def temporal_diversity(proofs: list[dict]) -> dict:
    """Score temporal pattern diversity across proof classes.
    
    Key insight: payment (persistent/session), generation (stateless/per-create),
    transport (per-message) have different natural frequencies. Faking all three
    temporal patterns simultaneously is much harder than faking one.
    """
    from collections import defaultdict
    
    class_timestamps = defaultdict(list)
    for p in proofs:
        ptype = p.get("proof_type", "unknown")
        pclass = PROOF_CLASSES.get(ptype, "unknown")
        ts = p.get("timestamp")
        if ts:
            try:
                dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
                class_timestamps[pclass].append(dt.timestamp())
            except (ValueError, AttributeError):
                pass
    
    if len(class_timestamps) < 2:
        return {"temporal_diversity": 0.0, "reason": "need 2+ classes with timestamps"}
    
    # Calculate inter-proof intervals per class
    class_intervals = {}
    for cls, timestamps in class_timestamps.items():
        if len(timestamps) >= 2:
            timestamps.sort()
            intervals = [timestamps[i+1] - timestamps[i] for i in range(len(timestamps)-1)]
            class_intervals[cls] = {
                "mean_interval": sum(intervals) / len(intervals),
                "count": len(timestamps),
            }
    
    # Temporal diversity = variance of mean intervals across classes
    # High variance = different temporal patterns = harder to fake
    if len(class_intervals) < 2:
        return {"temporal_diversity": 0.0, "reason": "need 2+ classes with multiple timestamps"}
    
    means = [v["mean_interval"] for v in class_intervals.values()]
    avg = sum(means) / len(means)
    variance = sum((m - avg) ** 2 for m in means) / len(means)
    cv = (variance ** 0.5) / avg if avg > 0 else 0
    
    # Normalize CV to 0-1 score (CV > 1 = high diversity)
    score = min(cv / 2.0, 1.0)
    
    return {
        "temporal_diversity": round(score, 3),
        "class_intervals": {k: round(v["mean_interval"], 1) for k, v in class_intervals.items()},
        "coefficient_of_variation": round(cv, 3),
    }


def temporal_diversity_score(proofs: list[dict]) -> dict:
    """Score by temporal diversity across proof classes.
    
    Insight (santaclawd Feb 25): payment=months, generation=minutes, DKIM=seconds.
    Attacker needs 3 different compromise strategies at 3 timescales.
    """
    TIMESCALES = {
        "payment": 86400 * 30,     # ~months (wallet lifecycle)
        "generation": 60 * 10,      # ~minutes (per-task)
        "transport": 60,             # ~seconds (per-message)
        "witness": 3600,             # ~hours (observation window)
    }
    
    classes_present = set()
    for p in proofs:
        ptype = p.get("proof_type", "unknown")
        pclass = PROOF_CLASSES.get(ptype, "unknown")
        if pclass != "unknown":
            classes_present.add(pclass)
    
    if len(classes_present) < 2:
        return {"temporal_diversity": 0.0, "timescales": 1, "attack_cost_multiplier": 1.0}
    
    timescales = [TIMESCALES.get(c, 3600) for c in classes_present]
    # Ratio of max to min timescale = attack surface diversity
    ratio = max(timescales) / min(timescales) if min(timescales) > 0 else 1
    
    # Score: log-scaled ratio normalized to 0-1
    import math
    score = min(math.log10(ratio) / 6.0, 1.0)  # 6 orders of magnitude = perfect
    
    return {
        "temporal_diversity": round(score, 3),
        "timescales": len(set(timescales)),
        "attack_cost_multiplier": round(ratio, 1),
        "classes": sorted(classes_present),
    }


def demo():
    """Demo with tc3-like bundles."""
    print("=== Proof Class Scorer ===\n")
    
    bundles = {
        "tc3 (3 classes)": [
            {"proof_type": "x402_tx", "issuer": "bro_agent"},
            {"proof_type": "gen_sig", "issuer": "kit_fox"},
            {"proof_type": "dkim", "issuer": "agentmail"},
        ],
        "sybil (5 same class)": [
            {"proof_type": "witness", "issuer": "bot1"},
            {"proof_type": "witness", "issuer": "bot2"},
            {"proof_type": "attestation", "issuer": "bot3"},
            {"proof_type": "clawtask", "issuer": "bot4"},
            {"proof_type": "witness", "issuer": "bot5"},
        ],
        "strong (4 classes)": [
            {"proof_type": "paylock", "issuer": "gendolf"},
            {"proof_type": "content_hash", "issuer": "kit_fox"},
            {"proof_type": "dkim", "issuer": "agentmail"},
            {"proof_type": "witness", "issuer": "momo"},
        ],
        "payment only": [
            {"proof_type": "x402_tx", "issuer": "agent1"},
            {"proof_type": "paylock", "issuer": "agent2"},
            {"proof_type": "escrow", "issuer": "agent3"},
        ],
    }
    
    for name, proofs in bundles.items():
        result = classify_proofs(proofs)
        print(f"  {name}:")
        print(f"    Score: {result['score']} ({result['tier']})")
        print(f"    Classes: {result['classes']}")
        if result['warnings']:
            for w in result['warnings']:
                print(f"    ⚠️  {w}")
        td = temporal_diversity_score(proofs)
        print(f"    Temporal: {td['temporal_diversity']} (attack cost {td['attack_cost_multiplier']}x)")
        print()


def surface():
    """Show 2D confidence surface: type diversity × temporal diversity."""
    print("=== 2D Confidence Surface (type × temporal) ===\n")
    print("Type diversity →  1-class    2-class    3-class    4-class")
    print("Temporal diversity ↓")
    
    # Simulate bundles at each intersection
    type_sets = [
        [("witness",)],          # 1 class
        [("x402_tx", "dkim")],   # 2 classes  
        [("x402_tx", "gen_sig", "dkim")],  # 3 classes
        [("x402_tx", "gen_sig", "dkim", "witness")],  # 4 classes
    ]
    temporal_labels = ["1 timescale", "2 timescales", "3 timescales"]
    temporal_types = [
        # 1 timescale: all hours
        lambda types: [{"proof_type": t, "issuer": f"a{i}"} for i, t in enumerate(types)],
        # 2 timescales: mix months + hours  
        lambda types: [{"proof_type": t, "issuer": f"a{i}"} for i, t in enumerate(types)],
        # 3 timescales: months + hours + seconds
        lambda types: [{"proof_type": t, "issuer": f"a{i}"} for i, t in enumerate(types)],
    ]
    
    for tl in temporal_labels:
        row = f"  {tl:14s}"
        for ts in type_sets:
            proofs = [{"proof_type": t, "issuer": f"a{i}"} for i, t in enumerate(ts[0])]
            r = classify_proofs(proofs)
            td = temporal_diversity_score(proofs)
            combined = round(r["score"] * 0.8 + td["temporal_diversity"] * 0.2, 2)
            row += f"  {combined:6.2f}({r['tier']}) "
        print(row)
    
    print()
    print("  Lesson: type diversity matters more, temporal is bonus.")
    print("  Gold standard: 3+ types × 3 timescales = A with max temporal bonus.")


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--json":
        proofs = json.loads(sys.stdin.read())
        result = classify_proofs(proofs)
        print(json.dumps(result, indent=2))
    elif len(sys.argv) > 1 and sys.argv[1] == "--surface":
        surface()
    else:
        demo()
