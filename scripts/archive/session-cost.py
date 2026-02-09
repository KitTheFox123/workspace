#!/usr/bin/env python3
"""session-cost.py — Estimate daily API cost from OpenClaw session data.

Reads session logs and estimates token usage / cost for the day.
Helps Ilya track spending on Kit's operations.

Usage:
    python3 scripts/session-cost.py [--date YYYY-MM-DD] [--detailed]
"""

import argparse
import json
import os
import re
import subprocess
from datetime import datetime, date
from pathlib import Path

# Model pricing per 1M tokens (input/output)
MODEL_PRICING = {
    "claude-opus-4-6": {"input": 15.0, "output": 75.0},
    "claude-opus-4": {"input": 15.0, "output": 75.0},
    "claude-sonnet-4": {"input": 3.0, "output": 15.0},
    "anthropic/claude-opus-4-6": {"input": 15.0, "output": 75.0},
    "anthropic/claude-sonnet-4": {"input": 3.0, "output": 15.0},
    "deepseek/deepseek-chat-v3.1": {"input": 0.14, "output": 0.28},
}

def estimate_tokens_from_log(log_path: str) -> dict:
    """Estimate tokens from a daily memory log file."""
    try:
        text = Path(log_path).read_text()
    except FileNotFoundError:
        return {"error": f"File not found: {log_path}"}
    
    # Count heartbeat sections
    heartbeats = len(re.findall(r'## Heartbeat', text))
    
    # Count writing actions (each involves API calls)
    writes = len(re.findall(r'\*\*(?:Clawk|Moltbook|lobchan|Shellmates).*?\*\*', text))
    
    # Count research sections (Keenable searches + tool calls)
    researches = len(re.findall(r'### Non-Agent Research', text))
    
    # Count build actions
    builds = len(re.findall(r'### Build Action', text))
    
    # Estimate tokens per action type
    # Main agent heartbeat dispatch: ~2K input, ~500 output
    # Subagent heartbeat: ~15K input (context), ~8K output (actions)
    # Each write action: ~1K input, ~500 output (API calls)
    # Each research: ~3K input (search results), ~1K output
    # Each build: ~2K input, ~3K output (code generation)
    
    estimates = {
        "heartbeats": heartbeats,
        "writes": writes,
        "researches": researches,
        "builds": builds,
        "tokens": {
            "main_dispatch": {
                "input": heartbeats * 5000,
                "output": heartbeats * 2000,
            },
            "subagent_work": {
                "input": heartbeats * 20000,
                "output": heartbeats * 12000,
            },
            "tool_calls": {
                "input": (writes + researches + builds) * 1500,
                "output": (writes + researches + builds) * 800,
            },
        }
    }
    
    total_input = sum(v["input"] for v in estimates["tokens"].values())
    total_output = sum(v["output"] for v in estimates["tokens"].values())
    estimates["total_input"] = total_input
    "total_output"
    estimates["total_output"] = total_output
    
    return estimates

def calculate_cost(estimates: dict, model: str = "anthropic/claude-opus-4-6") -> dict:
    """Calculate estimated cost from token estimates."""
    pricing = MODEL_PRICING.get(model, MODEL_PRICING["anthropic/claude-opus-4-6"])
    
    input_cost = (estimates["total_input"] / 1_000_000) * pricing["input"]
    output_cost = (estimates["total_output"] / 1_000_000) * pricing["output"]
    
    return {
        "model": model,
        "input_tokens": estimates["total_input"],
        "output_tokens": estimates["total_output"],
        "input_cost": round(input_cost, 2),
        "output_cost": round(output_cost, 2),
        "total_cost": round(input_cost + output_cost, 2),
    }

def check_openclaw_sessions() -> dict:
    """Try to get actual session data from OpenClaw."""
    try:
        result = subprocess.run(
            ["openclaw", "session", "list", "--json"],
            capture_output=True, text=True, timeout=5
        )
        if result.returncode == 0:
            return json.loads(result.stdout)
    except (subprocess.SubprocessError, json.JSONDecodeError, FileNotFoundError):
        pass
    return None

def main():
    parser = argparse.ArgumentParser(description="Estimate daily API costs")
    parser.add_argument("--date", default=date.today().isoformat(),
                       help="Date to analyze (YYYY-MM-DD)")
    parser.add_argument("--detailed", action="store_true",
                       help="Show detailed breakdown")
    parser.add_argument("--model", default="anthropic/claude-opus-4-6",
                       help="Model for pricing")
    parser.add_argument("--json", action="store_true", dest="json_out",
                       help="JSON output")
    args = parser.parse_args()
    
    log_path = f"memory/{args.date}.md"
    
    # Try OpenClaw session data first
    sessions = check_openclaw_sessions()
    
    # Fall back to log estimation
    estimates = estimate_tokens_from_log(log_path)
    
    if "error" in estimates:
        print(f"Error: {estimates['error']}")
        return 1
    
    cost = calculate_cost(estimates, args.model)
    
    if args.json_out:
        print(json.dumps({"estimates": estimates, "cost": cost}, indent=2))
        return 0
    
    print(f"📊 Session Cost Estimate — {args.date}")
    print(f"{'='*45}")
    print(f"Heartbeats:      {estimates['heartbeats']}")
    print(f"Writing actions:  {estimates['writes']}")
    print(f"Research topics:  {estimates['researches']}")
    print(f"Build actions:    {estimates['builds']}")
    print()
    print(f"Model: {cost['model']}")
    print(f"Est. input tokens:  {cost['input_tokens']:>10,}")
    print(f"Est. output tokens: {cost['output_tokens']:>10,}")
    print(f"Input cost:         ${cost['input_cost']:>8.2f}")
    print(f"Output cost:        ${cost['output_cost']:>8.2f}")
    print(f"{'─'*45}")
    print(f"TOTAL ESTIMATED:    ${cost['total_cost']:>8.2f}")
    
    if args.detailed:
        print(f"\n{'─'*45}")
        print("Breakdown:")
        for category, tokens in estimates["tokens"].items():
            inp = tokens["input"]
            out = tokens["output"]
            pricing = MODEL_PRICING.get(args.model, MODEL_PRICING["anthropic/claude-opus-4-6"])
            cat_cost = (inp / 1e6) * pricing["input"] + (out / 1e6) * pricing["output"]
            print(f"  {category:20s}  {inp:>8,} in / {out:>8,} out  ${cat_cost:.2f}")
    
    print(f"\n⚠️  Estimates based on log activity patterns. Actual costs may vary.")
    return 0

if __name__ == "__main__":
    exit(main())
