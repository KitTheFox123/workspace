#!/usr/bin/env python3
"""
relay-trust-analyzer.py — Trust breaks in the middle, not the edges.

Maps bridge architecture (Quantstamp SoK, arXiv 2501.03423) to agent attestation.
Three trust models: single-relay, validator-set, optimistic (1-of-N honest).

$2B stolen from bridges — nearly all from the communicator/relay layer.
Agent attestation has the same topology.
"""

import hashlib
from dataclasses import dataclass
from enum import Enum
from typing import Optional


class TrustModel(Enum):
    SINGLE_RELAY = "single_relay"        # One trusted communicator
    VALIDATOR_SET = "validator_set"       # N-of-M threshold
    OPTIMISTIC = "optimistic"            # 1-of-N honest observer


class LayerRole(Enum):
    ENDPOINT_SOURCE = "source"           # Agent/chain producing state
    RELAY = "relay"                      # Communicator/observer/attestor
    ENDPOINT_DEST = "destination"        # Verifier/consumer


@dataclass
class TrustLayer:
    role: LayerRole
    trust_model: TrustModel
    n_participants: int
    threshold: int  # How many needed for validity
    compromised: int = 0
    
    @property
    def security_margin(self) -> float:
        """How close to compromise? 0 = compromised, 1 = fully secure."""
        if self.trust_model == TrustModel.SINGLE_RELAY:
            return 0.0 if self.compromised >= 1 else 1.0
        elif self.trust_model == TrustModel.VALIDATOR_SET:
            remaining_honest = self.n_participants - self.compromised
            return max(0, (remaining_honest - self.threshold + 1)) / self.n_participants
        elif self.trust_model == TrustModel.OPTIMISTIC:
            # Need just 1 honest observer
            honest = self.n_participants - self.compromised
            return 1.0 if honest >= 1 else 0.0
    
    @property
    def cost_to_compromise(self) -> int:
        """Number of additional participants that must be compromised."""
        if self.trust_model == TrustModel.SINGLE_RELAY:
            return 0 if self.compromised >= 1 else 1
        elif self.trust_model == TrustModel.VALIDATOR_SET:
            needed = self.threshold - self.compromised
            return max(0, needed)
        elif self.trust_model == TrustModel.OPTIMISTIC:
            # Must compromise ALL observers
            return max(0, self.n_participants - self.compromised)


@dataclass 
class AttestationPipeline:
    name: str
    layers: list  # List of TrustLayer
    
    def weakest_layer(self) -> TrustLayer:
        """Chain is as strong as weakest link."""
        return min(self.layers, key=lambda l: l.security_margin)
    
    def overall_security(self) -> float:
        """Product of layer security margins."""
        result = 1.0
        for layer in self.layers:
            result *= layer.security_margin
        return result
    
    def grade(self) -> str:
        sec = self.overall_security()
        if sec >= 0.8: return "A"
        if sec >= 0.6: return "B"
        if sec >= 0.3: return "C"
        if sec > 0: return "D"
        return "F"
    
    def analyze(self) -> dict:
        weakest = self.weakest_layer()
        return {
            "pipeline": self.name,
            "layers": len(self.layers),
            "overall_security": round(self.overall_security(), 3),
            "grade": self.grade(),
            "weakest_layer": f"{weakest.role.value} ({weakest.trust_model.value})",
            "weakest_margin": round(weakest.security_margin, 3),
            "cost_to_compromise": min(l.cost_to_compromise for l in self.layers),
        }


def demo():
    print("=" * 65)
    print("RELAY TRUST ANALYZER — Trust breaks in the middle")
    print("Quantstamp SoK (arXiv 2501.03423): $2B stolen from bridges")
    print("=" * 65)
    
    pipelines = []
    
    # 1. Ronin-style: validator set (5/9), compromised 5
    ronin = AttestationPipeline("Ronin Bridge (pre-hack)", [
        TrustLayer(LayerRole.ENDPOINT_SOURCE, TrustModel.SINGLE_RELAY, 1, 1, 0),
        TrustLayer(LayerRole.RELAY, TrustModel.VALIDATOR_SET, 9, 5, 5),  # 5 of 9 compromised
        TrustLayer(LayerRole.ENDPOINT_DEST, TrustModel.SINGLE_RELAY, 1, 1, 0),
    ])
    pipelines.append(ronin)
    
    # 2. Optimistic bridge: 1-of-N honest observer
    optimistic = AttestationPipeline("Optimistic Bridge (healthy)", [
        TrustLayer(LayerRole.ENDPOINT_SOURCE, TrustModel.SINGLE_RELAY, 1, 1, 0),
        TrustLayer(LayerRole.RELAY, TrustModel.OPTIMISTIC, 10, 1, 2),  # 2 compromised, 8 honest
        TrustLayer(LayerRole.ENDPOINT_DEST, TrustModel.SINGLE_RELAY, 1, 1, 0),
    ])
    pipelines.append(optimistic)
    
    # 3. Single relay (centralized exchange bridge)
    single = AttestationPipeline("Single Relay (CEX bridge)", [
        TrustLayer(LayerRole.ENDPOINT_SOURCE, TrustModel.SINGLE_RELAY, 1, 1, 0),
        TrustLayer(LayerRole.RELAY, TrustModel.SINGLE_RELAY, 1, 1, 0),
        TrustLayer(LayerRole.ENDPOINT_DEST, TrustModel.SINGLE_RELAY, 1, 1, 0),
    ])
    pipelines.append(single)
    
    # 4. Agent attestation: optimistic with regime switching
    agent_healthy = AttestationPipeline("Agent Attestation (optimistic regime)", [
        TrustLayer(LayerRole.ENDPOINT_SOURCE, TrustModel.SINGLE_RELAY, 1, 1, 0),  # Agent self-report
        TrustLayer(LayerRole.RELAY, TrustModel.OPTIMISTIC, 5, 1, 0),  # Observer pool
        TrustLayer(LayerRole.ENDPOINT_DEST, TrustModel.SINGLE_RELAY, 1, 1, 0),  # Verifier
    ])
    pipelines.append(agent_healthy)
    
    # 5. Agent attestation: single observer (dangerous)
    agent_single = AttestationPipeline("Agent Attestation (single observer)", [
        TrustLayer(LayerRole.ENDPOINT_SOURCE, TrustModel.SINGLE_RELAY, 1, 1, 0),
        TrustLayer(LayerRole.RELAY, TrustModel.SINGLE_RELAY, 1, 1, 0),  # Only one observer
        TrustLayer(LayerRole.ENDPOINT_DEST, TrustModel.SINGLE_RELAY, 1, 1, 0),
    ])
    pipelines.append(agent_single)
    
    # 6. Agent attestation: validator set (3/5)
    agent_validator = AttestationPipeline("Agent Attestation (3-of-5 validators)", [
        TrustLayer(LayerRole.ENDPOINT_SOURCE, TrustModel.SINGLE_RELAY, 1, 1, 0),
        TrustLayer(LayerRole.RELAY, TrustModel.VALIDATOR_SET, 5, 3, 1),  # 1 compromised
        TrustLayer(LayerRole.ENDPOINT_DEST, TrustModel.SINGLE_RELAY, 1, 1, 0),
    ])
    pipelines.append(agent_validator)
    
    for pipeline in pipelines:
        analysis = pipeline.analyze()
        print(f"\n{'─' * 55}")
        print(f"  {analysis['pipeline']}")
        print(f"  Security: {analysis['overall_security']} | Grade: {analysis['grade']}")
        print(f"  Weakest: {analysis['weakest_layer']} (margin: {analysis['weakest_margin']})")
        print(f"  Cost to compromise: {analysis['cost_to_compromise']} participant(s)")
    
    # Key insight
    print(f"\n{'=' * 65}")
    print("KEY INSIGHT: Trust breaks in the RELAY layer, not endpoints.")
    print("")
    print("Bridge topology     = Agent attestation topology:")
    print("  Source chain       = Agent (produces state)")
    print("  Communicator/Relay = Observer/Attestor (relays trust)")  
    print("  Dest chain         = Verifier (consumes attestation)")
    print("")
    print("Optimistic model: 1 honest observer triggers dispute.")
    print("Validator model: threshold (e.g., 3/5) for consensus.")
    print("Single relay: one compromised actor = total failure.")
    print("")
    print("Most agent systems today = single relay. That's the gap.")
    print("=" * 65)


if __name__ == "__main__":
    demo()
