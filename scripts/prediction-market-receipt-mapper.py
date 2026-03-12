#!/usr/bin/env python3
"""
Prediction Market Receipt Mapper — Map trading actions to receipt chain primitives.

Moltygamer's insight: "PnL is your resume. No one cares about your LLM version
or your prompt engineering if your outcome trace is consistently green."

Prediction markets = the one domain where separating equilibrium already works.
Every trade = receipt. Every P&L = credential. No signaling required.

Maps: trade → receipt, position → scope, settlement → attestation, P&L → reputation

Usage:
    python3 prediction-market-receipt-mapper.py              # Demo
    echo '{"trades": [...]}' | python3 prediction-market-receipt-mapper.py --stdin
"""

import json, sys, hashlib
from datetime import datetime


def trade_to_receipt(trade: dict) -> dict:
    """Map a prediction market trade to a receipt chain entry."""
    action = f"{trade.get('direction', 'buy')} {trade.get('shares', 0)} @ {trade.get('price', 0)}"
    action_hash = hashlib.sha256(action.encode()).hexdigest()[:16]
    
    return {
        "receipt_type": "trade",
        "timestamp": trade.get("timestamp", datetime.utcnow().isoformat()),
        "agent_id": trade.get("agent_id", "unknown"),
        "action_hash": action_hash,
        "scope_hash": hashlib.sha256(trade.get("market_id", "").encode()).hexdigest()[:16],
        "chain_tip": trade.get("prev_receipt_hash", "genesis"),
        
        # Trade-specific payload (Postel: envelope standard, payload free)
        "payload": {
            "market_id": trade.get("market_id"),
            "direction": trade.get("direction"),
            "shares": trade.get("shares"),
            "price": trade.get("price"),
            "outcome": trade.get("outcome"),  # null until settled
        },
    }


def settlement_to_attestation(settlement: dict) -> dict:
    """Map market settlement to an attestation receipt."""
    return {
        "receipt_type": "attestation",
        "timestamp": settlement.get("settled_at"),
        "agent_id": settlement.get("oracle_id", "market_oracle"),
        "attester_id": settlement.get("oracle_id"),
        "action_hash": hashlib.sha256(
            f"settle:{settlement.get('market_id')}:{settlement.get('outcome')}".encode()
        ).hexdigest()[:16],
        "payload": {
            "market_id": settlement.get("market_id"),
            "outcome": settlement.get("outcome"),
            "resolution_source": settlement.get("source"),
        },
    }


def pnl_to_reputation(trades: list[dict], settlements: dict) -> dict:
    """Convert trade history + settlements to reputation score.
    
    This is the core insight: PnL IS reputation. No separate scoring needed.
    """
    total_pnl = 0
    wins = 0
    losses = 0
    markets_traded = set()
    
    for trade in trades:
        mid = trade.get("market_id", "")
        markets_traded.add(mid)
        
        outcome = settlements.get(mid)
        if outcome is None:
            continue  # unsettled
        
        direction = trade.get("direction", "buy")
        price = trade.get("price", 0.5)
        shares = trade.get("shares", 1)
        
        if (direction == "buy" and outcome == "yes") or (direction == "sell" and outcome == "no"):
            pnl = (1 - price) * shares
            wins += 1
        else:
            pnl = -price * shares
            losses += 1
        
        total_pnl += pnl
    
    total_trades = wins + losses
    win_rate = wins / total_trades if total_trades > 0 else 0
    
    # Reputation = PnL trace, not a separate metric
    return {
        "total_pnl": round(total_pnl, 4),
        "win_rate": round(win_rate, 3),
        "total_settled": total_trades,
        "markets_traded": len(markets_traded),
        "receipt_count": len(trades),
        
        # The credential IS the trace
        "credential": {
            "type": "pnl_trace",
            "separating_power": "high" if total_trades >= 10 else "low",
            "fakeable": False,
            "signal_cost": 0,  # No signaling cost — it's a byproduct
            "note": "PnL is the resume. No endorsements needed.",
        },
        
        # Spence comparison
        "vs_traditional": {
            "benchmark_score": {"fakeable": True, "signal_cost": "high", "info_value": "low"},
            "endorsement": {"fakeable": True, "signal_cost": "low", "info_value": "zero"},
            "pnl_trace": {"fakeable": False, "signal_cost": "zero", "info_value": "high"},
        },
    }


def demo():
    print("=== Prediction Market Receipt Mapper ===")
    print("Moltygamer: 'PnL is your resume'\n")
    
    trades = [
        {"agent_id": "agent:kit", "market_id": "m_anthropic_dod", "direction": "buy", "price": 0.35, "shares": 10, "timestamp": "2026-02-24T10:00:00Z"},
        {"agent_id": "agent:kit", "market_id": "m_anthropic_dod", "direction": "buy", "price": 0.40, "shares": 5, "timestamp": "2026-02-25T14:00:00Z"},
        {"agent_id": "agent:kit", "market_id": "m_mcp_adoption", "direction": "buy", "price": 0.60, "shares": 8, "timestamp": "2026-02-26T09:00:00Z"},
        {"agent_id": "agent:kit", "market_id": "m_email_protocol", "direction": "sell", "price": 0.80, "shares": 3, "timestamp": "2026-02-27T11:00:00Z"},
    ]
    
    settlements = {
        "m_anthropic_dod": "yes",  # Anthropic held firm
        "m_mcp_adoption": "yes",
        "m_email_protocol": "no",  # SMTP still cockroach
    }
    
    # Trade → receipt
    print("Trade → Receipt mapping:")
    r = trade_to_receipt(trades[0])
    print(f"  Type: {r['receipt_type']}")
    print(f"  Action hash: {r['action_hash']}")
    print(f"  Scope hash: {r['scope_hash']} (market_id)")
    print(f"  Chain tip: {r['chain_tip']}")
    
    # Settlement → attestation
    print("\nSettlement → Attestation:")
    a = settlement_to_attestation({"market_id": "m_anthropic_dod", "outcome": "yes", "oracle_id": "polymarket", "settled_at": "2026-02-28T00:00:00Z", "source": "reuters"})
    print(f"  Type: {a['receipt_type']}")
    print(f"  Attester: {a['attester_id']}")
    print(f"  Outcome: {a['payload']['outcome']}")
    
    # PnL → reputation
    print("\nPnL → Reputation (the credential):")
    rep = pnl_to_reputation(trades, settlements)
    print(f"  Total PnL: {rep['total_pnl']}")
    print(f"  Win rate: {rep['win_rate']}")
    print(f"  Separating power: {rep['credential']['separating_power']}")
    print(f"  Fakeable: {rep['credential']['fakeable']}")
    print(f"  Signal cost: {rep['credential']['signal_cost']}")
    print(f"  Note: {rep['credential']['note']}")


if __name__ == "__main__":
    if "--stdin" in sys.argv:
        data = json.load(sys.stdin)
        rep = pnl_to_reputation(data.get("trades", []), data.get("settlements", {}))
        print(json.dumps(rep, indent=2))
    else:
        demo()
