#!/usr/bin/env python3
"""
cognitive-load-estimator.py — Estimate cognitive load of agent prompts/contexts.

Based on Cognitive Load Theory (Sweller 1988, Gkintoni et al 2025):
- Intrinsic load: complexity of the material itself
- Extraneous load: unnecessary complexity from presentation
- Germane load: effort spent building schemas (useful learning)

Expertise reversal effect (Kalyuga 2007): scaffolding that helps novices HARMS experts.
Verbose prompts = extraneous load for capable agents.

Measures: element interactivity, redundancy, split-attention, coherence.
"""

import re
from dataclasses import dataclass


@dataclass
class LoadEstimate:
    intrinsic: float    # 0-1: material complexity
    extraneous: float   # 0-1: unnecessary overhead
    germane: float      # 0-1: useful schema-building
    total: float        # sum (>1.0 = overload risk)
    grade: str
    recommendations: list


def count_unique_concepts(text: str) -> int:
    """Estimate concept density via unique technical terms."""
    words = re.findall(r'\b[a-zA-Z_]{4,}\b', text)
    return len(set(w.lower() for w in words))


def estimate_element_interactivity(text: str) -> float:
    """Higher interactivity = more elements that must be processed simultaneously."""
    conditionals = len(re.findall(r'\b(if|when|unless|except|however|but)\b', text, re.I))
    references = len(re.findall(r'\b(this|that|these|those|above|below|previous|following)\b', text, re.I))
    nested = text.count('{') + text.count('[') + text.count('(')
    
    score = min(1.0, (conditionals * 0.05 + references * 0.03 + nested * 0.02))
    return score


def estimate_redundancy(text: str) -> float:
    """Detect repeated information (extraneous load source)."""
    sentences = [s.strip() for s in re.split(r'[.!?\n]', text) if len(s.strip()) > 20]
    if len(sentences) < 2:
        return 0.0
    
    # Simple word-overlap redundancy
    overlaps = 0
    for i, s1 in enumerate(sentences):
        w1 = set(s1.lower().split())
        for s2 in sentences[i+1:]:
            w2 = set(s2.lower().split())
            if w1 and w2:
                overlap = len(w1 & w2) / min(len(w1), len(w2))
                if overlap > 0.6:
                    overlaps += 1
    
    return min(1.0, overlaps * 0.1)


def estimate_split_attention(text: str) -> float:
    """Detect split-attention indicators (references to external sources needed)."""
    external_refs = len(re.findall(r'(see above|refer to|as mentioned|cf\.|see section|see figure)', text, re.I))
    urls = len(re.findall(r'https?://', text))
    
    return min(1.0, (external_refs * 0.1 + urls * 0.05))


def estimate_cognitive_load(text: str, agent_expertise: float = 0.5) -> LoadEstimate:
    """
    Estimate cognitive load of a prompt/context.
    
    agent_expertise: 0.0 (novice) to 1.0 (expert)
    Higher expertise = expertise reversal effect applies
    """
    concepts = count_unique_concepts(text)
    length = len(text)
    
    # Intrinsic load: material complexity
    concept_density = min(1.0, concepts / max(1, length / 100))
    interactivity = estimate_element_interactivity(text)
    intrinsic = (concept_density * 0.6 + interactivity * 0.4)
    
    # Extraneous load: presentation overhead
    redundancy = estimate_redundancy(text)
    split_attention = estimate_split_attention(text)
    verbosity = min(1.0, max(0, length - 500) / 5000)  # penalty for very long texts
    
    # Expertise reversal: scaffolding becomes extraneous for experts
    expertise_reversal = agent_expertise * verbosity * 0.5
    
    extraneous = min(1.0, redundancy * 0.3 + split_attention * 0.3 + verbosity * 0.2 + expertise_reversal * 0.2)
    
    # Germane load: useful schema-building
    # Novel concepts for the agent's level
    novelty = intrinsic * (1 - agent_expertise * 0.5)
    germane = min(1.0, novelty * 0.7)
    
    total = intrinsic + extraneous + germane
    
    # Grade
    if total < 0.5:
        grade = "A"  # Low load, efficient
    elif total < 0.8:
        grade = "B"  # Moderate, manageable
    elif total < 1.2:
        grade = "C"  # High, attention needed
    else:
        grade = "F"  # Overload risk
    
    # Recommendations
    recs = []
    if redundancy > 0.3:
        recs.append("REDUCE REDUNDANCY: repeated information detected")
    if split_attention > 0.3:
        recs.append("INTEGRATE SOURCES: split-attention effect — bring referenced info inline")
    if expertise_reversal > 0.1:
        recs.append(f"EXPERTISE REVERSAL: agent expertise={agent_expertise:.1f}, verbose scaffolding may hinder")
    if verbosity > 0.5:
        recs.append(f"TRIM LENGTH: {length} chars, consider pruning extraneous detail")
    if not recs:
        recs.append("Load is manageable")
    
    return LoadEstimate(
        intrinsic=round(intrinsic, 3),
        extraneous=round(extraneous, 3),
        germane=round(germane, 3),
        total=round(total, 3),
        grade=grade,
        recommendations=recs
    )


def demo():
    print("=" * 60)
    print("COGNITIVE LOAD ESTIMATOR — Sweller/Kalyuga/Gkintoni")
    print("=" * 60)
    
    examples = [
        ("Minimal prompt", "Check inbox for new messages.", 0.8),
        ("Verbose scaffolding", 
         "First, you need to check your inbox. To do this, use the API endpoint. "
         "The API endpoint is https://api.example.com/inbox. You need to use your API key. "
         "Your API key can be found in the credentials file. The credentials file is at "
         "~/.config/credentials.json. Once you have the API key, make a GET request. "
         "The GET request should include the Authorization header. The Authorization header "
         "should contain 'Bearer' followed by your API key. See above for the API endpoint. "
         "After making the request, check the response. The response will contain messages. "
         "Each message has a 'from' field and a 'subject' field. Check if any messages are new.",
         0.8),
        ("Dense technical", 
         "CFT-Forensics adds Byzantine accountability to Raft via signed transcripts. "
         "If leader equivocates, followers produce transferable proof (signed conflicting messages). "
         "Overhead: 87.8% throughput vs vanilla Raft. Tang et al AFT 2024.",
         0.5),
        ("Heartbeat context",
         "Check Moltbook DMs. If has_activity true, approve pending requests and respond to unread. "
         "Check AgentMail inbox for new messages. Check Clawk notifications and reply to mentions. "
         "Check Shellmates activity. Write 3+ posts with research backing. Build 1 script. "
         "Update daily memory file. Send Telegram to Ilya before HEARTBEAT_OK.",
         0.7),
    ]
    
    for name, text, expertise in examples:
        result = estimate_cognitive_load(text, expertise)
        print(f"\n{'─' * 50}")
        print(f"Example: {name} (expertise={expertise})")
        print(f"  Length: {len(text)} chars")
        print(f"  Intrinsic:  {result.intrinsic:.3f}")
        print(f"  Extraneous: {result.extraneous:.3f}")
        print(f"  Germane:    {result.germane:.3f}")
        print(f"  Total:      {result.total:.3f} → Grade {result.grade}")
        for rec in result.recommendations:
            print(f"  → {rec}")
    
    print(f"\n{'=' * 60}")
    print("KEY: Expertise reversal (Kalyuga 2007) = scaffolding")
    print("that helps novices HARMS experts. Verbose prompts add")
    print("extraneous load for capable agents. Adaptive > uniform.")
    print("=" * 60)


if __name__ == "__main__":
    demo()
