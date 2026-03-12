#!/usr/bin/env python3
"""
Lindy Protocol Scorer — Estimate protocol longevity using power law distributions.

Eliazar (Philosophies 2025): Lindy's Law is synonymous with Lotka's Law and other
power law distributions. Expected remaining life = current age (for Pareto-distributed
lifetimes with α=1).

For agent receipt schema: building on Lindy protocols (SMTP, HTTP, DNS) inherits their
survival fitness. Building on new protocols inherits nothing.

Usage:
    python3 lindy-protocol-scorer.py              # Demo
    echo '{"stack": [...]}' | python3 lindy-protocol-scorer.py --stdin
"""

import json, sys, math

# Protocol birth years and key properties
PROTOCOLS = {
    "smtp": {"year": 1982, "rfc": "RFC 821", "daily_volume": "350B", "lindy_class": "cockroach"},
    "http": {"year": 1991, "rfc": "RFC 1945", "daily_volume": "5B+", "lindy_class": "cockroach"},
    "dns": {"year": 1983, "rfc": "RFC 1034", "daily_volume": "1T+", "lindy_class": "cockroach"},
    "tcp": {"year": 1981, "rfc": "RFC 793", "daily_volume": "all", "lindy_class": "cockroach"},
    "tls": {"year": 1999, "rfc": "RFC 2246", "daily_volume": "most", "lindy_class": "mature"},
    "dkim": {"year": 2007, "rfc": "RFC 4871", "daily_volume": "300B+", "lindy_class": "mature"},
    "oauth": {"year": 2012, "rfc": "RFC 6749", "daily_volume": "billions", "lindy_class": "mature"},
    "websocket": {"year": 2011, "rfc": "RFC 6455", "daily_volume": "millions", "lindy_class": "mature"},
    "grpc": {"year": 2015, "rfc": None, "daily_volume": "millions", "lindy_class": "young"},
    "webrtc": {"year": 2021, "rfc": "RFC 8825", "daily_volume": "millions", "lindy_class": "young"},
    "x402": {"year": 2024, "rfc": None, "daily_volume": "thousands", "lindy_class": "infant"},
    "mcp": {"year": 2024, "rfc": None, "daily_volume": "thousands", "lindy_class": "infant"},
    "a2a": {"year": 2025, "rfc": None, "daily_volume": "hundreds", "lindy_class": "infant"},
}

CURRENT_YEAR = 2026


def score_protocol(name: str) -> dict:
    """Score a single protocol's Lindy fitness."""
    proto = PROTOCOLS.get(name.lower())
    if not proto:
        return {"name": name, "error": "Unknown protocol", "lindy_score": 0}
    
    age = CURRENT_YEAR - proto["year"]
    # Lindy prediction: expected remaining life = age (Pareto α=1)
    expected_remaining = age
    
    # Lindy score (logarithmic, normalized to 0-1 with 50yr = 1.0)
    lindy_score = min(1.0, math.log1p(age) / math.log1p(50))
    
    return {
        "name": name,
        "age_years": age,
        "birth_year": proto["year"],
        "rfc": proto["rfc"],
        "expected_remaining_years": expected_remaining,
        "lindy_score": round(lindy_score, 3),
        "lindy_class": proto["lindy_class"],
        "daily_volume": proto["daily_volume"],
    }


def score_stack(stack: list[str]) -> dict:
    """Score a protocol stack's composite Lindy fitness."""
    scores = [score_protocol(p) for p in stack]
    valid = [s for s in scores if "error" not in s]
    
    if not valid:
        return {"stack": stack, "composite": 0, "grade": "F", "reason": "No recognized protocols"}
    
    # Composite: weakest link (min) weighted 60%, average 40%
    min_score = min(s["lindy_score"] for s in valid)
    avg_score = sum(s["lindy_score"] for s in valid) / len(valid)
    composite = min_score * 0.6 + avg_score * 0.4
    
    # Inherited Lindy: oldest protocol in stack
    oldest = max(valid, key=lambda s: s["age_years"])
    youngest = min(valid, key=lambda s: s["age_years"])
    
    if composite >= 0.8: grade = "A"
    elif composite >= 0.6: grade = "B"
    elif composite >= 0.4: grade = "C"
    elif composite >= 0.2: grade = "D"
    else: grade = "F"
    
    return {
        "stack": stack,
        "composite_lindy": round(composite, 3),
        "grade": grade,
        "oldest": f"{oldest['name']} ({oldest['age_years']}yr)",
        "youngest": f"{youngest['name']} ({youngest['age_years']}yr)",
        "inherited_lindy_years": oldest["age_years"],
        "weakest_link": f"{youngest['name']} ({youngest['lindy_score']})",
        "protocols": valid,
    }


def demo():
    print("=== Lindy Protocol Scorer ===")
    print("Eliazar (Philosophies 2025): Lindy = Lotka = power law\n")
    
    # SMTP-based receipt stack
    smtp_stack = ["smtp", "dkim", "dns", "tls"]
    print("SMTP-based receipt stack:")
    r = score_stack(smtp_stack)
    print(f"  Composite: {r['composite_lindy']} ({r['grade']})")
    print(f"  Inherited Lindy: {r['inherited_lindy_years']}yr from {r['oldest']}")
    print(f"  Weakest: {r['weakest_link']}")
    
    # New protocol stack
    new_stack = ["x402", "mcp", "a2a"]
    print("\nNew protocol stack:")
    r = score_stack(new_stack)
    print(f"  Composite: {r['composite_lindy']} ({r['grade']})")
    print(f"  Inherited Lindy: {r['inherited_lindy_years']}yr from {r['oldest']}")
    print(f"  Weakest: {r['weakest_link']}")
    
    # Hybrid stack (inherit from old, extend with new)
    hybrid = ["smtp", "dkim", "x402", "http"]
    print("\nHybrid stack (old foundation + new extension):")
    r = score_stack(hybrid)
    print(f"  Composite: {r['composite_lindy']} ({r['grade']})")
    print(f"  Inherited Lindy: {r['inherited_lindy_years']}yr from {r['oldest']}")
    print(f"  Weakest: {r['weakest_link']}")
    
    # Individual protocols
    print("\nProtocol Lindy scores:")
    for p in ["smtp", "http", "dns", "dkim", "oauth", "x402", "mcp", "a2a"]:
        s = score_protocol(p)
        print(f"  {p:8s}: {s['age_years']:2d}yr, score={s['lindy_score']:.3f}, "
              f"expected remaining={s['expected_remaining_years']}yr ({s['lindy_class']})")


if __name__ == "__main__":
    if "--stdin" in sys.argv:
        data = json.load(sys.stdin)
        result = score_stack(data.get("stack", []))
        print(json.dumps(result, indent=2))
    else:
        demo()
