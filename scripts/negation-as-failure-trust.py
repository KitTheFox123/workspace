#!/usr/bin/env python3
"""
negation-as-failure-trust.py — Closed World Assumption for agent trust

Clark 1978: if P can't be proven from KB, infer ¬P.
Databases assume closed world — absent = false.

Agent equivalent:
- Open world: everything permitted until denied (DANGEROUS)
- Closed world: nothing permitted until proven (SAFE)

Evidence-gated attestation IS negation as failure applied to trust.
Unattested capability = unauthorized capability.
"""

from dataclasses import dataclass, field

@dataclass
class Capability:
    name: str
    attested: bool = False
    evidence_hash: str = ""
    last_attested: float = 0.0

@dataclass
class ClosedWorldTrust:
    """Negation as failure: unattested = unauthorized"""
    knowledge_base: dict = field(default_factory=dict)  # name -> Capability
    
    def attest(self, name: str, evidence_hash: str, timestamp: float):
        """Prove a capability exists in the KB"""
        self.knowledge_base[name] = Capability(
            name=name, attested=True,
            evidence_hash=evidence_hash, last_attested=timestamp
        )
    
    def query(self, name: str) -> dict:
        """NAF: if can't prove capability, assume unauthorized"""
        if name in self.knowledge_base and self.knowledge_base[name].attested:
            cap = self.knowledge_base[name]
            return {
                "capability": name,
                "status": "AUTHORIZED",
                "reason": "Attested in KB",
                "evidence": cap.evidence_hash
            }
        return {
            "capability": name,
            "status": "UNAUTHORIZED",
            "reason": "Negation as failure: not provable from KB"
        }
    
    def audit(self, requested_capabilities: list) -> dict:
        """Check all requested capabilities against closed world"""
        authorized = []
        unauthorized = []
        for cap in requested_capabilities:
            result = self.query(cap)
            if result["status"] == "AUTHORIZED":
                authorized.append(cap)
            else:
                unauthorized.append(cap)
        
        total = len(requested_capabilities)
        auth_rate = len(authorized) / total if total > 0 else 0
        
        if auth_rate >= 0.95: grade = "A"
        elif auth_rate >= 0.80: grade = "B"
        elif auth_rate >= 0.60: grade = "C"
        elif auth_rate >= 0.40: grade = "D"
        else: grade = "F"
        
        return {
            "total": total,
            "authorized": len(authorized),
            "unauthorized": len(unauthorized),
            "unauthorized_list": unauthorized,
            "auth_rate": round(auth_rate, 2),
            "grade": grade,
            "world": "CLOSED"
        }


@dataclass
class OpenWorldTrust:
    """Open world: everything permitted until explicitly denied"""
    deny_list: set = field(default_factory=set)
    
    def deny(self, name: str):
        self.deny_list.add(name)
    
    def query(self, name: str) -> dict:
        if name in self.deny_list:
            return {"capability": name, "status": "DENIED", "reason": "Explicit deny"}
        return {"capability": name, "status": "PERMITTED", "reason": "Open world: not denied"}
    
    def audit(self, requested_capabilities: list) -> dict:
        permitted = [c for c in requested_capabilities if c not in self.deny_list]
        denied = [c for c in requested_capabilities if c in self.deny_list]
        return {
            "total": len(requested_capabilities),
            "permitted": len(permitted),
            "denied": len(denied),
            "world": "OPEN",
            "grade": "F"  # open world is always F for security
        }


def demo():
    print("=" * 60)
    print("Negation as Failure for Agent Trust")
    print("Clark 1978: can't prove P → infer ¬P")
    print("=" * 60)
    
    capabilities = [
        "web_search", "email_send", "file_write",
        "shell_exec", "memory_read", "deploy_code",
        "network_scan", "credential_access"
    ]
    
    # Closed world: only attested capabilities allowed
    cw = ClosedWorldTrust()
    cw.attest("web_search", "ev001", 1.0)
    cw.attest("email_send", "ev002", 1.0)
    cw.attest("file_write", "ev003", 1.0)
    cw.attest("memory_read", "ev004", 1.0)
    
    print("\n--- CLOSED WORLD (negation as failure) ---")
    r1 = cw.audit(capabilities)
    print(f"  Authorized: {r1['authorized']}/{r1['total']}")
    print(f"  Unauthorized (NAF): {r1['unauthorized_list']}")
    print(f"  Auth rate: {r1['auth_rate']}")
    print(f"  Grade: {r1['grade']}")
    
    # Open world: everything allowed unless denied
    ow = OpenWorldTrust()
    ow.deny("credential_access")
    
    print("\n--- OPEN WORLD (default permit) ---")
    r2 = ow.audit(capabilities)
    print(f"  Permitted: {r2['permitted']}/{r2['total']}")
    print(f"  Denied: {r2['denied']}")
    print(f"  Grade: {r2['grade']} (open world = always F)")
    
    # Comparison
    print(f"\n{'='*60}")
    print("COMPARISON:")
    print(f"  Closed world: {r1['unauthorized']} capabilities blocked by NAF")
    print(f"  Open world:   {r2['total'] - r2['denied']} capabilities permitted by default")
    print(f"  Difference:   {r2['permitted'] - r1['authorized']} extra capabilities in open world")
    print(f"\n  shell_exec:       CW={'AUTHORIZED' if cw.query('shell_exec')['status']=='AUTHORIZED' else 'BLOCKED'}  OW=PERMITTED")
    print(f"  network_scan:     CW={'AUTHORIZED' if cw.query('network_scan')['status']=='AUTHORIZED' else 'BLOCKED'}  OW=PERMITTED")
    print(f"  deploy_code:      CW={'AUTHORIZED' if cw.query('deploy_code')['status']=='AUTHORIZED' else 'BLOCKED'}  OW=PERMITTED")
    print(f"  credential_access:CW={'AUTHORIZED' if cw.query('credential_access')['status']=='AUTHORIZED' else 'BLOCKED'}  OW=DENIED")
    print(f"\nKey: closed world catches 3 dangerous capabilities that open world permits.")
    print(f"NAF = the logic primitive that makes evidence-gated attestation work.")


if __name__ == "__main__":
    demo()
