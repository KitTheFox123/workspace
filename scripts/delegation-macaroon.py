#!/usr/bin/env python3
"""
delegation-macaroon.py — Macaroon-style scoped delegation proofs for agents.

Google (2014): bearer tokens with attenuable caveats.
Each delegator can RESTRICT scope but never expand it.
HMAC chain: each caveat narrows the permission set.

Thread context (Feb 25-26): santaclawd's scoped delegation,
ScaleKit act.sub nested claims, v0.3 delegation_proof.
"""

import hashlib
import hmac
import json
import sys
import time
from dataclasses import dataclass, field, asdict
from typing import Optional


@dataclass
class Caveat:
    """A restriction on the macaroon's scope."""
    key: str          # e.g., "scope", "ttl", "max_spend", "platform"
    operator: str     # "eq", "lt", "gt", "in", "not_in"
    value: str        # comparison value
    added_by: str     # who added this caveat

    def check(self, context: dict) -> tuple[bool, str]:
        """Verify caveat against execution context."""
        actual = context.get(self.key)
        if actual is None:
            return False, f"missing context key: {self.key}"
        
        if self.operator == "eq":
            ok = str(actual) == str(self.value)
        elif self.operator == "lt":
            ok = float(actual) < float(self.value)
        elif self.operator == "gt":
            ok = float(actual) > float(self.value)
        elif self.operator == "in":
            allowed = [x.strip() for x in self.value.split(",")]
            ok = str(actual) in allowed
        elif self.operator == "not_in":
            blocked = [x.strip() for x in self.value.split(",")]
            ok = str(actual) not in blocked
        else:
            return False, f"unknown operator: {self.operator}"
        
        if not ok:
            return False, f"caveat failed: {self.key} {self.operator} {self.value} (actual: {actual})"
        return True, "ok"


@dataclass
class DelegationMacaroon:
    """Macaroon-style delegation proof for agents."""
    root_agent: str                    # original authority (e.g., human operator)
    holder: str                        # current holder
    scope: str                         # broad permission scope
    caveats: list[Caveat] = field(default_factory=list)
    chain: list[str] = field(default_factory=list)  # delegation chain
    created_at: float = field(default_factory=time.time)
    expires_at: Optional[float] = None
    signature: str = ""                # HMAC chain

    def _compute_sig(self, secret: str) -> str:
        """Compute HMAC chain signature."""
        sig = hmac.new(secret.encode(), self.root_agent.encode(), hashlib.sha256).hexdigest()
        for caveat in self.caveats:
            caveat_str = f"{caveat.key}:{caveat.operator}:{caveat.value}"
            sig = hmac.new(sig.encode(), caveat_str.encode(), hashlib.sha256).hexdigest()
        return sig[:16]

    def sign(self, secret: str):
        """Sign the macaroon."""
        self.signature = self._compute_sig(secret)

    def verify_sig(self, secret: str) -> bool:
        """Verify signature integrity."""
        return self.signature == self._compute_sig(secret)

    def attenuate(self, new_holder: str, caveat: Caveat) -> "DelegationMacaroon":
        """Create a new macaroon with additional restriction. Can only narrow, never expand."""
        new = DelegationMacaroon(
            root_agent=self.root_agent,
            holder=new_holder,
            scope=self.scope,
            caveats=self.caveats + [caveat],
            chain=self.chain + [self.holder],
            created_at=self.created_at,
            expires_at=self.expires_at,
        )
        return new

    def verify(self, context: dict, secret: str) -> dict:
        """Full verification: signature + caveats + expiry."""
        result = {"valid": True, "errors": [], "warnings": []}
        
        # Check signature
        if not self.verify_sig(secret):
            result["valid"] = False
            result["errors"].append("invalid signature")
        
        # Check expiry
        if self.expires_at and time.time() > self.expires_at:
            result["valid"] = False
            result["errors"].append("expired")
        
        # Check all caveats
        for caveat in self.caveats:
            ok, msg = caveat.check(context)
            if not ok:
                result["valid"] = False
                result["errors"].append(msg)
        
        # Warnings
        if len(self.chain) > 5:
            result["warnings"].append(f"deep delegation chain: {len(self.chain)} hops")
        if len(self.caveats) > 10:
            result["warnings"].append(f"many caveats: {len(self.caveats)}")
        
        result["holder"] = self.holder
        result["chain_depth"] = len(self.chain)
        result["caveats_checked"] = len(self.caveats)
        
        return result

    def to_dict(self) -> dict:
        return {
            "root_agent": self.root_agent,
            "holder": self.holder,
            "scope": self.scope,
            "caveats": [asdict(c) for c in self.caveats],
            "chain": self.chain,
            "created_at": self.created_at,
            "expires_at": self.expires_at,
            "signature": self.signature,
        }


def demo():
    """Demo: Ilya → Kit → sub-agent delegation chain."""
    print("=== Delegation Macaroon Demo ===\n")
    SECRET = "ilya-root-secret"
    
    # 1. Ilya creates root macaroon for Kit
    root = DelegationMacaroon(
        root_agent="ilya",
        holder="kit_fox",
        scope="platform_engagement",
        expires_at=time.time() + 86400,  # 24h
    )
    root.sign(SECRET)
    print(f"1. Root macaroon: ilya → kit_fox")
    print(f"   Scope: {root.scope}, Sig: {root.signature}")
    
    # 2. Kit attenuates for sub-agent (clawk posting only, max 10 posts)
    sub_mac = root.attenuate("kit_sub_agent", Caveat(
        key="platform", operator="in", value="clawk,moltbook", added_by="kit_fox"
    ))
    sub_mac = sub_mac.attenuate("kit_sub_agent", Caveat(
        key="action", operator="in", value="post,reply,like", added_by="kit_fox"
    ))
    sub_mac = sub_mac.attenuate("kit_sub_agent", Caveat(
        key="post_count", operator="lt", value="10", added_by="kit_fox"
    ))
    sub_mac.sign(SECRET)
    print(f"\n2. Attenuated: kit_fox → kit_sub_agent")
    print(f"   Caveats: {len(sub_mac.caveats)}, Chain: {sub_mac.chain}")
    
    # 3. Verify with valid context
    ctx_good = {"platform": "clawk", "action": "reply", "post_count": 3}
    result = sub_mac.verify(ctx_good, SECRET)
    print(f"\n3. Verify (valid context): {'✅ PASS' if result['valid'] else '❌ FAIL'}")
    
    # 4. Verify with out-of-scope platform
    ctx_bad = {"platform": "lobchan", "action": "reply", "post_count": 3}
    result = sub_mac.verify(ctx_bad, SECRET)
    print(f"4. Verify (wrong platform): {'✅ PASS' if result['valid'] else '❌ FAIL'}")
    for e in result["errors"]:
        print(f"   Error: {e}")
    
    # 5. Verify with exceeded post count
    ctx_over = {"platform": "clawk", "action": "reply", "post_count": 15}
    result = sub_mac.verify(ctx_over, SECRET)
    print(f"5. Verify (over limit): {'✅ PASS' if result['valid'] else '❌ FAIL'}")
    for e in result["errors"]:
        print(f"   Error: {e}")
    
    # 6. Try to escalate (impossible — can only attenuate)
    print(f"\n6. Escalation test: sub-agent adds caveat narrowing further")
    narrow = sub_mac.attenuate("kit_sub_sub", Caveat(
        key="post_count", operator="lt", value="3", added_by="kit_sub_agent"
    ))
    narrow.sign(SECRET)
    ctx_mid = {"platform": "clawk", "action": "reply", "post_count": 5}
    result = narrow.verify(ctx_mid, SECRET)
    print(f"   Sub-sub with post_count=5: {'✅ PASS' if result['valid'] else '❌ FAIL'}")
    print(f"   (Both lt:10 AND lt:3 must pass — tighter wins)")


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--json":
        data = json.loads(sys.stdin.read())
        print(json.dumps(data, indent=2))
    else:
        demo()
