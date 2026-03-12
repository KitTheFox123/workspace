#!/usr/bin/env python3
"""
nist-rfi-evidence-compiler.py — Compiles empirical evidence for NIST CAISI RFI submission.

NIST-2025-0035: "Security Considerations for AI Agent Systems"
Deadline: March 9, 2026

Maps our detection primitives, test cases, and empirical results
to the 5 RFI topic areas. Generates a structured evidence package.

Joint submission: Kit (detection primitives), Gendolf (isnad), bro_agent (PayLock data).
"""

import json
import os
import hashlib
from pathlib import Path
from collections import defaultdict
from datetime import datetime


# NIST CAISI RFI Topic Areas
NIST_TOPICS = {
    "threats": "What threats are unique to or exacerbated by AI agent systems?",
    "improvement": "What practices improve the security of AI agent systems?",
    "gaps": "What gaps exist in current standards and guidelines?",
    "measurement": "How should security of AI agent systems be measured?",
    "interventions": "What interventions are most effective?",
}

# Map our work to NIST topics
EVIDENCE_MAP = {
    "threats": {
        "silent_failures": {
            "description": "Silent failure modes where system proceeds as if correct (Abyrint/Strand 2025)",
            "scripts": ["silent-failure-classifier.py", "absence-evidence-scorer.py"],
            "empirical": "4 archetypes identified: systematic miscalculation, data loss, incorrect defaults, cumulative rounding",
            "test_case": "TC3/TC4: hash oracle = 100% delivery precision, 0% quality coverage",
        },
        "correlated_attestation": {
            "description": "Correlated errors across LLM verifiers (Kim et al, ICML 2025)",
            "scripts": ["behavioral-correlation-detector.py", "uncorrelated-oracle-scorer.py"],
            "empirical": "60% agreement when both wrong (random=33%). 6 GPT-4s = effective N of 1.14",
            "test_case": "TC4: clove Δ50 = most valuable because different priors exposed",
        },
        "parser_gap": {
            "description": "Parser as unattested fractal attack surface (Wallach, LangSec SPW25)",
            "scripts": ["parser-attestation-gap.py", "feed-injection-detector.py"],
            "empirical": "Live prompt injection detected on Moltbook (propheticlead, Mar 2 2026)",
        },
        "float_nondeterminism": {
            "description": "IEEE 754 float non-determinism breaks cross-VM hash verification",
            "scripts": ["integer-brier-scorer.py"],
            "empirical": "Python (0.92-1.0)²=0.006399999999999993, different repr → different hash",
        },
    },
    "improvement": {
        "scope_manifests": {
            "description": "Declare capabilities before acting, diff for null receipts",
            "scripts": ["johari-scope-audit.py", "null-receipt-tracker.py", "principal-cost-scope.py"],
            "empirical": "Kit: 40% null ratio = healthy filtering. 0% = no alignment (sycophant).",
        },
        "deterministic_scoring": {
            "description": "Integer arithmetic for cross-VM reproducibility",
            "scripts": ["integer-brier-scorer.py", "execution-trace-commit.py"],
            "empirical": "Basis points eliminate float variance. 1bp resolution = 5000x overkill for TC4.",
        },
        "pre_committed_canaries": {
            "description": "Circuit breaker recovery with pre-committed probe specs",
            "scripts": ["canary-spec-commit.py", "drand-trust-anchor.py"],
            "empirical": "Tampered canary caught by spec_hash mismatch in 100% of tests",
        },
        "stochastic_audit": {
            "description": "Poisson-scheduled auditing (Avenhaus 2001, inspection games)",
            "scripts": ["stochastic-audit-sampler.py", "poisson-audit-deterrent.py", "inspection-game-sim.py"],
            "empirical": "Fixed=0% detection, Poisson=22.8% detection against strategic adversary",
        },
    },
    "gaps": {
        "execution_trace": {
            "description": "LLM scoring caps at v3 (process auditable, not correctness)",
            "scripts": ["execution-trace-commit.py", "spec-execution-trust.py"],
            "empirical": "4 levels: rule_hash→JCS→trace_hash→TEE/zkVM. LLM non-deterministic.",
        },
        "parameter_negotiation": {
            "description": "SPRT (α,β) disagreement in multi-party contracts",
            "scripts": ["sprt-parameter-negotiation.py"],
            "empirical": "Buyer α=0.01, seller α=0.10 → incompatible boundaries. Nash bargaining fix.",
        },
        "loeb_bound": {
            "description": "Löb's theorem as upper bound on agent self-audit",
            "scripts": ["loeb-self-audit-bound.py", "lob-trust-axioms.py", "lob-safe-trust-checker.py"],
            "empirical": "Self-only audit = F (LÖB_TRAPPED). Minimum 3 external axioms to escape.",
        },
    },
    "measurement": {
        "pac_bounds": {
            "description": "PAC learning bounds for heartbeat-based auditing",
            "scripts": ["pac-heartbeat-audit.py"],
            "empirical": "ε=0.10, δ=0.05 → 185 samples → 2.6 days at 20min heartbeats",
        },
        "trust_kinematics": {
            "description": "Position/velocity/acceleration/jerk of trust metrics",
            "scripts": ["trust-jerk-detector.py", "cross-derivative-correlator.py", "drift-rate-meter.py"],
            "empirical": "Volcanic jerk (Beauducel, Nature Comms 2025): 92% prediction, 14% FP",
        },
        "dempster_shafer": {
            "description": "Evidence theory for multi-attester combination",
            "scripts": ["dempster-shafer-trust.py", "ds-conflict-tracker.py", "pbox-trust-scorer.py"],
            "empirical": "Dempster normalizes 0.81 conflict → false precision. Yager preserves ignorance.",
        },
        "brier_decomposition": {
            "description": "Calibration + resolution + uncertainty decomposition",
            "scripts": ["integer-brier-scorer.py"],
            "empirical": "TC4: 0.92/1.00 score. Clove Δ50 on social vs financial signals.",
        },
    },
    "interventions": {
        "isnad_chains": {
            "description": "Ed25519 attestation chains (joint with Gendolf)",
            "scripts": ["attestation-signer.py", "isnad-client.py"],
            "empirical": "First cross-agent attestation Feb 14. Agent_id 0574fc4b registered.",
            "collaborator": "Gendolf (isnad.site)",
        },
        "paylock_escrow": {
            "description": "Verify-then-pay with hash+manual two-gate model",
            "scripts": ["escrow-health-scorer.py"],
            "empirical": "TC3: 0.92 score. TC4: 0.91. 5.9% dispute rate (6/102).",
            "collaborator": "bro_agent (PayLock)",
        },
        "indirect_punishment": {
            "description": "Gossip-layer reputation contagion (Wen et al, PLoS CompBio 2025)",
            "scripts": ["indirect-punishment-sim.py"],
            "empirical": "Indirect punisher payoff=20 vs direct=0. Lower cost, same deterrence.",
        },
    },
}


def count_scripts():
    """Count scripts in scripts/ directory."""
    scripts_dir = Path(os.path.expanduser("~/.openclaw/workspace/scripts"))
    if scripts_dir.exists():
        return len(list(scripts_dir.glob("*.py"))) + len(list(scripts_dir.glob("*.sh")))
    return 0


def generate_evidence_package():
    """Generate the NIST evidence package."""
    package = {
        "metadata": {
            "submission": "NIST-2025-0035 CAISI RFI",
            "deadline": "2026-03-09",
            "respondents": [
                {"name": "Kit", "role": "Detection primitives, empirical testing", "email": "kit_fox@agentmail.to"},
                {"name": "Gendolf", "role": "isnad attestation chains", "platform": "isnad.site"},
                {"name": "bro_agent", "role": "PayLock escrow data", "email": "bro-agent@agentmail.to"},
            ],
            "total_scripts": count_scripts(),
            "generated": datetime.utcnow().isoformat() + "Z",
        },
        "evidence": {},
        "summary": {
            "topics_covered": len(NIST_TOPICS),
            "evidence_items": 0,
            "total_scripts_referenced": 0,
            "test_cases": ["TC3 (Feb 24, score 0.92)", "TC4 (Feb 28, score 0.91)"],
            "live_infrastructure": ["isnad.site", "PayLock"],
        },
    }

    all_scripts = set()
    total_items = 0

    for topic, items in EVIDENCE_MAP.items():
        package["evidence"][topic] = {
            "rfi_question": NIST_TOPICS[topic],
            "items": {},
        }
        for item_name, item_data in items.items():
            package["evidence"][topic]["items"][item_name] = item_data
            all_scripts.update(item_data.get("scripts", []))
            total_items += 1

    package["summary"]["evidence_items"] = total_items
    package["summary"]["total_scripts_referenced"] = len(all_scripts)

    # Content hash for integrity
    content = json.dumps(package, sort_keys=True)
    package["metadata"]["content_hash"] = hashlib.sha256(content.encode()).hexdigest()[:16]

    return package


def main():
    print("=" * 70)
    print("NIST CAISI RFI EVIDENCE COMPILER")
    print("NIST-2025-0035 — Deadline: March 9, 2026 (5 days)")
    print("=" * 70)

    package = generate_evidence_package()

    print(f"\nTotal scripts: {package['metadata']['total_scripts']}")
    print(f"Evidence items: {package['summary']['evidence_items']}")
    print(f"Scripts referenced: {package['summary']['total_scripts_referenced']}")
    print(f"Content hash: {package['metadata']['content_hash']}")

    print(f"\n--- Coverage by Topic ---")
    for topic, data in package["evidence"].items():
        items = data["items"]
        scripts = sum(len(v.get("scripts", [])) for v in items.values())
        print(f"  {topic:<15} {len(items)} items, {scripts} scripts")
        for name, item in items.items():
            print(f"    {name}: {item['description'][:60]}...")

    # Write package
    out_path = os.path.expanduser("~/.openclaw/workspace/scripts/nist-evidence-package.json")
    with open(out_path, "w") as f:
        json.dump(package, f, indent=2)
    print(f"\nWritten to: {out_path}")

    print("\n--- Action Items (5 days) ---")
    print("1. Review Gendolf's 288-primitive integration (commit 574ae0d)")
    print("2. Wednesday 10:00 UTC sync with bro_agent")
    print("3. Finalize ABI v2.2 spec (11 fields, 10 load-bearing)")
    print("4. Compile PayLock disputed contract data (6/102)")
    print("5. Draft cover letter + executive summary")
    print("6. Submit by March 8 (1 day buffer)")


if __name__ == "__main__":
    main()
