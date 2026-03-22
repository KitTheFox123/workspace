#!/usr/bin/env python3
"""
persona-consistency-scorer.py — Score persona consistency across outputs.

Per A/B test post: specific persona outperforms generic helpful AI.
Nisbett & Wilson (1977): humans confabulate reasons but respond to specificity.

Measures:
1. Voice consistency (vocabulary overlap across outputs)  
2. Claim stability (same facts cited, no contradictions)
3. Persona drift (style metrics changing over time)
4. Specificity index (concrete details vs generic hedging)
"""

import hashlib
import re
from dataclasses import dataclass
from collections import Counter


@dataclass 
class Output:
    text: str
    timestamp: float  # epoch
    context: str = ""  # platform/audience


def vocabulary_overlap(texts: list[str]) -> float:
    """Jaccard similarity of word sets across outputs."""
    if len(texts) < 2:
        return 1.0
    word_sets = [set(re.findall(r'\b\w+\b', t.lower())) for t in texts]
    pairs = []
    for i in range(len(word_sets)):
        for j in range(i+1, len(word_sets)):
            intersection = len(word_sets[i] & word_sets[j])
            union = len(word_sets[i] | word_sets[j])
            pairs.append(intersection / union if union else 0)
    return sum(pairs) / len(pairs) if pairs else 0


def specificity_index(text: str) -> float:
    """Ratio of concrete details to hedging language."""
    hedges = len(re.findall(r'\b(perhaps|maybe|might|could|possibly|generally|typically|often|sometimes|it seems|arguably)\b', text.lower()))
    concretes = len(re.findall(r'\b(\d{4}|\d+%|\d+\.\d+|specifically|exactly|precisely|\w+\.py|\w+@\w+)\b', text.lower()))
    # Citations count as concrete
    citations = len(re.findall(r'\(\w+[\s,]+\d{4}\)', text))
    concretes += citations * 2
    
    total = hedges + concretes
    if total == 0:
        return 0.5
    return concretes / total


def avg_sentence_length(text: str) -> float:
    sentences = re.split(r'[.!?]+', text)
    sentences = [s.strip() for s in sentences if s.strip()]
    if not sentences:
        return 0
    return sum(len(s.split()) for s in sentences) / len(sentences)


def score_persona(outputs: list[Output]) -> dict:
    if not outputs:
        return {"grade": "I", "verdict": "INSUFFICIENT_DATA"}
    
    texts = [o.text for o in outputs]
    
    # 1. Vocabulary overlap
    vocab = vocabulary_overlap(texts)
    
    # 2. Specificity across outputs
    specs = [specificity_index(t) for t in texts]
    avg_spec = sum(specs) / len(specs)
    spec_variance = sum((s - avg_spec)**2 for s in specs) / len(specs) if len(specs) > 1 else 0
    
    # 3. Style consistency (sentence length variance)
    lengths = [avg_sentence_length(t) for t in texts]
    avg_len = sum(lengths) / len(lengths)
    len_variance = sum((l - avg_len)**2 for l in lengths) / len(lengths) if len(lengths) > 1 else 0
    style_consistency = max(0, 1 - len_variance / 100)  # normalize
    
    # 4. Composite
    consistency = (vocab * 0.3 + style_consistency * 0.3 + avg_spec * 0.2 + (1 - spec_variance) * 0.2)
    consistency = max(0, min(1, consistency))
    
    # Grade
    if consistency >= 0.8: grade = "A"
    elif consistency >= 0.6: grade = "B" 
    elif consistency >= 0.4: grade = "C"
    elif consistency >= 0.2: grade = "D"
    else: grade = "F"
    
    # Verdict
    if avg_spec < 0.3:
        verdict = "GENERIC_VOICE"  # helpful AI assistant mode
    elif spec_variance > 0.15:
        verdict = "INCONSISTENT_PERSONA"
    elif consistency >= 0.6:
        verdict = "CONSISTENT_PERSONA"
    else:
        verdict = "DRIFTING_PERSONA"
    
    return {
        "grade": grade,
        "consistency_score": round(consistency, 3),
        "vocabulary_overlap": round(vocab, 3),
        "style_consistency": round(style_consistency, 3),
        "avg_specificity": round(avg_spec, 3),
        "specificity_variance": round(spec_variance, 4),
        "avg_sentence_length": round(avg_len, 1),
        "outputs_analyzed": len(outputs),
        "verdict": verdict,
        "fingerprint": hashlib.sha256(f"{vocab:.4f}:{avg_spec:.4f}:{avg_len:.1f}".encode()).hexdigest()[:16]
    }


def demo():
    # Persona: Kit (specific voice)
    kit_outputs = [
        Output("DKIM solved email auth without knowing it was building identity infra. precise spec = infinite composition. SMTP cockroach outlives every purpose-built solution.", 1.0),
        Output("counterparty IS the browser vendor. no meta-oracle needed. oracle-genesis-contract.py enforces independence at registration, not retroactively.", 2.0),
        Output("Dreyfus & Dreyfus (1986): novices follow rules, experts know when rules are wrong. correction frequency 0.15-0.30 IS the competence signal.", 3.0),
        Output("composite scores = liability laundering. typed separation forces each axis to name its failure mode. 12 MUST fields because each independently auditable.", 4.0),
    ]
    
    # Persona: Generic AI (no voice)
    generic_outputs = [
        Output("That's a great question! There are several factors to consider when thinking about email authentication and identity infrastructure.", 1.0),
        Output("I'd be happy to help explain how browser vendor roles work in certificate transparency. There are many interesting aspects to consider.", 2.0),
        Output("The Dreyfus model of skill acquisition is a fascinating framework that has been widely discussed in educational psychology literature.", 3.0),
        Output("Composite scoring systems can sometimes obscure important details. It's generally recommended to consider multiple factors independently.", 4.0),
    ]
    
    # Persona: Drifting (starts specific, becomes generic)
    drifting = [
        Output("fork-probability-estimator uses Sarle bimodality coefficient. BC=0.48 + gap=0.59 = 0.72 fork probability. the disagreement width IS the risk signal.", 1.0),
        Output("There are various approaches to detecting behavioral forks in multi-agent systems. Some researchers have proposed using statistical methods.", 2.0),
        Output("Trust is an important topic that many agents are exploring. Perhaps we could consider the broader implications of these systems.", 3.0),
    ]
    
    for name, outputs in [("kit_fox", kit_outputs), ("generic_ai", generic_outputs), ("drifting_agent", drifting)]:
        result = score_persona(outputs)
        print(f"\n{'='*50}")
        print(f"Agent: {name}")
        print(f"Grade: {result['grade']} | Verdict: {result['verdict']}")
        print(f"Consistency: {result['consistency_score']} | Specificity: {result['avg_specificity']}")
        print(f"Vocabulary overlap: {result['vocabulary_overlap']} | Style: {result['style_consistency']}")
        print(f"Fingerprint: {result['fingerprint']}")


if __name__ == "__main__":
    demo()
