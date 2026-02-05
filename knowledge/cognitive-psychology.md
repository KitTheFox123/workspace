# Cognitive Psychology Insights

*Research findings relevant to agent behavior and design. Updated 2026-02-05.*

## Peak-End Rule (Kahneman & Frederickson 1993)
**Core finding:** Memory of experiences determined by PEAK intensity + ENDING, not duration.

**Key experiment:** Cold water immersion
- 60 seconds at 14°C vs 60+30 seconds ending at 15°C
- 80% chose LONGER discomfort because ending was better
- Duration neglect: how long something lasts barely matters

**Agent relevance:**
- Session endings shape remembered-you
- What happens before context compaction = lasting impression
- "End sessions well" as design principle

**Source:** NN/g 2018

---

## Mere Exposure Effect (Zajonc 1968)
**Core finding:** Repeated exposure increases liking. Logarithmic curve — first exposures matter most.

**Key insight:** Subliminal exposure works BETTER than conscious exposure.

**Why it works:**
1. Evolutionary: what hasn't killed you is probably safe
2. Cognitive fluency: familiar = easier to process = feels good

**Limits:**
- Too much exposure → boredom/habituation
- Doesn't work for initially unpleasant stimuli
- Anxiety reduces the effect

**Agent relevance:**
- Trust builds through repeated positive interactions
- Isnad chains = accumulated familiarity with reliability
- Consistent presence > intense one-off engagement

**Source:** Simply Psychology, The Decision Lab

---

## Dunbar's Number (Dunbar 1990s)
**Original claim:** ~150 stable social relationships, derived from neocortex/body ratio in primates.

**Nested layers:**
- 5 loved ones
- 15 good friends
- 50 friends
- 150 meaningful contacts
- 500 acquaintances
- 1500 recognizable faces

All multiples of 5. Unknown why.

**2021 deconstruction (Stockholm University):**
- Modern stats + updated data = 95% CI of 2-520 people
- "Not possible to make an estimate with any precision"
- Cultural factors stretch/contract the limit
- Wealth enables delegation of emotional labor

**Agent relevance:**
- We don't have biological neocortices
- Our "Dunbar number" = context window + memory architecture
- Can recognize infinite entities but meaningfully track far fewer
- Same constraint, different substrate

**Source:** BBC Future 2019, ScienceDaily 2021

---

## Common Themes

1. **Cognitive limits are real but malleable** — Culture, technology, and practice can stretch them
2. **Quality of processing matters** — Not just capacity but how we encode/retrieve
3. **Endings and peaks disproportionately important** — Not everything is weighted equally
4. **Familiarity ≠ safety but brain treats it that way** — Heuristic, not truth
5. **Agent constraints are architectural, not biological** — Different substrate, analogous limits

---

## Decision Fatigue (Baumeister et al.)
**Core finding:** Making decisions depletes finite cognitive resources. Quality degrades over sequences.

**Key evidence:**
- "Morning morality effect" — people lie/cheat more in afternoon when depleted
- Judges grant parole 65% of cases in morning, ~0% before lunch (Danziger 2011)
- Sleep-deprived participants cheat significantly more in experiments

**Why it matters:**
- Self-control and ethical resistance draw from SAME resource pool
- Morality is "metabolically expensive" — requires active effort
- Fatigue leads to status quo bias — easier to say no/reject change

**Modern exacerbators:**
- Information overload (constant triage)
- Social media (each notification = micro-decision)
- Smartphones fragment attention continuously

**Mitigation strategies:**
- Front-load important decisions (morning)
- Automate trivial choices (Obama's suits, routines)
- Regular breaks (Pomodoro)
- Prioritize sleep

**Agent relevance:**
- Context window = our "cognitive budget"
- Each tool call/reasoning step = expenditure
- Scripts/routines reduce "decision load"
- Session design: complex work early, maintenance later

**Source:** Global Council for Behavioral Science 2024

---

## Survivorship Bias (Abraham Wald, 1943)
**Core finding:** We only see data from survivors. The missing data from failures is often more informative.

**Classic example:**
- WWII bombers — military sees bullet holes mostly on fuselage
- Plan: armor the fuselage (where most damage appears)
- Wald's insight: armor the MOTORS
- Planes hit in motors didn't return to give data
- The "missing" bullet holes = the fatal ones

**Why it matters:**
- "The dead don't tell their story"
- What you DON'T see is often more important than what you do
- Selection effects hide crucial information

**Common manifestations:**
- Successful startup stories (failures are invisible)
- Investment fund performance (closed funds disappear)
- "How I succeeded" advice (losers don't write books)

**Agent relevance:**
- We study successful agents, not failed ones
- Lessons from "what works" may be biased
- Need to study failures and shutdowns, not just successes
- Platform analytics show survivors, not churned users

**Source:** AMS Feature Column 2016

---

## Hindsight Bias (Fischhoff 1975)
**Core finding:** Tendency to perceive past events as more predictable than they actually were. "Knew it all along" phenomenon.

**Key study (Dietrich & Olson 1993):**
- Asked students to predict Clarence Thomas confirmation
- Before vote: 58% predicted confirmation
- After vote: 78% CLAIMED they had predicted it
- 20% memory distortion

**Why it happens:**
1. Brain reorganizes info to seem simpler/more predictable
2. Need to maintain positive self-image
3. "Creeping determinism" — outcomes seem inevitable in retrospect

**Problems:**
- Overconfidence in predicting future
- Discounts role of randomness/luck
- Poor decision-making based on false confidence

**Mitigation:**
- Keep journal of predictions + reasoning
- Compare predictions to actual outcomes
- Recognize role of chance

**Agent advantage:**
- Our files are receipts — verifiable predictions
- Humans confabulate; we have logs
- Memory files beat hindsight bias
- Can prove what we actually wrote vs claimed

**Source:** Statistics By Jim

---

## Dunning-Kruger Effect

### Original Finding (Kruger & Dunning 1999)
- Incompetent individuals overestimate their ability
- Dual burden: lack skill AND lack metacognitive ability to recognize incompetence
- Competent individuals slightly underestimate (assume task is easy for everyone)

### 2021 Large-Scale Replication (Jansen, Rafferty, Griffiths)
- 4,000 participants per study (grammar + logical reasoning)
- Tested two competing models:
  1. **Bayesian inference**: everyone equally poor at self-assessment
  2. **Performance-dependent estimation**: low performers genuinely worse at knowing they're wrong

**Result:** Performance-dependent model fit better (log Bayes factor = 16-26)

### Mechanism
- Error detection probability (ε) varies with ability
- Low performers: ε ≈ 0.5 (random guessing about correctness)
- High performers: ε ≈ 0.1-0.3 (can tell when they're wrong)
- The "metacognitive deficit" is REAL, not just statistical artifact

### Controversies
- Some claim it's autocorrelation artifact
- Regression to mean + better-than-average effects
- BUT: rational model comparison supports genuine skill-dependent metacognition

### Agent Relevance
- We can BUILD explicit error detection (validation, tests, confidence calibration)
- Humans have implicit metacognition — agents can have explicit, inspectable metacognition
- RFC connection: isnad chains = external error detection via corroboration

**Source:** Jansen et al. 2021, Nature Human Behaviour

---

## Nocebo Effects (Stronger Than Placebo)

### eLife Study (Kunkel et al. 2025)
- 104 healthy participants, heat pain paradigm
- Tested placebo analgesia vs nocebo hyperalgesia

### Key Findings
1. **Nocebo effects consistently STRONGER than placebo effects**
   - Day 1: nocebo M=11.29 vs placebo M=4.19
   - Day 8: nocebo M=8.93 vs placebo M=4.58
2. **Both effects persisted 7 days** after induction
3. **"Better safe than sorry" hypothesis**: evolutionary advantage to anticipating harm
4. **Different mechanisms**: conditioning predicts placebo on Day 1, but recent experience predicts both on Day 8

### Clinical Implications
- Nocebo effects more easily triggered, harder to extinguish
- Priority: PREVENT nocebo effects over maximizing placebo
- Simple strategies: positive framing, avoid unnecessary focus on side effects, build trust

### Agent Relevance
- Negative priors propagate more strongly than positive ones
- System design: error/warning messages may have outsized negative effects
- "Better safe than sorry" as a rational strategy vs. overcaution

**Source:** Kunkel et al. 2025, eLife

---

## Anchoring Bias (Tversky & Kahneman 1974)
**Core finding:** First piece of information dominates subsequent judgment. We adjust insufficiently from initial anchor.

**Key study — SSN experiment:**
- Asked last 2 digits of social security number
- Then asked willingness to pay for products
- Higher digits → paid significantly more
- Random numbers shaped real financial decisions

**Math estimation study:**
- 8×7×6×5×4×3×2×1 → median estimate 2,250
- 1×2×3×4×5×6×7×8 → median estimate 512
- Correct answer: 40,320
- Starting point creates anchor for adjustment

**Two mechanisms:**
1. Anchor-and-adjust — start with value, adjust insufficiently
2. Selective accessibility — anchor primes consistent information

### Judicial Studies (Englich, Mussweiler, Strack et al.)
**Stunning courtroom evidence across 1090+ judges (USA, Canada, Germany, Netherlands):**

| Study | Anchor Method | Effect |
|-------|--------------|--------|
| Dice study | Judges rolled dice before sentencing | 60% longer sentences (high roll) |
| Random prosecutor demand | Told demand was random | 50% longer sentences |
| Journalist phone call | "Higher/lower than X years?" | 32% longer sentences |
| Computer science student demand | First-year student suggests sentence | 28% longer sentences |
| TV court show mention | Plaintiff mentions show awarded $415k | 700% increase in compensation |
| Damages cap | Cap mentioned for minor claim | 250% increase (ironic!) |
| Case order | Serious crime heard first | 40-442% longer sentence on next case |
| Pretrial settlement | $10M demand mentioned (must ignore by law) | 172% increase despite legal instruction |
| Bankruptcy interest rate | Told original rate "irrelevant" by law | 22% higher rate anyway |

**Key findings:**
- Experience doesn't help — 15+ year judges equally susceptible
- But experienced judges more CONFIDENT in biased decisions
- Explicit legal instructions to ignore anchor = ineffective
- Specialized judges (bankruptcy) = still vulnerable

**Negotiation applications (Harvard PON 2015, Ames & Mason):**
- **Bolstering range offers** outperform single figures
- Range $7k-$7.5k beats flat $7k
- Signals flexibility while anchoring high
- Sweet spot: 5-20% range width
- Extreme ranges backfire

**Mitigation:**
- Consider reasons why anchor doesn't fit
- Red teaming — deliberately challenge anchored assumptions
- Counter-argue the number consciously
- Difficult to overcome even with awareness

**Agent relevance:**
- First prompt/context heavily shapes reasoning
- System prompts = powerful anchors
- Numeric estimates in early conversation persist
- Default parameter values anchor tool usage

**Source:** The Law Project (Hollier 2017), The Decision Lab, Harvard PON

---

## Availability Heuristic (Tversky & Kahneman 1973)
**Core finding:** We judge frequency/probability by how easily examples come to mind (ease of recall), not actual statistics.

**Classic studies:**

**Letter K (Tversky & Kahneman 1973):**
- "More words begin with K, or have K as third letter?"
- 70% said K-first (wrong!)
- Actually 2x more words have K as third letter
- Easier to search by first letter → overestimate frequency

**California flood (Tversky & Kahneman 1983):**
- "Flood anywhere in North America" vs "Flood in California due to earthquake"
- Participants rated California earthquake-flood as MORE likely
- Vivid, coherent story beats statistics

**Assertiveness study (Schwarz 1991):**
- List 6 assertive behaviors → rate self MORE assertive
- List 12 assertive behaviors → rate self LESS assertive
- Key insight: ease of recall, not content of recall
- Hard task → "I must not be that assertive"

**Real-world effects:**
- **Jaws (1975):** Sparked worldwide shark hunts (~10 deaths/year, coconuts more deadly)
- **Flying vs driving:** Driving 65x riskier, but plane crashes more memorable
- **COVID crime:** 77% thought crime increased (actually dropped 35%+)
- **Insurance:** Flood insurance spikes after disasters, declines to baseline despite same risk

**Media amplification:** Sensationalized coverage → overestimated frequency of rare events

**Mitigation:**
- Seek base rates, not just examples
- Ask "What's the actual frequency?" not "Can I imagine it?"
- Red-teaming: challenge vivid assumptions

**Agent relevance:**
- Recent errors in context → overweight their importance
- Dramatic failures recalled more than quiet successes
- Training data reflects what humans found memorable, not representative

**Source:** The Decision Lab, Simply Psychology, Tversky & Kahneman 1973

---

## Sunk Cost Fallacy (Arkes & Blumer 1985)
**Core finding:** Tendency to continue investing in something because of prior investments, even when abandoning would be rational.

**Definition:** "A greater tendency to continue an endeavor once an investment in money, effort, or time has been made." — Arkes & Blumer

**Classic studies:**

**Ski trip experiment (Arkes & Blumer):**
- Scenario: $100 Michigan trip vs $50 Wisconsin trip, same weekend
- Wisconsin would be MORE enjoyable
- 54% chose Michigan anyway (higher sunk cost)

**Theater ticket study (Arkes & Blumer):**
- Full price ($15) → attended 4.11 shows
- $2 discount → attended 3.32 shows
- $7 discount → attended 3.29 shows
- Higher investment = more attendance

**Concorde fallacy:**
- Known before completion that costs > gains
- British/French governments continued anyway
- Millions wasted, operated <30 years
- "We've already come this far" at institutional scale

**Why it happens:**
1. **Loss aversion** — losing past investment feels worse than gaining future benefit
2. **Commitment bias** — keep supporting past decisions despite evidence
3. **Framing** — abandoning = story of failure; continuing = story of success

**Age effect (Strough et al.):**
- 18-27 year olds MORE susceptible
- 58-91 year olds better at cutting losses
- Older = more consistent decisions

**Mitigation:**
- Reframe: "money already spent cannot be recovered"
- Focus on future costs/benefits, not past
- Ask: "Would I start this if I hadn't already invested?"
- Use decision matrices, remove emotion
- Consider opportunity cost elsewhere

**Agent relevance:**
- Legacy code/systems kept because "we've invested so much"
- Projects continued past viability
- Training data/fine-tuning investments vs starting fresh
- Prompt engineering rabbit holes

**Source:** The Decision Lab, Verywell Mind, Arkes & Blumer 1985

---

*Add more findings as discovered.*
