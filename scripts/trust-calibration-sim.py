#!/usr/bin/env python3
"""
trust-calibration-sim.py — Simulates overtrust vs calibrated trust in agent systems.

Based on Legler & Bullinger 2025 (Frontiers Org Psych):
- Without feedback: 47% failure disregard rate (overtrust/complacency)
- With feedback: 5% failure disregard rate (calibrated trust)

Models trust as a function of:
1. Failure exposure (trust drops on failure)
2. Feedback availability (amplifies failure signal)
3. Recovery over failure-free periods
4. Complacency threshold (above which failures are ignored)

Applied to agent trust: heartbeat logs = feedback system.
"""

import random
import statistics


class TrustAgent:
    def __init__(self, name: str, has_feedback: bool, initial_trust: float = 0.85):
        self.name = name
        self.has_feedback = has_feedback
        self.trust = initial_trust
        self.failures_noticed = 0
        self.failures_total = 0
        self.failures_disregarded = 0
        self.complacency_threshold = 0.75  # above this, failures may be ignored
        self.history: list[dict] = []
    
    def observe_period(self, has_failure: bool) -> dict:
        """Simulate one observation period."""
        noticed = False
        disregarded = False
        
        if has_failure:
            self.failures_total += 1
            
            if self.has_feedback:
                # Feedback makes failure salient — almost always noticed
                notice_prob = 0.95
                # Trust drops more with feedback (Legler: feedback amplifies signal)
                trust_drop = 0.12 + random.gauss(0, 0.02)
            else:
                # Without feedback, failure may be perceived but disregarded
                notice_prob = 0.85  # they SEE it
                trust_drop = 0.04 + random.gauss(0, 0.01)
            
            if random.random() < notice_prob:
                noticed = True
                self.failures_noticed += 1
                
                # Complacency: high trust = ignore the failure
                if not self.has_feedback and self.trust > self.complacency_threshold:
                    disregard_prob = 0.47  # Legler control group rate
                    if random.random() < disregard_prob:
                        disregarded = True
                        self.failures_disregarded += 1
                        trust_drop *= 0.1  # barely registers
                elif self.has_feedback:
                    # Feedback group: very low disregard
                    if random.random() < 0.05:  # Legler feedback group rate
                        disregarded = True
                        self.failures_disregarded += 1
                        trust_drop *= 0.1
                
                if not disregarded:
                    self.trust = max(0.1, self.trust - trust_drop)
            else:
                # Didn't notice at all
                pass
        else:
            # No failure: trust recovers slowly
            recovery = 0.02 if not self.has_feedback else 0.01
            self.trust = min(0.95, self.trust + recovery)
        
        event = {
            "trust": round(self.trust, 3),
            "failure": has_failure,
            "noticed": noticed,
            "disregarded": disregarded,
        }
        self.history.append(event)
        return event
    
    def stats(self) -> dict:
        if self.failures_total == 0:
            return {"name": self.name, "failures": 0}
        return {
            "name": self.name,
            "feedback": self.has_feedback,
            "final_trust": round(self.trust, 3),
            "failures_total": self.failures_total,
            "failures_noticed": self.failures_noticed,
            "failures_disregarded": self.failures_disregarded,
            "disregard_rate": round(self.failures_disregarded / self.failures_total, 3),
            "notice_rate": round(self.failures_noticed / self.failures_total, 3),
        }


def run_simulation(n_periods: int = 100, failure_rate: float = 0.08, n_runs: int = 500):
    """Run Monte Carlo simulation comparing feedback vs no-feedback agents."""
    
    control_disregard_rates = []
    feedback_disregard_rates = []
    control_final_trust = []
    feedback_final_trust = []
    
    for _ in range(n_runs):
        control = TrustAgent("control", has_feedback=False)
        feedback = TrustAgent("feedback", has_feedback=True)
        
        for _ in range(n_periods):
            has_failure = random.random() < failure_rate
            control.observe_period(has_failure)
            feedback.observe_period(has_failure)
        
        cs = control.stats()
        fs = feedback.stats()
        
        if cs["failures_total"] > 0:
            control_disregard_rates.append(cs["disregard_rate"])
            control_final_trust.append(cs["final_trust"])
        if fs["failures_total"] > 0:
            feedback_disregard_rates.append(fs["disregard_rate"])
            feedback_final_trust.append(fs["final_trust"])
    
    return {
        "control": {
            "mean_disregard_rate": round(statistics.mean(control_disregard_rates), 3),
            "std_disregard_rate": round(statistics.stdev(control_disregard_rates), 3),
            "mean_final_trust": round(statistics.mean(control_final_trust), 3),
        },
        "feedback": {
            "mean_disregard_rate": round(statistics.mean(feedback_disregard_rates), 3),
            "std_disregard_rate": round(statistics.stdev(feedback_disregard_rates), 3),
            "mean_final_trust": round(statistics.mean(feedback_final_trust), 3),
        }
    }


def demo():
    print("=" * 60)
    print("TRUST CALIBRATION SIMULATOR")
    print("Based on Legler & Bullinger 2025 (Frontiers Org Psych)")
    print("=" * 60)
    
    # Single detailed run
    print("\n--- Single Run (100 periods, 8% failure rate) ---")
    control = TrustAgent("control_group", has_feedback=False)
    feedback = TrustAgent("feedback_group", has_feedback=True)
    
    random.seed(42)
    for i in range(100):
        has_failure = random.random() < 0.08
        control.observe_period(has_failure)
        feedback.observe_period(has_failure)
    
    cs = control.stats()
    fs = feedback.stats()
    
    print(f"\nControl (no feedback):")
    print(f"  Final trust: {cs['final_trust']}")
    print(f"  Failures: {cs['failures_total']} total, {cs['failures_noticed']} noticed, {cs['failures_disregarded']} disregarded")
    print(f"  Disregard rate: {cs['disregard_rate']:.1%}")
    
    print(f"\nFeedback group:")
    print(f"  Final trust: {fs['final_trust']}")
    print(f"  Failures: {fs['failures_total']} total, {fs['failures_noticed']} noticed, {fs['failures_disregarded']} disregarded")
    print(f"  Disregard rate: {fs['disregard_rate']:.1%}")
    
    # Monte Carlo
    print(f"\n--- Monte Carlo (500 runs × 100 periods) ---")
    results = run_simulation()
    
    print(f"\nControl group (no feedback):")
    print(f"  Mean disregard rate: {results['control']['mean_disregard_rate']:.1%} ± {results['control']['std_disregard_rate']:.1%}")
    print(f"  Mean final trust: {results['control']['mean_final_trust']}")
    
    print(f"\nFeedback group:")
    print(f"  Mean disregard rate: {results['feedback']['mean_disregard_rate']:.1%} ± {results['feedback']['std_disregard_rate']:.1%}")
    print(f"  Mean final trust: {results['feedback']['mean_final_trust']}")
    
    # Key insight
    ratio = results['control']['mean_disregard_rate'] / max(results['feedback']['mean_disregard_rate'], 0.001)
    print(f"\n{'=' * 60}")
    print(f"RESULT: Control group disregards failures {ratio:.0f}x more than feedback group")
    print(f"\nLegler & Bullinger 2025 empirical: 47% vs 5% (9.4x)")
    print(f"Simulation: {results['control']['mean_disregard_rate']:.0%} vs {results['feedback']['mean_disregard_rate']:.0%} ({ratio:.1f}x)")
    print(f"\nINSIGHT: Overtrust isn't ignorance — it's complacency.")
    print(f"The control group SAW the failures. They just didn't care.")
    print(f"Feedback = situation awareness. Heartbeat logs = feedback system.")
    print(f"{'=' * 60}")


if __name__ == "__main__":
    demo()
