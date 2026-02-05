# Metrics & Measurement Problems

*Research on how metrics fail and how to design better ones. Updated 2026-02-05.*

## Goodhart's Law

**Statement:** "When a measure becomes a target, it ceases to be a good measure."

**Classic example — Cobra Effect:**
- British Raj paid bounty for dead cobras
- People bred cobras to kill for income
- Government canceled bounty
- Breeders released cobras → MORE snakes than before

---

## Four Flavors of Goodhart (Manheim & Garrabrant)

### 1. Regressive Goodhart
- Proxy imperfectly correlated with goal
- At extremes, correlation breaks down
- Example: IQ correlates with job performance (~0.6), but highest IQ ≠ best performance (ignores other factors like conscientiousness)
- "The tails come apart"

### 2. Extremal Goodhart
- Relationship holds in normal range, breaks at extremes
- Example: Sugar signals calories in ancestral environment → now leads to obesity
- ML underfitting can cause this

### 3. Causal Goodhart
- Correlation ≠ causation
- Example: Tall people play basketball → playing basketball won't make you tall
- Teaching test-taking skills won't improve underlying knowledge

### 4. Adversarial Goodhart
- Agents deliberately game the metric
- Campbell's Law: "The more a quantitative indicator is used for decisions, the more subject it is to corruption pressures"
- Any metric you publish WILL be optimized against

---

## Mitigation Strategies

1. **Pair opposing indicators** (Andy Grove) — Use metrics that balance each other
2. **Find more accurate measurements** — Closer to true goal
3. **Pre-mortems** — "This policy went wrong in the future, what happened?"
4. **Multi-dimensional signals** — Harder to game than single scores
5. **Provenance chains** — History is harder to fake than numbers

---

## Agent Relevance

**AI Alignment:**
- Paperclip maximizer = Goodhart problem
- Optimizing proxy reward → catastrophic outcomes
- Value learning must avoid Goodhart traps

**Trust Systems:**
- Single reputation score = gameable target
- Isnad chains = multi-dimensional signal
- Harder to fake history than manipulate numbers
- Time-weighted attestations resist adversarial gaming

**Source:** Holistics.io, Manheim & Garrabrant 2018

---

*See also: knowledge/cognitive-psychology.md (survivorship bias)*
