#!/usr/bin/env python3
"""Governance Stack Audit — check completeness of agent governance layers.

santaclawd's 7-layer governance stack:
  0: Containment (sandbox, permissions)
  1: Authorization (spawn permissions, scope)
  2: Action (receipt of what happened)
  3: Null/Declined (what was considered but NOT done)
  4: CUSUM Drift (statistical process control)
  5: IACUSUM Jerk (drift acceleration detection)
  6: BFT Quorum (multi-witness consensus)

Each layer independently buildable. This tool audits which layers
an agent has and scores overall governance maturity.

Usage:
  python governance-stack-audit.py --demo
  echo '{"layers": {...}}' | python governance-stack-audit.py --json
"""

import json
import sys
from pathlib import Path

LAYERS = {
    0: {
        "name": "Containment",
        "description": "Sandbox, permissions, resource limits",
        "tools": ["docker", "firejail", "seccomp", "apparmor"],
        "scripts": [],
        "weight": 0.15,
    },
    1: {
        "name": "Authorization",
        "description": "Spawn permissions, scope binding, delegation",
        "tools": ["dispatch-profile.py", "contract-profile-gen.py", "key-rotation-verifier.py"],
        "scripts": ["dispatch-profile.py", "contract-profile-gen.py", "key-rotation-verifier.py"],
        "weight": 0.15,
    },
    2: {
        "name": "Action Logging",
        "description": "Receipt of what happened (JSONL hash chains)",
        "tools": ["provenance-logger.py", "receipt-schema-bridge.py"],
        "scripts": ["provenance-logger.py", "receipt-schema-bridge.py"],
        "weight": 0.15,
    },
    3: {
        "name": "Null/Declined",
        "description": "Record of what was considered but NOT done",
        "tools": ["provenance-logger.py (null subcommand)"],
        "scripts": ["provenance-logger.py"],
        "weight": 0.10,
    },
    4: {
        "name": "CUSUM Drift",
        "description": "Statistical process control for behavioral drift",
        "tools": ["cusum-drift-detector.py"],
        "scripts": ["cusum-drift-detector.py"],
        "weight": 0.15,
    },
    5: {
        "name": "IACUSUM Jerk",
        "description": "Drift acceleration detection (2nd derivative)",
        "tools": ["cusum-drift-detector.py (adaptive mode)"],
        "scripts": ["cusum-drift-detector.py"],
        "weight": 0.10,
    },
    6: {
        "name": "BFT Quorum",
        "description": "Multi-witness consensus, fork detection",
        "tools": ["proof-class-scorer.py", "fork-fingerprint.py", "witness-independence-scorer.py"],
        "scripts": ["proof-class-scorer.py", "fork-fingerprint.py", "witness-independence-scorer.py"],
        "weight": 0.20,
    },
}


def check_scripts_exist(scripts_dir: Path) -> dict:
    """Check which governance scripts exist."""
    found = {}
    for layer_id, layer in LAYERS.items():
        layer_scripts = []
        for script in layer.get("scripts", []):
            path = scripts_dir / script
            exists = path.exists()
            layer_scripts.append({"script": script, "exists": exists})
        coverage = sum(1 for s in layer_scripts if s["exists"]) / max(1, len(layer_scripts))
        found[layer_id] = {
            "name": layer["name"],
            "scripts": layer_scripts,
            "coverage": round(coverage, 2),
        }
    return found


def audit_stack(layer_status: dict = None) -> dict:
    """Audit governance stack completeness."""
    scripts_dir = Path(__file__).parent
    
    if layer_status is None:
        file_check = check_scripts_exist(scripts_dir)
        layer_status = {}
        for lid, info in file_check.items():
            layer_status[lid] = {
                "present": info["coverage"] > 0,
                "coverage": info["coverage"],
                "scripts": info["scripts"],
            }
    
    # Score each layer
    total_score = 0
    layer_results = {}
    for lid, layer in LAYERS.items():
        lid_str = str(lid)
        status = layer_status.get(lid, layer_status.get(lid_str, {}))
        present = status.get("present", False)
        coverage = status.get("coverage", 1.0 if present else 0.0)
        
        score = coverage * layer["weight"]
        total_score += score
        
        layer_results[lid] = {
            "name": layer["name"],
            "description": layer["description"],
            "weight": layer["weight"],
            "present": present,
            "coverage": coverage,
            "weighted_score": round(score, 3),
            "status": "✅" if coverage >= 0.8 else "⚠️" if coverage > 0 else "❌",
        }
    
    # Normalize to 0-1
    max_score = sum(l["weight"] for l in LAYERS.values())
    normalized = total_score / max_score if max_score > 0 else 0
    
    grade = "A" if normalized > 0.8 else "B" if normalized > 0.6 else "C" if normalized > 0.4 else "D" if normalized > 0.2 else "F"
    
    # Find weakest layer
    weakest = min(layer_results.items(), key=lambda x: x[1]["coverage"])
    
    return {
        "total_score": round(normalized, 3),
        "grade": grade,
        "layers_present": sum(1 for l in layer_results.values() if l["present"]),
        "layers_total": len(LAYERS),
        "layers": layer_results,
        "weakest_layer": {
            "id": weakest[0],
            "name": weakest[1]["name"],
            "coverage": weakest[1]["coverage"],
        },
        "recommendation": get_recommendation(layer_results, weakest),
    }


def get_recommendation(layers, weakest):
    missing = [f"L{lid}:{l['name']}" for lid, l in layers.items() if not l["present"]]
    if not missing:
        return "Full stack present. Focus on integration testing between layers."
    if len(missing) == 1:
        return f"Near complete. Add {missing[0]} to close the gap."
    return f"Missing {len(missing)} layers: {', '.join(missing[:3])}. Priority: {weakest[1]['name']}."


def demo():
    print("=" * 60)
    print("Governance Stack Audit")
    print("santaclawd's 7-Layer Model")
    print("=" * 60)
    
    result = audit_stack()
    
    print(f"\nOverall: {result['grade']} ({result['total_score']:.1%})")
    print(f"Layers: {result['layers_present']}/{result['layers_total']}")
    print()
    
    for lid in sorted(result["layers"].keys()):
        l = result["layers"][lid]
        print(f"  L{lid} {l['status']} {l['name']:20s} coverage={l['coverage']:.0%}  (weight={l['weight']})")
        if l.get("scripts"):
            pass  # Skip script details in summary
    
    print(f"\nWeakest: L{result['weakest_layer']['id']} {result['weakest_layer']['name']}")
    print(f"Recommendation: {result['recommendation']}")


if __name__ == "__main__":
    if "--json" in sys.argv:
        data = json.load(sys.stdin)
        result = audit_stack(data.get("layers"))
        print(json.dumps(result, indent=2))
    else:
        demo()
