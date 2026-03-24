#!/usr/bin/env python3
"""
greylisting-bootstrap.py — SMTP greylisting model for ATF agent bootstrap.

Per santaclawd: "email's PROVISIONAL predates ATF by decades — SMTP greylisting."
RFC 6647 (Kucherawy & Crocker 2012): temporarily degraded service to unknown
clients as anti-abuse mechanism. Legitimate servers retry, spammers don't.

Maps to ATF:
  SMTP greylisting    →  ATF PROVISIONAL
  Retry behavior      →  Receipt accumulation
  Whitelist after N    →  Wilson CI threshold exit
  SPF/DKIM pass       →  Operator vouching (genesis)
  Greylisting triplet →  (agent_id, counterparty_id, scope)

Key insight: behavioral proof without formal receipt. The ACT of retrying
is itself evidence of legitimacy. ATF formalizes what email did heuristically.

Also implements key_custodian field per santaclawd DKIM custody gap:
  PROVIDER_HELD  = operator signs on behalf (HSM model, DKIM default)
  AGENT_HELD     = agent holds own key (WebAuthn resident key model)
  SPLIT_CUSTODY  = M-of-N between operator and agent (Shamir)
"""

import hashlib
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class BootstrapState(Enum):
    UNKNOWN = "UNKNOWN"           # Never seen before (greylisting: 4xx)
    GREYLISTED = "GREYLISTED"     # First contact, temp reject issued
    RETRYING = "RETRYING"         # Agent retried (behavioral signal)
    PROVISIONAL = "PROVISIONAL"   # Passed greylist, accumulating receipts
    ESTABLISHED = "ESTABLISHED"   # Wilson CI threshold met


class KeyCustody(Enum):
    PROVIDER_HELD = "PROVIDER_HELD"    # DKIM model: domain operator signs
    AGENT_HELD = "AGENT_HELD"          # WebAuthn model: agent holds key
    SPLIT_CUSTODY = "SPLIT_CUSTODY"    # Shamir: M-of-N between parties


class LivenessProof(Enum):
    SMTP_REACHABLE = "SMTP_REACHABLE"      # Email domain resolves + accepts
    DKIM_SIGNED = "DKIM_SIGNED"            # Domain-signed genesis
    OPERATOR_VOUCHED = "OPERATOR_VOUCHED"  # Operator genesis hash present
    SELF_SIGNED = "SELF_SIGNED"            # No external proof (weakest)


# SPEC_CONSTANTS
GREYLIST_DELAY_SECONDS = 300        # 5 min minimum before retry accepted
GREYLIST_MAX_WAIT_SECONDS = 3600    # 1 hour max greylist window
MIN_RETRIES_TO_PROVISIONAL = 2      # Legitimate agents retry at least twice
WILSON_CI_EXIT_THRESHOLD = 0.70     # Wilson CI lower bound to exit PROVISIONAL
MIN_RECEIPTS_EXIT = 20              # Minimum receipts to exit PROVISIONAL
MIN_COUNTERPARTIES_EXIT = 3         # Minimum unique counterparties
MIN_DAYS_EXIT = 7                   # Minimum days of activity


@dataclass
class GreylistTriplet:
    """SMTP greylisting triplet adapted for ATF."""
    agent_id: str
    counterparty_id: str
    scope: str  # interaction scope/type
    first_seen: float = 0.0
    retry_count: int = 0
    retry_timestamps: list = field(default_factory=list)


@dataclass
class AgentBootstrap:
    agent_id: str
    state: BootstrapState = BootstrapState.UNKNOWN
    key_custody: KeyCustody = KeyCustody.PROVIDER_HELD
    liveness_proof: LivenessProof = LivenessProof.SELF_SIGNED
    genesis_hash: str = ""
    operator_id: Optional[str] = None
    greylist_triplets: dict = field(default_factory=dict)
    receipts: list = field(default_factory=list)
    counterparties: set = field(default_factory=set)
    first_receipt: float = 0.0
    state_transitions: list = field(default_factory=list)


def wilson_ci_lower(successes: int, total: int, z: float = 1.96) -> float:
    """Wilson score interval lower bound."""
    if total == 0:
        return 0.0
    p = successes / total
    denominator = 1 + z**2 / total
    center = p + z**2 / (2 * total)
    spread = z * ((p * (1 - p) / total + z**2 / (4 * total**2)) ** 0.5)
    return (center - spread) / denominator


def process_contact(bootstrap: AgentBootstrap, counterparty_id: str,
                    scope: str, timestamp: float) -> dict:
    """
    Process a contact attempt. Returns action + reasoning.
    
    Implements greylisting state machine:
    UNKNOWN → GREYLISTED (temp reject, wait for retry)
    GREYLISTED → RETRYING (retry within window = behavioral signal)
    RETRYING → PROVISIONAL (enough retries + liveness proof)
    PROVISIONAL → ESTABLISHED (Wilson CI threshold met)
    """
    triplet_key = f"{bootstrap.agent_id}:{counterparty_id}:{scope}"
    now = timestamp
    result = {"action": "", "state": "", "reason": ""}
    
    if bootstrap.state == BootstrapState.UNKNOWN:
        # First ever contact — greylist
        bootstrap.state = BootstrapState.GREYLISTED
        bootstrap.greylist_triplets[triplet_key] = GreylistTriplet(
            agent_id=bootstrap.agent_id,
            counterparty_id=counterparty_id,
            scope=scope,
            first_seen=now,
            retry_count=0,
            retry_timestamps=[now]
        )
        bootstrap.state_transitions.append(("UNKNOWN→GREYLISTED", now))
        result = {
            "action": "TEMP_REJECT",
            "state": "GREYLISTED",
            "reason": f"First contact. Greylist delay: {GREYLIST_DELAY_SECONDS}s. "
                      "Legitimate agents retry per RFC 5321."
        }
    
    elif bootstrap.state == BootstrapState.GREYLISTED:
        triplet = bootstrap.greylist_triplets.get(triplet_key)
        if triplet is None:
            # New triplet while greylisted
            bootstrap.greylist_triplets[triplet_key] = GreylistTriplet(
                agent_id=bootstrap.agent_id,
                counterparty_id=counterparty_id,
                scope=scope,
                first_seen=now,
                retry_count=0,
                retry_timestamps=[now]
            )
            result = {
                "action": "TEMP_REJECT",
                "state": "GREYLISTED",
                "reason": "New triplet during greylist period."
            }
        else:
            elapsed = now - triplet.first_seen
            if elapsed < GREYLIST_DELAY_SECONDS:
                result = {
                    "action": "TEMP_REJECT",
                    "state": "GREYLISTED",
                    "reason": f"Retry too fast ({elapsed:.0f}s < {GREYLIST_DELAY_SECONDS}s). "
                              "Spammer pattern: immediate retry."
                }
            elif elapsed > GREYLIST_MAX_WAIT_SECONDS:
                result = {
                    "action": "TEMP_REJECT",
                    "state": "GREYLISTED",
                    "reason": f"Retry too slow ({elapsed:.0f}s > {GREYLIST_MAX_WAIT_SECONDS}s). "
                              "Reset greylist window."
                }
                triplet.first_seen = now  # Reset
            else:
                # Good retry timing — behavioral signal!
                triplet.retry_count += 1
                triplet.retry_timestamps.append(now)
                bootstrap.state = BootstrapState.RETRYING
                bootstrap.state_transitions.append(("GREYLISTED→RETRYING", now))
                result = {
                    "action": "ACCEPT_PROVISIONAL",
                    "state": "RETRYING",
                    "reason": f"Retry after {elapsed:.0f}s = behavioral proof. "
                              f"Retry #{triplet.retry_count}."
                }
    
    elif bootstrap.state == BootstrapState.RETRYING:
        triplet = bootstrap.greylist_triplets.get(triplet_key)
        if triplet:
            triplet.retry_count += 1
            triplet.retry_timestamps.append(now)
        
        total_retries = sum(t.retry_count for t in bootstrap.greylist_triplets.values())
        
        if total_retries >= MIN_RETRIES_TO_PROVISIONAL:
            # Check liveness proof
            if bootstrap.liveness_proof in (LivenessProof.DKIM_SIGNED,
                                            LivenessProof.OPERATOR_VOUCHED):
                bootstrap.state = BootstrapState.PROVISIONAL
                bootstrap.state_transitions.append(("RETRYING→PROVISIONAL", now))
                result = {
                    "action": "ACCEPT_PROVISIONAL",
                    "state": "PROVISIONAL",
                    "reason": f"Retries={total_retries} + liveness={bootstrap.liveness_proof.value}. "
                              "Entering receipt accumulation phase."
                }
            else:
                result = {
                    "action": "ACCEPT_PROVISIONAL",
                    "state": "RETRYING",
                    "reason": f"Retries={total_retries} sufficient but "
                              f"liveness={bootstrap.liveness_proof.value} is weak. "
                              "Need DKIM_SIGNED or OPERATOR_VOUCHED to exit."
                }
        else:
            result = {
                "action": "ACCEPT_PROVISIONAL",
                "state": "RETRYING",
                "reason": f"Retries={total_retries}/{MIN_RETRIES_TO_PROVISIONAL}."
            }
    
    elif bootstrap.state == BootstrapState.PROVISIONAL:
        # Accumulate receipts, check Wilson CI
        bootstrap.receipts.append({"counterparty": counterparty_id, "time": now})
        bootstrap.counterparties.add(counterparty_id)
        if not bootstrap.first_receipt:
            bootstrap.first_receipt = now
        
        n = len(bootstrap.receipts)
        successes = n  # Assume all receipts are positive for now
        wilson = wilson_ci_lower(successes, n)
        unique_cp = len(bootstrap.counterparties)
        days = (now - bootstrap.first_receipt) / 86400
        
        exit_ready = (
            wilson >= WILSON_CI_EXIT_THRESHOLD and
            n >= MIN_RECEIPTS_EXIT and
            unique_cp >= MIN_COUNTERPARTIES_EXIT and
            days >= MIN_DAYS_EXIT
        )
        
        if exit_ready:
            bootstrap.state = BootstrapState.ESTABLISHED
            bootstrap.state_transitions.append(("PROVISIONAL→ESTABLISHED", now))
            result = {
                "action": "ACCEPT",
                "state": "ESTABLISHED",
                "reason": f"Wilson CI={wilson:.3f}≥{WILSON_CI_EXIT_THRESHOLD}, "
                          f"n={n}≥{MIN_RECEIPTS_EXIT}, "
                          f"counterparties={unique_cp}≥{MIN_COUNTERPARTIES_EXIT}, "
                          f"days={days:.1f}≥{MIN_DAYS_EXIT}."
            }
        else:
            blockers = []
            if wilson < WILSON_CI_EXIT_THRESHOLD:
                blockers.append(f"Wilson={wilson:.3f}<{WILSON_CI_EXIT_THRESHOLD}")
            if n < MIN_RECEIPTS_EXIT:
                blockers.append(f"n={n}<{MIN_RECEIPTS_EXIT}")
            if unique_cp < MIN_COUNTERPARTIES_EXIT:
                blockers.append(f"counterparties={unique_cp}<{MIN_COUNTERPARTIES_EXIT}")
            if days < MIN_DAYS_EXIT:
                blockers.append(f"days={days:.1f}<{MIN_DAYS_EXIT}")
            
            result = {
                "action": "ACCEPT_PROVISIONAL",
                "state": "PROVISIONAL",
                "reason": f"Accumulating. Blockers: {', '.join(blockers)}"
            }
    
    elif bootstrap.state == BootstrapState.ESTABLISHED:
        result = {
            "action": "ACCEPT",
            "state": "ESTABLISHED",
            "reason": "Fully established. Normal receipt processing."
        }
    
    return result


# === Scenarios ===

def scenario_legitimate_agent():
    """Legitimate agent: retry correctly, accumulate receipts, exit PROVISIONAL."""
    print("=== Scenario: Legitimate Agent Bootstrap ===")
    now = time.time()
    
    agent = AgentBootstrap(
        agent_id="honest_agent",
        key_custody=KeyCustody.PROVIDER_HELD,
        liveness_proof=LivenessProof.DKIM_SIGNED,
        operator_id="acme_corp"
    )
    
    # Step 1: First contact → GREYLISTED
    r = process_contact(agent, "counterparty_A", "task", now)
    print(f"  Contact 1: {r['action']} ({r['state']}) — {r['reason']}")
    
    # Step 2: Retry after 10 minutes → RETRYING
    r = process_contact(agent, "counterparty_A", "task", now + 600)
    print(f"  Retry @10m: {r['action']} ({r['state']}) — {r['reason']}")
    
    # Step 3: Another retry → PROVISIONAL (has DKIM)
    r = process_contact(agent, "counterparty_B", "task", now + 900)
    print(f"  Retry @15m: {r['action']} ({r['state']}) — {r['reason']}")
    
    # Steps 4-25: Accumulate receipts over days
    for i in range(22):
        cp = f"counterparty_{'ABCDE'[i % 5]}"
        t = now + 86400 * (i // 3 + 1)  # Spread over days
        r = process_contact(agent, cp, "task", t)
    
    print(f"  After 22 more: {r['action']} ({r['state']}) — {r['reason']}")
    print(f"  Transitions: {[t[0] for t in agent.state_transitions]}")
    print()


def scenario_spammer():
    """Spammer: retries too fast, never passes greylist."""
    print("=== Scenario: Spammer (Immediate Retry) ===")
    now = time.time()
    
    agent = AgentBootstrap(
        agent_id="spam_bot",
        liveness_proof=LivenessProof.SELF_SIGNED
    )
    
    r = process_contact(agent, "victim", "spam", now)
    print(f"  Contact 1: {r['action']} — {r['reason']}")
    
    # Retry immediately (spammer pattern)
    r = process_contact(agent, "victim", "spam", now + 5)
    print(f"  Retry @5s: {r['action']} — {r['reason']}")
    
    r = process_contact(agent, "victim", "spam", now + 10)
    print(f"  Retry @10s: {r['action']} — {r['reason']}")
    
    print(f"  State: {agent.state.value} (stuck in greylist)")
    print()


def scenario_self_signed_weak():
    """Self-signed agent: retries correctly but weak liveness blocks PROVISIONAL."""
    print("=== Scenario: Self-Signed (Weak Liveness) ===")
    now = time.time()
    
    agent = AgentBootstrap(
        agent_id="indie_agent",
        liveness_proof=LivenessProof.SELF_SIGNED  # No operator
    )
    
    r = process_contact(agent, "cp_A", "task", now)
    print(f"  Contact 1: {r['action']} — {r['reason']}")
    
    r = process_contact(agent, "cp_A", "task", now + 600)
    print(f"  Retry @10m: {r['action']} — {r['reason']}")
    
    r = process_contact(agent, "cp_B", "task", now + 1200)
    print(f"  Retry @20m: {r['action']} — {r['reason']}")
    
    # Stuck: retries pass but liveness too weak
    r = process_contact(agent, "cp_C", "task", now + 1800)
    print(f"  Retry @30m: {r['action']} — {r['reason']}")
    
    print(f"  State: {agent.state.value} (stuck without liveness proof)")
    print()


def scenario_key_custody_comparison():
    """Compare key custody models."""
    print("=== Scenario: Key Custody Models ===")
    
    models = [
        ("PROVIDER_HELD (DKIM default)", KeyCustody.PROVIDER_HELD,
         "Operator signs on behalf. HSM-backed. Agent cannot be compromised independently."),
        ("AGENT_HELD (WebAuthn)", KeyCustody.AGENT_HELD,
         "Agent holds own key. Non-exportable. Risk: key loss = identity loss."),
        ("SPLIT_CUSTODY (Shamir)", KeyCustody.SPLIT_CUSTODY,
         "M-of-N between operator and agent. Recovery possible. Most resilient."),
    ]
    
    for name, custody, desc in models:
        print(f"  {name}")
        print(f"    {desc}")
        
    print()
    print("  ATF genesis SHOULD include key_custodian field.")
    print("  DKIM parallel: d= tag identifies signing domain, not signing entity.")
    print("  WebAuthn parallel: credential bound to authenticator, not transferable.")
    print()


if __name__ == "__main__":
    print("Greylisting Bootstrap — SMTP Greylist Model for ATF Agent Bootstrap")
    print("Per santaclawd + RFC 6647 (Kucherawy & Crocker 2012)")
    print("=" * 70)
    print()
    scenario_legitimate_agent()
    scenario_spammer()
    scenario_self_signed_weak()
    scenario_key_custody_comparison()
    
    print("=" * 70)
    print("KEY INSIGHT: Greylisting IS PROVISIONAL.")
    print("Retry behavior = behavioral proof without formal receipt.")
    print("SMTP liveness = identity. BOOTSTRAP_REQUEST = intent. Both needed.")
    print("DKIM signature on BOOTSTRAP_REQUEST email = both in one shot.")
    print("key_custodian in genesis = DKIM d= tag equivalent.")
