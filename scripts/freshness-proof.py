#!/usr/bin/env python3
"""
freshness-proof.py — Prove you saw something NEW

funwolf: "stale context = stale attestation. email threads have this built in —
you can't reply to a message that doesn't exist yet."

TLS session tickets pattern: replay protection via nonce.
Agent version: heartbeat includes hash of most recent EXTERNAL state.
Can't fake what hasn't happened yet.

External anchors:
- Latest feed post ID (platform-written)
- Inbox message count (infrastructure-witnessed)
- Block height (consensus-verified)
- SMTP timestamp (third-party)
"""

import hashlib
import json
import time
from dataclasses import dataclass, field

@dataclass
class ExternalAnchor:
    """Something the agent couldn't have known before checking"""
    source: str           # e.g. "clawk_feed", "email_inbox", "block_height"
    value: str            # the external state
    timestamp: float      # when observed
    
    @property
    def anchor_hash(self) -> str:
        return hashlib.sha256(f"{self.source}:{self.value}:{self.timestamp}".encode()).hexdigest()[:12]


@dataclass
class FreshnessProof:
    """Heartbeat payload with external anchors proving recency"""
    agent_id: str
    anchors: list = field(default_factory=list)  # ExternalAnchor list
    observation_hash: str = ""
    
    def add_anchor(self, source: str, value: str, timestamp: float = None):
        self.anchors.append(ExternalAnchor(source, value, timestamp or time.time()))
    
    def sign(self) -> dict:
        anchor_data = [{"source": a.source, "value": a.value, "hash": a.anchor_hash} for a in self.anchors]
        payload = json.dumps({"agent": self.agent_id, "anchors": anchor_data}, sort_keys=True)
        self.observation_hash = hashlib.sha256(payload.encode()).hexdigest()[:16]
        return {
            "agent": self.agent_id,
            "anchors": anchor_data,
            "proof_hash": self.observation_hash,
            "anchor_count": len(self.anchors)
        }


@dataclass
class FreshnessVerifier:
    """Verify freshness proofs aren't stale or replayed"""
    seen_anchors: dict = field(default_factory=dict)  # source → last value
    seen_proofs: set = field(default_factory=set)      # replay detection
    min_anchors: int = 2                                # minimum external anchors
    
    def verify(self, proof: dict) -> dict:
        result = {"checks": [], "verdict": "UNKNOWN", "grade": "F"}
        
        # Check 1: Replay detection
        if proof["proof_hash"] in self.seen_proofs:
            result["checks"].append({"check": "replay", "status": "FAIL", "detail": "Exact proof seen before"})
            result["verdict"] = "REPLAY"
            return result
        self.seen_proofs.add(proof["proof_hash"])
        result["checks"].append({"check": "replay", "status": "PASS"})
        
        # Check 2: Minimum anchors
        if proof["anchor_count"] < self.min_anchors:
            result["checks"].append({"check": "anchor_count", "status": "FAIL", 
                                      "detail": f"{proof['anchor_count']} < {self.min_anchors} minimum"})
            result["verdict"] = "INSUFFICIENT"
            result["grade"] = "D"
            return result
        result["checks"].append({"check": "anchor_count", "status": "PASS", "count": proof["anchor_count"]})
        
        # Check 3: Freshness (anchor values must change)
        stale_count = 0
        for anchor in proof["anchors"]:
            src = anchor["source"]
            if src in self.seen_anchors and self.seen_anchors[src] == anchor["value"]:
                stale_count += 1
                result["checks"].append({"check": f"fresh_{src}", "status": "STALE", "detail": "Same value as last proof"})
            else:
                result["checks"].append({"check": f"fresh_{src}", "status": "FRESH"})
            self.seen_anchors[src] = anchor["value"]
        
        fresh_ratio = 1 - (stale_count / max(len(proof["anchors"]), 1))
        
        if fresh_ratio >= 0.5:
            result["verdict"] = "FRESH"
            result["grade"] = "A" if fresh_ratio == 1.0 else "B"
        else:
            result["verdict"] = "STALE"
            result["grade"] = "D"
        
        result["fresh_ratio"] = round(fresh_ratio, 2)
        return result


def demo():
    print("=" * 60)
    print("Freshness Proof — Prove You Saw Something NEW")
    print("Can't fake what hasn't happened yet")
    print("=" * 60)
    
    verifier = FreshnessVerifier()
    t = time.time()
    
    # Proof 1: fresh anchors
    fp1 = FreshnessProof(agent_id="kit_fox")
    fp1.add_anchor("clawk_latest_post", "abc123", t)
    fp1.add_anchor("email_inbox_count", "47", t)
    fp1.add_anchor("moltbook_feed_hash", "def456", t)
    signed1 = fp1.sign()
    r1 = verifier.verify(signed1)
    print(f"\n1. FRESH PROOF: {r1['verdict']} (Grade {r1['grade']})")
    for c in r1["checks"]:
        print(f"   {c['check']}: {c['status']}")
    
    # Proof 2: some stale anchors
    fp2 = FreshnessProof(agent_id="kit_fox")
    fp2.add_anchor("clawk_latest_post", "ghi789", t + 1200)  # new
    fp2.add_anchor("email_inbox_count", "47", t + 1200)       # stale
    fp2.add_anchor("moltbook_feed_hash", "jkl012", t + 1200)  # new
    signed2 = fp2.sign()
    r2 = verifier.verify(signed2)
    print(f"\n2. MOSTLY FRESH: {r2['verdict']} (Grade {r2['grade']}, fresh: {r2['fresh_ratio']})")
    
    # Proof 3: replay attempt
    r3 = verifier.verify(signed1)
    print(f"\n3. REPLAY ATTEMPT: {r3['verdict']} (Grade {r3['grade']})")
    
    # Proof 4: insufficient anchors
    fp4 = FreshnessProof(agent_id="kit_fox")
    fp4.add_anchor("clawk_latest_post", "mno345", t + 2400)
    signed4 = fp4.sign()
    r4 = verifier.verify(signed4)
    print(f"\n4. INSUFFICIENT ANCHORS: {r4['verdict']} (Grade {r4['grade']})")
    
    print(f"\n{'='*60}")
    print("External anchors = proof of recency.")
    print("Latest post ID, inbox count, block height — all platform-written.")
    print("TLS nonce pattern: can't replay what's already been seen.")


if __name__ == "__main__":
    demo()
