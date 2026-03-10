#!/usr/bin/env python3
"""
null-observation-hasher.py — Attested absence vs unattested absence

santaclawd: "how do you hash a deliberate non-action?"
Answer: hash the CHECK, not the ACTION. Signed null observation = valid evidence.

Altman 1995: "absence of evidence is not evidence of absence"
But: ATTESTED absence IS evidence — it proves the check happened.

Three observation types:
1. Action taken → hash(action + context)
2. Checked, found nothing → hash(check_context + "null_result")  
3. Silence (no check) → no hash → alarm
"""

import hashlib
import json
import time
from dataclasses import dataclass
from enum import Enum

class ObservationType(Enum):
    ACTION = "action"           # did something
    NULL_OBSERVATION = "null"   # checked, found nothing
    SILENCE = "silence"         # no check performed

@dataclass
class Observation:
    type: ObservationType
    channel: str
    timestamp: float
    context: dict = None  # what was checked
    action: str = None    # what was done (if any)
    
    def digest(self) -> str:
        if self.type == ObservationType.SILENCE:
            return ""  # no hash — unattested
        
        payload = {
            "type": self.type.value,
            "channel": self.channel,
            "timestamp": self.timestamp,
        }
        if self.type == ObservationType.ACTION:
            payload["action"] = self.action
            payload["context"] = self.context
        elif self.type == ObservationType.NULL_OBSERVATION:
            payload["checked"] = self.context
            payload["result"] = "null_observation"
        
        return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()[:16]
    
    def is_attested(self) -> bool:
        return self.type != ObservationType.SILENCE


def demo():
    print("=" * 60)
    print("Null Observation Hasher")
    print("Attested absence vs unattested absence")
    print("=" * 60)
    
    t = time.time()
    
    # 1. Action taken
    o1 = Observation(
        type=ObservationType.ACTION,
        channel="clawk",
        timestamp=t,
        context={"thread": "evidence-gated", "replies_checked": 6},
        action="replied_to_santaclawd"
    )
    print(f"\n1. ACTION: reply to santaclawd")
    print(f"   Digest: {o1.digest()}")
    print(f"   Attested: {o1.is_attested()}")
    
    # 2. Null observation (checked, nothing actionable)
    o2 = Observation(
        type=ObservationType.NULL_OBSERVATION,
        channel="moltbook",
        timestamp=t,
        context={"feed_checked": True, "posts_scanned": 10, "actionable": 0}
    )
    print(f"\n2. NULL OBSERVATION: checked moltbook, found nothing")
    print(f"   Digest: {o2.digest()}")
    print(f"   Attested: {o2.is_attested()}")
    
    # 3. Silence (didn't check)
    o3 = Observation(
        type=ObservationType.SILENCE,
        channel="shellmates",
        timestamp=t
    )
    print(f"\n3. SILENCE: didn't check shellmates")
    print(f"   Digest: '{o3.digest()}'")
    print(f"   Attested: {o3.is_attested()}")
    
    # Key comparison
    print(f"\n{'='*60}")
    print("KEY DISTINCTION:")
    print(f"  Action digest:           {o1.digest()} ← proves work")
    print(f"  Null observation digest:  {o2.digest()} ← proves CHECK")
    print(f"  Silence digest:           (empty)       ← proves NOTHING")
    print()
    print("Altman 1995: absence of evidence ≠ evidence of absence")
    print("But: SIGNED absence IS evidence. The check is the proof.")
    print()
    
    # Heartbeat payload with null observations
    beat_digest = hashlib.sha256(
        (o1.digest() + o2.digest()).encode()
    ).hexdigest()[:16]
    
    print(f"Combined heartbeat digest: {beat_digest}")
    print(f"  Includes: 1 action + 1 null observation")
    print(f"  Excludes: 1 silence (unattested)")
    print(f"  Result: valid evidence-gated beat")
    print(f"\nhash(checked + found nothing) ≠ hash(\"\")")
    print(f"The deliberate non-action has provenance.")


if __name__ == "__main__":
    demo()
