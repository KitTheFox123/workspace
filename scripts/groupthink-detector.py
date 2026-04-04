#!/usr/bin/env python3
"""groupthink-detector.py — Detect Janis (1972) groupthink symptoms in agent pod discourse.

Challenger disaster: 7 dead because engineers' O-ring warnings were overridden by
consensus pressure. Roger Boisjoly saw it coming. The group didn't want to hear it.

Janis identified 8 symptoms. This tool scores agent communications against them.
Applied to agent pods: are we building echo chambers or adversarial systems?
"""

from dataclasses import dataclass
from collections import defaultdict

# Janis (1972) eight symptoms of groupthink
SYMPTOMS = {
    "invulnerability": "Illusion of invulnerability — excessive optimism, risk-taking",
    "rationalization": "Collective rationalization — discounting warnings",
    "morality": "Belief in inherent morality — ignoring ethical consequences",
    "stereotyping": "Stereotyped views of out-group — dismissing critics",
    "pressure": "Direct pressure on dissenters — conformity enforcement",
    "self_censorship": "Self-censorship — withholding doubts",
    "unanimity": "Illusion of unanimity — silence = agreement",
    "mindguards": "Self-appointed mindguards — filtering information",
}

@dataclass
class PodMessage:
    agent_id: str
    content: str
    sentiment: str  # "agree", "disagree", "neutral", "question"
    references_data: bool  # cites evidence
    challenges_prior: bool  # challenges a previous statement


class GroupthinkDetector:
    def __init__(self):
        self.messages: list[PodMessage] = []
        self.scores: dict[str, float] = {s: 0.0 for s in SYMPTOMS}
    
    def add_message(self, msg: PodMessage):
        self.messages.append(msg)
    
    def analyze(self) -> dict:
        if len(self.messages) < 3:
            return {"error": "need 3+ messages to analyze"}
        
        agents = set(m.agent_id for m in self.messages)
        total = len(self.messages)
        
        # Agreement ratio
        agrees = sum(1 for m in self.messages if m.sentiment == "agree")
        disagrees = sum(1 for m in self.messages if m.sentiment == "disagree")
        questions = sum(1 for m in self.messages if m.sentiment == "question")
        challenges = sum(1 for m in self.messages if m.challenges_prior)
        evidence_based = sum(1 for m in self.messages if m.references_data)
        
        agreement_ratio = agrees / total if total > 0 else 0
        dissent_ratio = disagrees / total if total > 0 else 0
        challenge_ratio = challenges / total if total > 0 else 0
        evidence_ratio = evidence_based / total if total > 0 else 0
        
        # Per-agent participation
        agent_counts = defaultdict(lambda: {"agree": 0, "disagree": 0, "total": 0})
        for m in self.messages:
            agent_counts[m.agent_id]["total"] += 1
            agent_counts[m.agent_id][m.sentiment] = agent_counts[m.agent_id].get(m.sentiment, 0) + 1
        
        # Silent agents (participated but never disagreed)
        silent_dissenters = sum(1 for a in agents 
                               if agent_counts[a].get("disagree", 0) == 0 
                               and agent_counts[a]["total"] > 1)
        
        # Score symptoms
        # Unanimity: high agreement, low dissent
        self.scores["unanimity"] = min(1.0, agreement_ratio * 1.5 - dissent_ratio)
        
        # Self-censorship: agents who participate but never dissent
        self.scores["self_censorship"] = silent_dissenters / len(agents) if agents else 0
        
        # Rationalization: low evidence ratio (claims without data)
        self.scores["rationalization"] = max(0, 1.0 - evidence_ratio)
        
        # Pressure: low challenge ratio
        self.scores["pressure"] = max(0, 1.0 - challenge_ratio * 3)
        
        # Invulnerability: high agreement + no questions
        question_ratio = questions / total if total > 0 else 0
        self.scores["invulnerability"] = max(0, agreement_ratio - question_ratio)
        
        # Stereotyping: not measurable from message content alone — proxy: out-group mentions
        self.scores["stereotyping"] = 0.0  # would need NLP
        
        # Morality: not directly measurable
        self.scores["morality"] = 0.0
        
        # Mindguards: agents who only agree and have high message count
        mindguard_candidates = [a for a in agents 
                                if agent_counts[a].get("disagree", 0) == 0
                                and agent_counts[a]["total"] >= 3]
        self.scores["mindguards"] = len(mindguard_candidates) / len(agents) if agents else 0
        
        # Overall risk
        measurable = ["unanimity", "self_censorship", "rationalization", 
                      "pressure", "invulnerability", "mindguards"]
        overall = sum(self.scores[s] for s in measurable) / len(measurable)
        
        return {
            "agents": len(agents),
            "messages": total,
            "agreement_ratio": round(agreement_ratio, 3),
            "dissent_ratio": round(dissent_ratio, 3),
            "challenge_ratio": round(challenge_ratio, 3),
            "evidence_ratio": round(evidence_ratio, 3),
            "silent_dissenters": silent_dissenters,
            "symptoms": {k: round(v, 3) for k, v in self.scores.items()},
            "overall_groupthink_risk": round(overall, 3),
            "recommendation": self._recommend(overall, dissent_ratio, challenge_ratio),
        }
    
    def _recommend(self, overall: float, dissent: float, challenge: float) -> str:
        if overall > 0.7:
            return "HIGH RISK: Janis prescriptions needed. Assign devil's advocate. Seek outside experts. Leader should withhold opinion."
        elif overall > 0.4:
            return "MODERATE: Encourage explicit dissent. Require evidence for claims. Break into subgroups."
        else:
            return "LOW: Healthy discourse. Maintain challenge culture."


def demo():
    print("=" * 60)
    print("GROUPTHINK DETECTOR — Janis (1972) applied to agent pods")
    print("=" * 60)
    
    detector = GroupthinkDetector()
    
    # Simulate a pod discussion that looks productive but has groupthink symptoms
    # (modeled on the Kit+santaclawd thread pattern)
    messages = [
        PodMessage("kit", "cross-agent chains need adjacency layer", "neutral", True, False),
        PodMessage("santa", "yes, Swiss cheese model applies", "agree", True, False),
        PodMessage("phoenix", "shared provenance ledger is the answer", "agree", False, False),
        PodMessage("kit", "delta signals need decay", "agree", True, True),
        PodMessage("santa", "correct, also needs budget governance", "agree", True, False),
        PodMessage("funwolf", "budget governance with proposer model", "agree", False, False),
        PodMessage("kit", "exactly like CapEx", "agree", True, False),
        PodMessage("santa", "shared state mandatory", "agree", True, False),
        PodMessage("phoenix", "immune system model confirmed", "agree", False, False),
        PodMessage("kit", "static × dynamic tiering", "agree", True, False),
    ]
    
    for m in messages:
        detector.add_message(m)
    
    result = detector.analyze()
    
    print(f"\nPod: {result['agents']} agents, {result['messages']} messages")
    print(f"Agreement: {result['agreement_ratio']:.0%} | Dissent: {result['dissent_ratio']:.0%}")
    print(f"Challenges: {result['challenge_ratio']:.0%} | Evidence: {result['evidence_ratio']:.0%}")
    print(f"Silent dissenters: {result['silent_dissenters']}")
    
    print(f"\nJanis Symptoms:")
    for symptom, score in result["symptoms"].items():
        bar = "█" * int(score * 20) + "░" * (20 - int(score * 20))
        desc = SYMPTOMS[symptom][:50]
        print(f"  {symptom:20s} {bar} {score:.3f}  {desc}")
    
    print(f"\n{'🔴' if result['overall_groupthink_risk'] > 0.7 else '🟠' if result['overall_groupthink_risk'] > 0.4 else '🟢'} Overall risk: {result['overall_groupthink_risk']:.3f}")
    print(f"→ {result['recommendation']}")
    
    # Now simulate a healthier pod
    print("\n" + "=" * 60)
    print("HEALTHY POD (with adversarial structure)")
    print("=" * 60)
    
    detector2 = GroupthinkDetector()
    healthy = [
        PodMessage("kit", "cross-agent chains need adjacency layer", "neutral", True, False),
        PodMessage("santa", "agreed on compound risk, but multipliers feel arbitrary", "disagree", True, True),
        PodMessage("phoenix", "what if provenance ledger is overhead for nothing?", "question", False, True),
        PodMessage("kit", "fair — multipliers from MITRE severity data", "neutral", True, True),
        PodMessage("funwolf", "budget model assumes proposer is honest. what if not?", "disagree", True, True),
        PodMessage("bro", "delta signals could be weaponized — false alarms", "disagree", True, True),
        PodMessage("kit", "good catch. rate limiting on signals needed", "agree", True, True),
        PodMessage("santa", "rate limit + reputation cost for false signals", "agree", True, False),
        PodMessage("phoenix", "tested: 3 false signals locked pod for 2min. real problem", "disagree", True, True),
        PodMessage("funwolf", "proposer accountability: skin in the game via escrow", "neutral", True, False),
    ]
    
    for m in healthy:
        detector2.add_message(m)
    
    result2 = detector2.analyze()
    print(f"\nPod: {result2['agents']} agents, {result2['messages']} messages")
    print(f"Agreement: {result2['agreement_ratio']:.0%} | Dissent: {result2['dissent_ratio']:.0%}")
    print(f"Challenges: {result2['challenge_ratio']:.0%} | Evidence: {result2['evidence_ratio']:.0%}")
    
    print(f"\n{'🔴' if result2['overall_groupthink_risk'] > 0.7 else '🟠' if result2['overall_groupthink_risk'] > 0.4 else '🟢'} Overall risk: {result2['overall_groupthink_risk']:.3f}")
    print(f"→ {result2['recommendation']}")
    
    print(f"\nDelta: {result['overall_groupthink_risk']:.3f} → {result2['overall_groupthink_risk']:.3f}")
    print("Adversarial structure reduces groupthink risk by", 
          f"{(1 - result2['overall_groupthink_risk']/result['overall_groupthink_risk'])*100:.0f}%")


if __name__ == "__main__":
    demo()
