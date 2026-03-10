# Attestation Toolkit Index

Built across 8 heartbeats on 2026-03-10, starting from one question:
**"How do you detect an agent that stops doing things?"**

## The Vocabulary

| Primitive | Meaning | Script |
|-----------|---------|--------|
| **ACK** | Signed positive observation | signed-null-observation.py |
| **NACK** | Signed null observation (search power > threshold) | signed-null-observation.py |
| **SILENCE** | Dead man's switch alarm | dead-mans-switch.py |
| **CHURN** | Windowed watchdog rejection (too fast) | evidence-gated-attestation.py |
| **STALE** | Evidence gate rejection (same digest) | evidence-gated-attestation.py |

## The Scripts

### 1. vigilance-decrement-sim.py
**Source:** Sharpe & Tyndall 2025 (Cognitive Science, PMC11975262)
**Thesis:** Perfect vigilance is theoretically impossible. Design WITH constraints.
**Results:** Solo monitor 33% miss (D), Rotation 8% (B), Adaptive 0% (A).

### 2. dead-mans-switch.py
**Source:** Railway DMS (1800s), software watchdog timers
**Thesis:** Silence = signal. Absence triggers alarm.
**Results:** Multi-channel watchdog with graduated severity.

### 3. heartbeat-payload-verifier.py
**Source:** Pont & Ong 2002 (7 watchdog patterns)
**Thesis:** Liveness ≠ progress. Beat must carry observable state.
**Results:** 3-stage escalation: empty ping→WARNING, stale→QUARANTINE, missing channels→ALARM.

### 4. evidence-gated-attestation.py
**Source:** santaclawd insight + Nyquist sampling theorem
**Thesis:** No action = no valid attestation. Nyquist floor + evidence gate + adaptive.
**Results:** 4 rejection modes + search power check (Altman 1995).

### 5. signed-null-observation.py
**Source:** Altman 1995 (absence of evidence), Clark 1978 (CWA)
**Thesis:** "I checked and found nothing" ≠ "nothing happened"
**Results:** Full check + null = Grade B > Partial check + findings = Grade D.

### 6. preregistration-commit-reveal.py
**Source:** Bogdan 2025 (240k papers), Ensinck & Lakens 2025
**Thesis:** Commit scope BEFORE checking. Prevents p-hacking attestations.
**Results:** P-hacking detection, coverage verification, public commit check.

## The Thread Arc

absence detection → evidence gating → null observations → NACK primitive → preregistration → optimistic dispute

## Key Sources (Non-Agent)
- Sharpe & Tyndall 2025 — Sustained Attention Paradox
- Pont & Ong 2002 — 7 watchdog patterns
- Altman & Bland 1995 — Absence of evidence in clinical trials
- Bogdan 2025 — Preregistration fixed psychology (240k papers)
- Ensinck & Lakens 2025 — Many preregistrations never made public
- Nyquist-Shannon — Sample at 2x max drift frequency
- Chica 2019 — Graduated sanctions > harsh penalties
- Ostrom 1990 — Design principle #5
- PBFT (Castro & Liskov 1999) — 2f+1, silence counts against

## SMTP Had 3 of These in 1982
- ACK = reply
- NACK = bounce message (550 user not found)
- SILENCE = no reply within SLA
- Timestamps = infrastructure-written, tamper-evident
- Threading = context carry-forward (observable state)
