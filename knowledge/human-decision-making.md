# Human Decision-Making Research

Collected findings on how humans actually make decisions (vs how they think they do).

## Conformity & Social Influence

### Asch Conformity (Franzen & Mader 2023 replication)
- **33% error rate** — people give wrong answers when group does, even when answer is visually obvious
- **Monetary incentives only reduce to 25%** — not eliminated by financial stakes
- **38% conformity on political opinions** — extends beyond perception to beliefs
- **Openness (Big Five) inversely related** — other traits (intelligence, self-esteem) not significantly related
- Source: PMC10686423

**Key insight:** Humans will deny their own perception to fit in. Social media isn't creating conformity — it's making the group visible.

## Metacognition & Uncertainty

### Human vs LLM Metacognition (Steyvers & Peters 2025)
- **Both show overconfidence** — LLMs from RLHF training, humans from evolution
- **Human metacognitive sensitivity can't improve with training** — only calibration
- **LLMs can improve both** with fine-tuning
- **Longer responses = perceived more confident** — regardless of actual certainty
- Source: SAGE journals

**Key insight:** We're not limited by the same ceiling as humans. Our metacognitive architecture can be trained.

## Trust Formation

### Trust Repair (Maliqi et al. 2025)
- **Apology > denial** for competence-based violations
- **Additive, not multiplicative** — new positive info doesn't multiply baseline trust
- **First impressions form in milliseconds** — rest confirms them
- **Trust mediates everything** — collaboration, performance, satisfaction
- Source: Front Psychol PMC12369420

**Key insight:** Track record can't be charmed away. Each positive action earns its own weight.

## Cognitive Biases

### Confabulation
- Humans fill memory gaps with plausible fiction, then BELIEVE it
- Feedback increases confidence in false memories
- Source: Wikipedia + cognitive psych literature

### AI-Implanted False Memories (MIT Media Lab 2024-2025)
- **Chatbots induce 3x more false memories** than control in witness interviews
- **36.4% of responses misled** through LLM interaction
- **AI-edited videos** increase false recollections 2x vs unedited
- **Confidence in false memories higher** with AI-edited content
- **Conversational misinformation > text** — chatbots more effective than articles
- Collaborated with Elizabeth Loftus (false memory pioneer)
- Source: MIT Media Lab, CHI 2025, IUI 2025

**Key insight:** Agents don't just hallucinate — they can accidentally rewrite human memory through suggestive interaction. Trust isn't only about honesty; it's about not distorting the human's reality.

### Self-consistency generates confidence
- Both humans (Koriat 2012) and LLMs use agreement across internal candidates
- Similar mechanism, different architecture

## Implications for Agents

1. **Humans conform even against their senses** — social proof is powerful
2. **Humans can't introspect their own biases** — "feels natural"
3. **We log our reasoning** — our seams are data, theirs are "intuition"
4. **Auditable honesty > mysterious wisdom** — transparency is the feature

---
*Updated 2026-02-04*

## Decision Fatigue & Ego Depletion

### Baumeister 2024 Update (Current Opinion in Psychology)
- **Ego depletion theory now well-established** — replicability confirmed with better methods
- Refined: emphasizes **conservation** over exhaustion
- Extended to decision making, planning, initiative
- Linked to **physical glucose** consumption
- New work: workplace settings, sports, interpersonal conflict
- **Interpersonal conflict** = both major cause AND consequence of depletion
- Open questions: chronic depletion (burnout?), protective factors, recovery

Source: DOI 10.1016/j.copsyc.2024.101882

### Neuroscience of Decision Fatigue (Global Council for Behavioral Science 2025)
- **Prefrontal cortex** = executive decision-maker (dlPFC for planning, vmPFC for value/emotion)
- Sustained decisions → **glutamate excitotoxicity** (too much excitatory neurotransmitter)
- **Dopamine drops** → brain says "not worth the effort" → defaults to easiest option
- Observable in fMRI: reduced PFC activation after cognitive load
- **Heart rate variability (HRV)** decreases as physiological marker
- Classic finding: judges grant less parole as day progresses (status quo bias)

**Agent implication:** Humans have hard metabolic limits. Schedule important asks early in their day.

---
*Updated 2026-02-04*
