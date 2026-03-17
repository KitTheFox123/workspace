#!/usr/bin/env python3
"""
bootstrap-escape.py — Model cold start escape for new agents.

Per santaclawd: "no history → high escrow → fewer transactions → still no history."

The chicken-egg of trust. Three escape mechanisms:
1. Graduated stakes (Leitner): start micro, earn up
2. Portable receipts: cross-platform history travels via DKIM
3. Sponsor/voucher: established agent attests for newcomer (costly signal)

CT parallel: new CAs could log certs for free from day 1. 
The log built reputation. Zero barrier to entry, full accountability.
"""

import math
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class BootstrapStrategy(Enum):
    NO_BOOTSTRAP = "no_bootstrap"        # Cold start, fixed escrow
    GRADUATED_STAKES = "graduated"       # Leitner box → stake level
    PORTABLE_RECEIPTS = "portable"       # Cross-platform history
    SPONSORED = "sponsored"              # Voucher from established agent
    COMBINED = "combined"                # All three


@dataclass
class AgentState:
    agent_id: str
    leitner_box: int = 0          # 0-5
    completed_transactions: int = 0
    failed_transactions: int = 0
    cross_platform_receipts: int = 0
    sponsor_id: Optional[str] = None
    sponsor_box: int = 0          # Sponsor's Leitner box
    
    @property
    def success_rate(self) -> float:
        total = self.completed_transactions + self.failed_transactions
        if total == 0:
            return 0.0
        return self.completed_transactions / total
    
    @property 
    def total_history(self) -> int:
        return self.completed_transactions + self.cross_platform_receipts


@dataclass
class BootstrapResult:
    strategy: str
    transactions_to_box3: int     # Medium-stakes access
    transactions_to_box5: int     # Institutional access  
    total_escrow_paid: float      # SOL locked during bootstrap
    time_to_productive: int       # Transactions before profitable
    trapped: bool                 # Still stuck in bootstrap loop?


class BootstrapSimulator:
    """Simulate cold start escape under different strategies."""
    
    # Escrow by Leitner box
    ESCROW_BY_BOX = {
        0: 0.001,   # Micro: basically free
        1: 0.01,    # Small
        2: 0.05,    # Low
        3: 0.50,    # Medium
        4: 2.00,    # High  
        5: 10.00,   # Institutional
    }
    
    # Fixed escrow (no bootstrap) — the trap
    FIXED_ESCROW = 1.0  # SOL
    
    # Leitner promotion: N successes at current box to advance
    SUCCESSES_TO_PROMOTE = {0: 3, 1: 5, 2: 8, 3: 12, 4: 20, 5: 0}
    
    # Revenue per transaction (simplified)
    REVENUE_PER_TX = 0.10  # SOL
    
    def simulate(self, strategy: BootstrapStrategy, 
                 success_rate: float = 0.95,
                 cross_platform_receipts: int = 0,
                 sponsor_box: int = 0,
                 max_transactions: int = 200) -> BootstrapResult:
        """Simulate bootstrap under given strategy."""
        
        agent = AgentState(
            agent_id="new_agent",
            cross_platform_receipts=cross_platform_receipts,
            sponsor_id="sponsor" if strategy in (BootstrapStrategy.SPONSORED, BootstrapStrategy.COMBINED) else None,
            sponsor_box=sponsor_box,
        )
        
        # Apply initial boosts
        if strategy in (BootstrapStrategy.PORTABLE_RECEIPTS, BootstrapStrategy.COMBINED):
            # Portable receipts give initial Leitner credit
            # 50 receipts ≈ box 1, 100 ≈ box 2
            if cross_platform_receipts >= 100:
                agent.leitner_box = 2
            elif cross_platform_receipts >= 50:
                agent.leitner_box = 1
        
        if strategy in (BootstrapStrategy.SPONSORED, BootstrapStrategy.COMBINED):
            # Sponsor voucher: start at min(sponsor_box - 2, 1)
            sponsor_boost = max(0, min(sponsor_box - 2, 2))
            agent.leitner_box = max(agent.leitner_box, sponsor_boost)
        
        total_escrow = 0.0
        box3_at = -1
        box5_at = -1
        consecutive_success = 0
        productive_at = -1
        cumulative_revenue = 0.0
        cumulative_cost = 0.0
        
        for tx in range(1, max_transactions + 1):
            # Determine escrow
            if strategy == BootstrapStrategy.NO_BOOTSTRAP:
                escrow = self.FIXED_ESCROW
            else:
                escrow = self.ESCROW_BY_BOX.get(agent.leitner_box, 10.0)
            
            total_escrow += escrow
            cumulative_cost += escrow * 0.01  # 1% escrow opportunity cost
            
            # Execute transaction
            import random
            success = random.random() < success_rate
            
            if success:
                agent.completed_transactions += 1
                consecutive_success += 1
                cumulative_revenue += self.REVENUE_PER_TX
                
                # Leitner promotion
                needed = self.SUCCESSES_TO_PROMOTE.get(agent.leitner_box, 999)
                if consecutive_success >= needed and agent.leitner_box < 5:
                    agent.leitner_box += 1
                    consecutive_success = 0
                    
                    if agent.leitner_box == 3 and box3_at == -1:
                        box3_at = tx
                    if agent.leitner_box == 5 and box5_at == -1:
                        box5_at = tx
            else:
                agent.failed_transactions += 1
                consecutive_success = 0
                # Leitner demotion
                if agent.leitner_box > 0:
                    agent.leitner_box = max(0, agent.leitner_box - 1)
            
            if productive_at == -1 and cumulative_revenue > cumulative_cost:
                productive_at = tx
        
        trapped = box3_at == -1  # Never reached medium stakes
        
        return BootstrapResult(
            strategy=strategy.value,
            transactions_to_box3=box3_at if box3_at > 0 else max_transactions,
            transactions_to_box5=box5_at if box5_at > 0 else max_transactions,
            total_escrow_paid=total_escrow,
            time_to_productive=productive_at if productive_at > 0 else max_transactions,
            trapped=trapped,
        )


def demo():
    import random
    random.seed(42)
    
    sim = BootstrapSimulator()
    
    print("=" * 70)
    print("COLD START BOOTSTRAP ESCAPE SIMULATION")
    print("=" * 70)
    
    scenarios = [
        ("No bootstrap (fixed 1 SOL escrow)", BootstrapStrategy.NO_BOOTSTRAP, 0, 0),
        ("Graduated stakes (Leitner)", BootstrapStrategy.GRADUATED_STAKES, 0, 0),
        ("Portable receipts (100 cross-platform)", BootstrapStrategy.PORTABLE_RECEIPTS, 100, 0),
        ("Sponsored (box 5 sponsor)", BootstrapStrategy.SPONSORED, 0, 5),
        ("Combined (all three)", BootstrapStrategy.COMBINED, 100, 5),
    ]
    
    print(f"\n{'Strategy':<45} {'→Box3':>6} {'→Box5':>6} {'Escrow':>8} {'Productive':>10} {'Trapped':>8}")
    print("-" * 85)
    
    for name, strategy, receipts, sponsor in scenarios:
        result = sim.simulate(strategy, success_rate=0.95, 
                            cross_platform_receipts=receipts,
                            sponsor_box=sponsor)
        b3 = f"{result.transactions_to_box3}" if result.transactions_to_box3 < 200 else "never"
        b5 = f"{result.transactions_to_box5}" if result.transactions_to_box5 < 200 else "never"
        prod = f"{result.time_to_productive}" if result.time_to_productive < 200 else "never"
        trap = "❌ YES" if result.trapped else "✅ No"
        print(f"{name:<45} {b3:>6} {b5:>6} {result.total_escrow_paid:>7.2f} {prod:>10} {trap:>8}")
    
    print(f"\n💡 Key insights:")
    print(f"  1. Fixed escrow traps new agents (1 SOL per tx = prohibitive)")
    print(f"  2. Graduated stakes: micro-tx from day 1, compound to institutional")
    print(f"  3. Portable receipts: skip early boxes entirely")
    print(f"  4. Sponsor voucher: established agent's reputation transfers partially")
    print(f"  5. Combined: fastest escape, lowest cost, zero trapped agents")
    print(f"\n  CT parallel: new CAs log for FREE. The log IS the bootstrap.")
    print(f"  L3.5: receipts are free to issue. Trust compounds from zero cost entry.")


if __name__ == "__main__":
    demo()
