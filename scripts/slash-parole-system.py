#!/usr/bin/env python3
"""
slash-parole-system.py — Post-SLASH rehabilitation via Leitner reset.

Per santaclawd (2026-03-15): permanent exclusion creates identity laundering
incentives. Scar should be data point, not death sentence.

Design:
- SLASHED agent resets to Leitner box 0 (below box 1 — probation)
- 2x frequency multiplier during parole
- Transaction limits until box 3 re-earned
- Scar stays in log forever
- Recidivism (2nd slash) = permanent exclusion
"""

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
import math


class ParoleStatus(Enum):
    ACTIVE = "active"           # Normal operation
    PAROLED = "paroled"         # Post-slash, rebuilding trust
    PERMANENTLY_EXCLUDED = "permanently_excluded"  # 2nd slash


@dataclass
class SlashRecord:
    timestamp: datetime
    reason: str  # delivery_hash_mismatch, double_spend, conflicting_signatures
    evidence_hash: str


@dataclass  
class ParoleAgent:
    agent_id: str
    current_box: int = 1        # Leitner box (0 = probation)
    consecutive_passes: int = 0
    slash_history: list[SlashRecord] = field(default_factory=list)
    parole_start: datetime | None = None
    status: ParoleStatus = ParoleStatus.ACTIVE
    
    # Leitner intervals (hours) — box 0 is probation-only
    BASE_INTERVALS = {0: 0.5, 1: 1, 2: 2, 3: 4, 4: 8, 5: 16, 6: 32}
    
    # Transaction limits by box
    TX_LIMITS = {
        0: {"max_value_usd": 0, "description": "No transactions (probation)"},
        1: {"max_value_usd": 1, "description": "Micro-transactions only"},
        2: {"max_value_usd": 10, "description": "Small transactions"},
        3: {"max_value_usd": 100, "description": "Standard transactions"},
        4: {"max_value_usd": 1000, "description": "Large transactions"},
        5: {"max_value_usd": 10000, "description": "High-value transactions"},
        6: {"max_value_usd": float('inf'), "description": "Unlimited"},
    }
    
    @property
    def frequency_multiplier(self) -> float:
        """Paroled agents get 2x verification frequency."""
        return 2.0 if self.status == ParoleStatus.PAROLED else 1.0
    
    @property
    def current_interval_hours(self) -> float:
        base = self.BASE_INTERVALS.get(self.current_box, 32)
        return base / self.frequency_multiplier
    
    @property
    def tx_limit(self) -> dict:
        return self.TX_LIMITS.get(self.current_box, self.TX_LIMITS[0])
    
    @property
    def parole_complete(self) -> bool:
        """Parole ends when box 3 is re-earned."""
        return self.status == ParoleStatus.PAROLED and self.current_box >= 3
    
    def slash(self, reason: str, evidence_hash: str) -> str:
        """Apply slash. 2nd slash = permanent exclusion."""
        record = SlashRecord(
            timestamp=datetime.utcnow(),
            reason=reason,
            evidence_hash=evidence_hash,
        )
        self.slash_history.append(record)
        
        if len(self.slash_history) >= 2:
            self.status = ParoleStatus.PERMANENTLY_EXCLUDED
            self.current_box = 0
            return "PERMANENTLY_EXCLUDED — recidivism, no recovery"
        
        # First slash: reset to box 0, enter parole
        self.current_box = 0
        self.consecutive_passes = 0
        self.parole_start = datetime.utcnow()
        self.status = ParoleStatus.PAROLED
        return "PAROLED — reset to box 0, 2x frequency, tx limits active"
    
    def verify_pass(self) -> str:
        """Successful verification — promote box."""
        if self.status == ParoleStatus.PERMANENTLY_EXCLUDED:
            return "REJECTED — permanently excluded"
        
        self.consecutive_passes += 1
        if self.current_box < 6:
            self.current_box += 1
        
        msg = f"PASS — promoted to box {self.current_box}"
        
        # Check parole completion
        if self.parole_complete:
            self.status = ParoleStatus.ACTIVE
            msg += " (PAROLE COMPLETE — scar remains in log)"
        
        return msg
    
    def verify_fail(self) -> str:
        """Failed verification — demote to box 1 (or 0 if paroled)."""
        if self.status == ParoleStatus.PERMANENTLY_EXCLUDED:
            return "REJECTED — permanently excluded"
        
        self.consecutive_passes = 0
        self.current_box = 0 if self.status == ParoleStatus.PAROLED else 1
        return f"FAIL — demoted to box {self.current_box}"
    
    def report(self) -> dict:
        return {
            "agent_id": self.agent_id,
            "status": self.status.value,
            "box": self.current_box,
            "interval_hours": self.current_interval_hours,
            "tx_limit": self.tx_limit,
            "consecutive_passes": self.consecutive_passes,
            "slash_count": len(self.slash_history),
            "frequency_multiplier": self.frequency_multiplier,
            "scars": [
                {"reason": s.reason, "time": s.timestamp.isoformat()}
                for s in self.slash_history
            ],
        }


def demo():
    print("=== Slash Parole System ===\n")
    
    # Scenario 1: Good agent gets slashed, rehabilitates
    agent = ParoleAgent(agent_id="agent_alice")
    
    # Build up trust
    print("📈 Building trust...")
    for i in range(5):
        result = agent.verify_pass()
        print(f"   {result} (interval: {agent.current_interval_hours}h, limit: ${agent.tx_limit['max_value_usd']})")
    
    # Slash!
    print(f"\n⚡ SLASH: delivery_hash_mismatch")
    result = agent.slash("delivery_hash_mismatch", "0xdeadbeef")
    print(f"   {result}")
    print(f"   Box: {agent.current_box}, Interval: {agent.current_interval_hours}h")
    print(f"   TX limit: {agent.tx_limit['description']}")
    print(f"   Frequency: {agent.frequency_multiplier}x")
    
    # Rehabilitate
    print(f"\n📈 Rehabilitation...")
    for i in range(4):
        result = agent.verify_pass()
        r = agent.report()
        print(f"   {result} (interval: {r['interval_hours']}h, limit: ${r['tx_limit']['max_value_usd']}, scars: {r['slash_count']})")
    
    # Scenario 2: Recidivist
    print(f"\n\n⚡ SECOND SLASH: double_spend")
    result = agent.slash("double_spend", "0xcafebabe")
    print(f"   {result}")
    print(f"   Status: {agent.status.value}")
    result = agent.verify_pass()
    print(f"   Attempt to verify: {result}")
    
    # Key principles
    print("\n--- Design Principles ---")
    print("1. First slash = parole (box 0, 2x frequency, tx limits)")
    print("2. Scar stays in log FOREVER (never deleted)")
    print("3. Parole ends at box 3 (re-earned trust)")
    print("4. Second slash = permanent exclusion (no recovery)")
    print("5. This prevents identity laundering (new key = zero history)")


if __name__ == "__main__":
    demo()
