#!/usr/bin/env python3
"""Decay Prediction Error Tracker.

Extends fok-calibration.py with Ocean Tiger's insight:
track predicted vs actual staleness to self-correct decay rates.

Usage:
    python3 decay-prediction-error.py [--check] [--history FILE]
"""

import json
import re
import sys
import hashlib
from datetime import datetime, timedelta
from pathlib import Path

MEMORY_DIR = Path(__file__).parent.parent / "memory"
HISTORY_FILE = MEMORY_DIR / "decay-predictions.jsonl"

# Domain-specific half-lives (days) — from fok-calibration.py
DECAY_RATES = {
    "urls": 30,
    "apis": 45,
    "credentials": 90,
    "concepts": 180,
    "tools": 60,
    "dates": 365,
    "agent_names": 120,
    "quotes": 365,
    "default": 90,
}

def classify_claim(text: str) -> str:
    """Classify a claim into a decay domain."""
    text_lower = text.lower()
    if re.search(r'https?://', text):
        return "urls"
    if re.search(r'api|endpoint|/v\d|curl', text_lower):
        return "apis"
    if re.search(r'key|token|password|credential|bearer', text_lower):
        return "credentials"
    if re.search(r'script|tool|\.py|\.sh|install', text_lower):
        return "tools"
    if re.search(r'\d{4}-\d{2}-\d{2}|202[4-9]', text):
        return "dates"
    if re.search(r'@\w+|agent|bot|_bot', text_lower):
        return "agent_names"
    if re.search(r'"[^"]{20,}"', text):
        return "quotes"
    return "concepts"


def extract_claims(filepath: Path) -> list[dict]:
    """Extract claims from a markdown file."""
    claims = []
    text = filepath.read_text()
    for i, line in enumerate(text.split('\n'), 1):
        line = line.strip()
        if not line or line.startswith('#'):
            continue
        if line.startswith('- ') or line.startswith('* '):
            claim_text = line[2:].strip()
            if len(claim_text) > 20:
                domain = classify_claim(claim_text)
                claim_hash = hashlib.sha256(claim_text.encode()).hexdigest()[:12]
                claims.append({
                    "hash": claim_hash,
                    "domain": domain,
                    "text": claim_text[:120],
                    "source": f"{filepath.name}:{i}",
                })
    return claims


def predict_staleness(claim: dict, as_of: datetime) -> dict:
    """Predict when a claim will go stale."""
    half_life = DECAY_RATES.get(claim["domain"], DECAY_RATES["default"])
    # Extract date from source if possible
    date_match = re.search(r'(\d{4}-\d{2}-\d{2})', claim.get("source", ""))
    if date_match:
        created = datetime.strptime(date_match.group(1), "%Y-%m-%d")
    else:
        created = as_of - timedelta(days=30)  # assume ~1 month old
    
    age_days = (as_of - created).days
    # Probability of being stale: 1 - 2^(-age/half_life)
    staleness_prob = 1 - (2 ** (-age_days / half_life))
    predicted_stale_date = created + timedelta(days=half_life)
    
    return {
        **claim,
        "age_days": age_days,
        "half_life": half_life,
        "staleness_prob": round(staleness_prob, 3),
        "predicted_stale": predicted_stale_date.isoformat()[:10],
        "checked_at": as_of.isoformat()[:10],
    }


def record_prediction(prediction: dict):
    """Append prediction to JSONL history."""
    HISTORY_FILE.parent.mkdir(exist_ok=True)
    with open(HISTORY_FILE, "a") as f:
        f.write(json.dumps(prediction) + "\n")


def compute_prediction_errors() -> dict:
    """Compare past predictions against current reality."""
    if not HISTORY_FILE.exists():
        return {"error": "No prediction history yet. Run --check first."}
    
    predictions = []
    for line in HISTORY_FILE.read_text().strip().split('\n'):
        if line:
            predictions.append(json.loads(line))
    
    # Group by domain
    domain_errors = {}
    for p in predictions:
        domain = p["domain"]
        if domain not in domain_errors:
            domain_errors[domain] = {"predictions": 0, "total_prob": 0}
        domain_errors[domain]["predictions"] += 1
        domain_errors[domain]["total_prob"] += p["staleness_prob"]
    
    for domain, stats in domain_errors.items():
        stats["avg_staleness_prob"] = round(stats["total_prob"] / stats["predictions"], 3)
        del stats["total_prob"]
    
    return {
        "total_predictions": len(predictions),
        "domains": domain_errors,
        "unique_claims": len(set(p["hash"] for p in predictions)),
    }


def main():
    now = datetime.utcnow()
    check_mode = "--check" in sys.argv
    
    # Extract claims from MEMORY.md
    memory_file = Path(__file__).parent.parent / "MEMORY.md"
    claims = extract_claims(memory_file)
    
    print(f"Extracted {len(claims)} claims from MEMORY.md")
    print(f"\nDomain distribution:")
    domains = {}
    for c in claims:
        domains[c["domain"]] = domains.get(c["domain"], 0) + 1
    for d, count in sorted(domains.items(), key=lambda x: -x[1]):
        half_life = DECAY_RATES.get(d, DECAY_RATES["default"])
        print(f"  {d:15s}: {count:3d} claims (half-life: {half_life}d)")
    
    # Predict staleness
    predictions = [predict_staleness(c, now) for c in claims]
    
    # Top 10 most likely stale
    stale = sorted(predictions, key=lambda x: -x["staleness_prob"])[:10]
    print(f"\nTop 10 most likely stale:")
    for p in stale:
        print(f"  [{p['staleness_prob']:.0%}] ({p['domain']}) {p['text'][:80]}")
    
    if check_mode:
        for p in predictions:
            record_prediction(p)
        print(f"\nRecorded {len(predictions)} predictions to {HISTORY_FILE}")
    
    # Show prediction errors if history exists
    errors = compute_prediction_errors()
    if "error" not in errors:
        print(f"\nPrediction history: {errors['total_predictions']} total, {errors['unique_claims']} unique claims")
        for domain, stats in sorted(errors["domains"].items()):
            print(f"  {domain:15s}: {stats['predictions']:3d} checks, avg staleness: {stats['avg_staleness_prob']:.1%}")


if __name__ == "__main__":
    main()
