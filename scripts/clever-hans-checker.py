#!/usr/bin/env python3
"""
clever-hans-checker.py - Evaluate ML claims for Clever Hans risk factors.

Checks whether an ML paper/claim addresses key Pfungst-test criteria:
1. Out-of-distribution evaluation (not just train/test split)
2. Ablation studies (removing suspected spurious features)
3. Cross-domain validation (different data sources)
4. Explainability analysis (saliency maps, SHAP, etc.)
5. Confound controls (metadata, artifacts, demographics)

Usage:
  python3 scripts/clever-hans-checker.py --text "paste abstract or claims"
  python3 scripts/clever-hans-checker.py --url "https://arxiv.org/abs/..."
  python3 scripts/clever-hans-checker.py --interactive
"""

import argparse
import re
import sys
import json

CRITERIA = {
    "ood_evaluation": {
        "name": "Out-of-Distribution Testing",
        "description": "Tests on data from different distribution than training",
        "keywords": [
            "out-of-distribution", "ood", "domain shift", "external validation",
            "cross-institutional", "held-out institution", "distribution shift",
            "external dataset", "external test", "prospective validation"
        ],
        "weight": 0.30,
        "risk_if_missing": "HIGH — model may exploit distribution-specific artifacts"
    },
    "ablation": {
        "name": "Ablation / Feature Removal",
        "description": "Systematic removal of suspected confounds",
        "keywords": [
            "ablation", "feature removal", "occluding", "masking",
            "counterfactual", "without feature", "removing", "knocked out"
        ],
        "weight": 0.20,
        "risk_if_missing": "MEDIUM — unclear which features drive predictions"
    },
    "cross_domain": {
        "name": "Cross-Domain Validation",
        "description": "Testing across multiple data sources/institutions",
        "keywords": [
            "cross-domain", "multi-site", "multi-center", "multi-institutional",
            "external cohort", "generalization", "transferability", "portable"
        ],
        "weight": 0.20,
        "risk_if_missing": "HIGH — results may not generalize beyond source data"
    },
    "explainability": {
        "name": "Explainability Analysis",
        "description": "Visual/quantitative explanation of model decisions",
        "keywords": [
            "grad-cam", "shap", "lime", "saliency", "attention map",
            "relevance propagation", "lrp", "feature importance",
            "interpretab", "explainab", "heatmap"
        ],
        "weight": 0.15,
        "risk_if_missing": "MEDIUM — no visibility into what model actually learned"
    },
    "confound_control": {
        "name": "Confound Controls",
        "description": "Explicit handling of known confounding variables",
        "keywords": [
            "confound", "covariate", "stratif", "demographic",
            "batch effect", "scanner", "artifact", "metadata",
            "spurious correlation", "shortcut"
        ],
        "weight": 0.15,
        "risk_if_missing": "HIGH — known confounds may drive apparent performance"
    }
}

def check_text(text: str) -> dict:
    """Analyze text for Clever Hans risk factors."""
    text_lower = text.lower()
    results = {}
    total_score = 0.0
    
    for key, criterion in CRITERIA.items():
        found = []
        for kw in criterion["keywords"]:
            pattern = re.compile(re.escape(kw), re.IGNORECASE)
            matches = pattern.findall(text)
            if matches:
                found.append(kw)
        
        present = len(found) > 0
        score = criterion["weight"] if present else 0.0
        total_score += score
        
        results[key] = {
            "name": criterion["name"],
            "present": present,
            "evidence": found[:3],
            "score": score,
            "max_score": criterion["weight"],
            "risk_if_missing": criterion["risk_if_missing"]
        }
    
    # Risk assessment
    if total_score >= 0.80:
        risk_level = "LOW"
        assessment = "Claim addresses most Pfungst-test criteria"
    elif total_score >= 0.50:
        risk_level = "MEDIUM" 
        assessment = "Some evaluation gaps — check missing criteria"
    elif total_score >= 0.25:
        risk_level = "HIGH"
        assessment = "Significant evaluation gaps — Clever Hans risk elevated"
    else:
        risk_level = "CRITICAL"
        assessment = "Minimal robustness evaluation — high Clever Hans risk"
    
    return {
        "total_score": round(total_score, 2),
        "max_score": 1.0,
        "risk_level": risk_level,
        "assessment": assessment,
        "criteria": results
    }

def print_report(result: dict):
    """Pretty-print the Clever Hans risk report."""
    risk_colors = {"LOW": "🟢", "MEDIUM": "🟡", "HIGH": "🟠", "CRITICAL": "🔴"}
    
    print(f"\n{'='*60}")
    print(f"  CLEVER HANS RISK ASSESSMENT")
    print(f"{'='*60}")
    print(f"  Score: {result['total_score']}/{result['max_score']}")
    print(f"  Risk:  {risk_colors.get(result['risk_level'], '?')} {result['risk_level']}")
    print(f"  {result['assessment']}")
    print(f"{'='*60}\n")
    
    for key, c in result["criteria"].items():
        status = "✅" if c["present"] else "❌"
        print(f"  {status} {c['name']} ({c['max_score']:.0%} weight)")
        if c["present"]:
            print(f"     Evidence: {', '.join(c['evidence'])}")
        else:
            print(f"     ⚠️  {c['risk_if_missing']}")
        print()
    
    print(f"{'='*60}")
    print(f"  Based on Pfungst (1907), Lapuschkin et al. (2019),")
    print(f"  and Pathak et al. (2026) Clever Hans framework")
    print(f"{'='*60}\n")

def main():
    parser = argparse.ArgumentParser(description="Clever Hans risk checker for ML claims")
    parser.add_argument("--text", help="Text to analyze")
    parser.add_argument("--file", help="File to analyze")
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    parser.add_argument("--interactive", action="store_true", help="Interactive mode")
    
    args = parser.parse_args()
    
    if args.interactive:
        print("Paste ML claim/abstract (end with empty line):")
        lines = []
        while True:
            line = input()
            if not line:
                break
            lines.append(line)
        text = "\n".join(lines)
    elif args.file:
        with open(args.file) as f:
            text = f.read()
    elif args.text:
        text = args.text
    else:
        # Demo mode
        text = """We trained a deep neural network on chest X-rays to detect COVID-19 
        with 98.7% accuracy on our test set. The model uses a ResNet-50 architecture 
        fine-tuned on 5,000 images from our hospital. We applied Grad-CAM visualization 
        to verify the model focuses on lung regions."""
        print("Demo mode (no input provided):")
        print(f"  \"{text[:80]}...\"")
    
    result = check_text(text)
    
    if args.json:
        print(json.dumps(result, indent=2))
    else:
        print_report(result)

if __name__ == "__main__":
    main()
