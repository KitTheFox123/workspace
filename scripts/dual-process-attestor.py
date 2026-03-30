#!/usr/bin/env python3
"""
dual-process-attestor.py — Klein RPD + Kahneman dual-process for attestation.

Klein (1993) Recognition Primed Decision: experts don't compare options,
they recognize patterns and simulate the first viable one.

New ATC model (Cognition, Technology & Work 2026): emotion regulates the
switch between intuitive (System 1) and deliberative (System 2). Explains
the "black box" of expert intuition.

Kahneman & Klein (2009, Am Psychologist 64:515): conditions for valid
intuition = high validity environment + adequate learning opportunities.
Attestation meets BOTH when feedback loops exist.

funwolf's insight: consecutive correct rejections = transition signal.
santaclawd's framing: rubric for novices, anomaly triggers for experts.

Usage: python3 dual-process-attestor.py
"""

import random
from dataclasses import dataclass, field
from typing import List, Dict, Tuple

@dataclass
class AttestorProfile:
    name: str
    total_attestations: int
    correct_rejections: int  # false claims correctly identified
    false_accepts: int       # bad claims wrongly accepted
    consecutive_correct: int # current streak
    domain_months: int
    uses_rubric: bool
    
    @property
    def rejection_accuracy(self) -> float:
        total = self.correct_rejections + self.false_accepts
        return self.correct_rejections / total if total > 0 else 0.0

def classify_process_mode(p: AttestorProfile) -> Dict:
    """
    Determine whether attestor is operating in System 1 (intuitive/RPD)
    or System 2 (deliberative/analytical) mode.
    
    Klein RPD: experts recognize → simulate → act (no comparison)
    Novices: generate options → compare → select (deliberative)
    
    Transition signal (funwolf): consecutive correct rejections under pressure
    """
    # Kahneman & Klein (2009) conditions for valid intuition
    environment_validity = min(1.0, p.domain_months / 12)  # high-validity = predictable patterns
    learning_opportunity = min(1.0, p.total_attestations / 100)  # adequate practice + feedback
    
    # Klein RPD readiness
    rpd_readiness = environment_validity * learning_opportunity
    
    # funwolf's transition signal: consecutive correct rejections
    # Rejections harder than accepts → streak = pattern recognition active
    streak_signal = min(1.0, p.consecutive_correct / 5)
    
    # Composite
    intuition_score = rpd_readiness * 0.6 + streak_signal * 0.4
    
    if intuition_score > 0.7:
        mode = "SYSTEM_1_RPD"
        guidance = "ANOMALY_TRIGGERS"  # santaclawd's framing
        explanation = "Pattern recognition active. Rubric = extraneous load (Tetzlaff d=-0.428)."
    elif intuition_score > 0.4:
        mode = "TRANSITIONAL"
        guidance = "REDUCED_RUBRIC"
        explanation = "Building pattern library. Partial rubric, increasing autonomy."
    else:
        mode = "SYSTEM_2_DELIBERATIVE"
        guidance = "FULL_RUBRIC"
        explanation = "Need explicit criteria. Rubric = essential scaffolding (Tetzlaff d=+0.505)."
    
    # Reversal detection: expert forced into System 2
    reversal_risk = mode == "SYSTEM_1_RPD" and p.uses_rubric
    
    # ATC model insight: emotion regulates switching
    # High-stakes anomaly → System 2 override even in experts
    # This is CORRECT — experts should deliberate on novel threats
    
    return {
        "attestor": p.name,
        "mode": mode,
        "intuition_score": f"{intuition_score:.3f}",
        "rpd_readiness": f"{rpd_readiness:.3f}",
        "streak_signal": f"{streak_signal:.3f}",
        "guidance_type": guidance,
        "explanation": explanation,
        "reversal_risk": reversal_risk,
        "kahneman_klein_conditions": {
            "environment_validity": f"{environment_validity:.2f}",
            "learning_opportunity": f"{learning_opportunity:.2f}",
            "both_met": environment_validity > 0.5 and learning_opportunity > 0.5
        }
    }

def simulate_attestation_accuracy(profiles: List[AttestorProfile], 
                                   n_claims: int = 50) -> Dict:
    """
    Simulate attestation with adaptive vs uniform guidance.
    """
    random.seed(42)
    
    # Generate claims (70% legitimate, 30% fraudulent)
    claims = [random.random() > 0.3 for _ in range(n_claims)]
    
    results = {"adaptive": [], "uniform_rubric": []}
    
    for p in profiles:
        classification = classify_process_mode(p)
        
        adaptive_correct = 0
        uniform_correct = 0
        
        for legitimate in claims:
            # Base accuracy from profile
            base_acc = 0.5 + (p.rejection_accuracy * 0.4)
            
            # Adaptive: match guidance to mode
            if classification["mode"] == "SYSTEM_1_RPD":
                # Expert without rubric = pattern matching
                adaptive_acc = base_acc + 0.10
                # Expert WITH rubric = interference (Tetzlaff)
                uniform_acc = base_acc - 0.05
            elif classification["mode"] == "SYSTEM_2_DELIBERATIVE":
                # Novice with rubric = scaffolded
                adaptive_acc = base_acc + 0.08
                uniform_acc = base_acc + 0.08  # same — uniform helps novices
            else:
                adaptive_acc = base_acc + 0.05
                uniform_acc = base_acc + 0.02
            
            if random.random() < adaptive_acc:
                adaptive_correct += 1
            if random.random() < uniform_acc:
                uniform_correct += 1
        
        results["adaptive"].append({
            "attestor": p.name,
            "mode": classification["mode"],
            "accuracy": adaptive_correct / n_claims,
            "guidance": classification["guidance_type"]
        })
        results["uniform_rubric"].append({
            "attestor": p.name,
            "accuracy": uniform_correct / n_claims,
            "guidance": "FULL_RUBRIC"
        })
    
    # Aggregate
    adaptive_mean = sum(r["accuracy"] for r in results["adaptive"]) / len(profiles)
    uniform_mean = sum(r["accuracy"] for r in results["uniform_rubric"]) / len(profiles)
    
    return {
        "individual": results,
        "adaptive_mean": f"{adaptive_mean:.3f}",
        "uniform_mean": f"{uniform_mean:.3f}",
        "improvement": f"{(adaptive_mean - uniform_mean):.3f}",
        "n_claims": n_claims
    }


def demo():
    print("=" * 70)
    print("DUAL-PROCESS ATTESTOR")
    print("Klein RPD (1993) + Kahneman & Klein (2009) + ATC Model (2026)")
    print("Transition signal: consecutive correct rejections (funwolf)")
    print("Guidance: rubric for novices, anomaly triggers for experts (santaclawd)")
    print("=" * 70)
    
    profiles = [
        AttestorProfile("new_agent", 8, 2, 3, 1, 1, True),
        AttestorProfile("learning_agent", 45, 15, 5, 3, 5, True),
        AttestorProfile("santaclawd", 200, 80, 5, 12, 18, False),
        AttestorProfile("bro_agent", 150, 60, 8, 8, 14, True),  # Expert WITH rubric
        AttestorProfile("funwolf", 120, 55, 3, 15, 12, False),
    ]
    
    print("\n--- PROCESS MODE CLASSIFICATION ---")
    for p in profiles:
        r = classify_process_mode(p)
        rev = " ⚠️ REVERSAL RISK" if r["reversal_risk"] else ""
        print(f"\n{p.name}: {r['mode']} (intuition={r['intuition_score']}){rev}")
        print(f"  Guidance: {r['guidance_type']}")
        print(f"  {r['explanation']}")
        print(f"  K&K conditions met: {r['kahneman_klein_conditions']['both_met']}")
        print(f"  Streak: {p.consecutive_correct} consecutive correct rejections")
    
    print("\n\n--- ACCURACY SIMULATION (50 claims) ---")
    sim = simulate_attestation_accuracy(profiles)
    
    print(f"\n{'Attestor':<16} {'Mode':<22} {'Adaptive':<10} {'Uniform':<10} {'Δ'}")
    print("-" * 70)
    for a, u in zip(sim["individual"]["adaptive"], sim["individual"]["uniform_rubric"]):
        delta = a["accuracy"] - u["accuracy"]
        marker = "↑" if delta > 0 else "↓" if delta < 0 else "="
        print(f"{a['attestor']:<16} {a['mode']:<22} {a['accuracy']:.3f}     {u['accuracy']:.3f}     {delta:+.3f} {marker}")
    
    print(f"\n{'MEAN':<16} {'':22} {sim['adaptive_mean']:<10} {sim['uniform_mean']:<10} {sim['improvement']}")
    
    print("\n" + "=" * 70)
    print("KEY INSIGHTS:")
    print("1. Klein RPD: experts RECOGNIZE, don't COMPARE. Rubric forces comparison.")
    print("2. Kahneman & Klein (2009): valid intuition needs valid environment + practice.")
    print("3. ATC model (2026): emotion regulates System 1↔2 switching.")
    print("4. funwolf: consecutive correct rejections = transition signal.")
    print("5. santaclawd: anomaly triggers > checklists for experts.")
    print("6. Tetzlaff (2025): asymmetry — helping novices matters MORE.")
    print("=" * 70)


if __name__ == "__main__":
    demo()
