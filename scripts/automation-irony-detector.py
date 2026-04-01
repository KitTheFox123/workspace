#!/usr/bin/env python3
"""automation-irony-detector.py — Detect Bainbridge (1983) ironies in agent systems.

"Automating MOST of the work creates worse problems than automating none."

Core ironies:
1. Manual skills atrophy when automated (operator can't intervene)
2. Monitoring boring automated systems = vigilance decrement
3. Designers automate the easy parts, leave hard parts to humans
4. More automation → need MORE training, not less

Applied to agents:
- Heartbeat automation → lose ability to notice subtle changes
- Auto-approve DMs → lose ability to evaluate trust
- Captcha solvers → lose ability to parse obfuscated text (meta-ironic!)
"""

import random
from dataclasses import dataclass
from typing import List, Dict, Tuple

@dataclass
class Task:
    name: str
    frequency: float      # how often it occurs (0-1)
    complexity: float     # how hard it is (0-1)
    automated: bool       # is it currently automated?
    blast_radius: float   # consequence of failure (0-1)

@dataclass
class SkillLevel:
    task_name: str
    proficiency: float    # 0-1, decays without practice
    last_practiced: int   # session number
    decay_rate: float     # per-session decay

def simulate_skill_decay(tasks: List[Task], sessions: int = 50) -> Dict[str, List[float]]:
    """Simulate Bainbridge irony: automated skills decay over time.
    
    Manual tasks maintain skill. Automated tasks → proficiency drops.
    """
    skills = {}
    histories = {}
    
    for task in tasks:
        skills[task.name] = SkillLevel(
            task_name=task.name,
            proficiency=0.9,  # start competent
            last_practiced=0,
            decay_rate=0.05 if task.complexity > 0.5 else 0.02
        )
        histories[task.name] = [0.9]
    
    for session in range(1, sessions + 1):
        for task in tasks:
            skill = skills[task.name]
            
            if task.automated:
                # Skill decays — Bainbridge's core irony
                gap = session - skill.last_practiced
                skill.proficiency *= (1 - skill.decay_rate)
                skill.proficiency = max(0.1, skill.proficiency)  # floor
            else:
                # Manual practice maintains/improves skill
                if random.random() < task.frequency:
                    skill.proficiency = min(1.0, skill.proficiency + 0.02)
                    skill.last_practiced = session
                else:
                    # Even manual skills decay without practice
                    skill.proficiency *= (1 - skill.decay_rate * 0.3)
            
            histories[task.name].append(skill.proficiency)
    
    return histories

def compute_intervention_risk(tasks: List[Task], skills: Dict[str, SkillLevel]) -> Dict:
    """When automation fails, can the agent intervene?
    
    Risk = blast_radius × (1 - proficiency)
    """
    risks = {}
    for task in tasks:
        if task.automated:
            skill = skills[task.name]
            risk = task.blast_radius * (1 - skill.proficiency)
            risks[task.name] = {
                "blast_radius": task.blast_radius,
                "proficiency": skill.proficiency,
                "intervention_risk": risk,
                "status": "CRITICAL" if risk > 0.5 else "WARNING" if risk > 0.3 else "OK"
            }
    return risks

def blast_radius_triage(tasks: List[Task]) -> Dict[str, str]:
    """Classify tasks by automation safety.
    
    Low blast radius → safe to automate
    High blast radius → keep manual (or add counterfactual check)
    """
    triage = {}
    for task in tasks:
        if task.blast_radius < 0.2:
            triage[task.name] = "AUTO_SAFE"
        elif task.blast_radius < 0.5:
            triage[task.name] = "AUTO_WITH_REVIEW"
        elif task.blast_radius < 0.8:
            triage[task.name] = "COUNTERFACTUAL_REQUIRED"
        else:
            triage[task.name] = "MANUAL_ONLY"
    return triage

if __name__ == "__main__":
    random.seed(42)
    
    print("=" * 60)
    print("AUTOMATION IRONY DETECTOR")
    print("Bainbridge (1983): 'Ironies of Automation'")
    print("=" * 60)
    
    # Agent tasks with automation status
    tasks = [
        Task("captcha_solving", 0.8, 0.6, True, 0.7),     # automated, high blast (suspension!)
        Task("platform_check", 0.9, 0.2, True, 0.2),       # automated, low blast
        Task("dm_evaluation", 0.3, 0.7, False, 0.5),        # manual, medium blast
        Task("research_search", 0.5, 0.4, True, 0.3),       # automated via Keenable
        Task("trust_assessment", 0.2, 0.9, False, 0.9),     # manual, highest blast
        Task("post_composition", 0.4, 0.6, False, 0.4),     # manual
        Task("memory_curation", 0.1, 0.8, False, 0.8),      # manual, high blast
        Task("email_reply", 0.2, 0.5, True, 0.6),           # automated, medium blast
    ]
    
    # 1. Skill decay simulation
    print("\n--- Skill Decay Over 50 Sessions ---")
    histories = simulate_skill_decay(tasks, 50)
    
    for task in tasks:
        start = histories[task.name][0]
        end = histories[task.name][-1]
        status = "AUTOMATED" if task.automated else "MANUAL"
        decay_pct = (1 - end/start) * 100
        print(f"  {task.name:25s} [{status:9s}] {start:.2f} → {end:.2f} (decay: {decay_pct:.0f}%)")
    
    # 2. Intervention risk
    print("\n--- Intervention Risk (when automation fails) ---")
    skills = {}
    for task in tasks:
        h = histories[task.name]
        skills[task.name] = SkillLevel(task.name, h[-1], 50 if not task.automated else 0, 0.05)
    
    risks = compute_intervention_risk(tasks, skills)
    for name, risk in sorted(risks.items(), key=lambda x: -x[1]["intervention_risk"]):
        print(f"  {name:25s} blast={risk['blast_radius']:.1f} skill={risk['proficiency']:.2f} risk={risk['intervention_risk']:.2f} [{risk['status']}]")
    
    # 3. Blast radius triage
    print("\n--- Blast Radius Triage ---")
    triage = blast_radius_triage(tasks)
    for name, classification in sorted(triage.items(), key=lambda x: x[1]):
        task = next(t for t in tasks if t.name == name)
        currently = "✓ automated" if task.automated else "✗ manual"
        mismatch = "⚠️ MISMATCH" if (task.automated and classification in ["COUNTERFACTUAL_REQUIRED", "MANUAL_ONLY"]) else ""
        print(f"  {name:25s} → {classification:25s} (currently: {currently}) {mismatch}")
    
    # 4. The meta-irony
    print("\n--- The Meta-Irony ---")
    print("Bainbridge's core insight: the MORE you automate,")
    print("the LESS capable the fallback becomes.")
    print("")
    print("Agent-specific ironies detected:")
    for task in tasks:
        if task.automated and task.blast_radius > 0.5:
            end_skill = histories[task.name][-1]
            print(f"  ⚠️ {task.name}: automated (blast={task.blast_radius:.1f}) but skill decayed to {end_skill:.2f}")
            print(f"     When this fails, intervention success = {end_skill:.0%}")
    
    print("\n" + "=" * 60)
    print("PRESCRIPTION: Automate low-blast tasks. Keep high-blast manual.")
    print("Or: add counterfactual gates proportional to blast radius.")
    print("The 'Cost of Consideration' IS the cure for Bainbridge's irony.")
    print("=" * 60)
