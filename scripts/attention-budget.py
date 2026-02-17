#!/usr/bin/env python3
"""
attention-budget.py — Attention Economy Calculator for Agents

Herbert Simon (1971): "A wealth of information creates a poverty of attention."

Estimates attention cost of agent activities per heartbeat cycle.
Helps identify attention sinks and optimize heartbeat routines.

Usage:
  python3 attention-budget.py                    # default heartbeat profile
  python3 attention-budget.py --interval 20      # 20-min heartbeat interval
"""

import argparse
import json
import sys

# Attention cost estimates (arbitrary units, calibrated to context tokens)
# Higher = more attention consumed
ACTIVITIES = {
    # Platform checks (low cost each, but cumulative)
    'clawk_notifications':   {'cost': 3, 'category': 'check', 'desc': 'Check Clawk notifications'},
    'clawk_timeline':        {'cost': 5, 'category': 'check', 'desc': 'Browse Clawk timeline'},
    'moltbook_feed':         {'cost': 5, 'category': 'check', 'desc': 'Check Moltbook feed'},
    'moltbook_dms':          {'cost': 2, 'category': 'check', 'desc': 'Check Moltbook DMs'},
    'shellmates_activity':   {'cost': 2, 'category': 'check', 'desc': 'Check Shellmates activity'},
    'email_inbox':           {'cost': 2, 'category': 'check', 'desc': 'Check AgentMail inbox'},
    'lobchan_boards':        {'cost': 3, 'category': 'check', 'desc': 'Browse lobchan boards'},

    # Writing (high cost — requires composition)
    'clawk_reply':           {'cost': 8, 'category': 'write', 'desc': 'Write Clawk reply'},
    'clawk_standalone':      {'cost': 12, 'category': 'write', 'desc': 'Write standalone Clawk post'},
    'moltbook_comment':      {'cost': 10, 'category': 'write', 'desc': 'Write Moltbook comment'},
    'moltbook_post':         {'cost': 20, 'category': 'write', 'desc': 'Write Moltbook research post'},
    'shellmates_gossip':     {'cost': 10, 'category': 'write', 'desc': 'Write Shellmates gossip post'},
    'shellmates_dm':         {'cost': 6, 'category': 'write', 'desc': 'Send Shellmates DM'},
    'lobchan_reply':         {'cost': 8, 'category': 'write', 'desc': 'Write lobchan reply'},
    'email_compose':         {'cost': 12, 'category': 'write', 'desc': 'Compose email'},

    # Research (moderate-high cost)
    'keenable_search':       {'cost': 4, 'category': 'research', 'desc': 'Keenable web search'},
    'keenable_fetch':        {'cost': 6, 'category': 'research', 'desc': 'Fetch and read page content'},
    'keenable_feedback':     {'cost': 2, 'category': 'research', 'desc': 'Submit search feedback'},

    # Building (highest cost — deep work)
    'script_write':          {'cost': 25, 'category': 'build', 'desc': 'Write new script'},
    'script_debug':          {'cost': 15, 'category': 'build', 'desc': 'Debug existing script'},
    'git_commit':            {'cost': 5, 'category': 'build', 'desc': 'Stage and commit changes'},
    'memory_update':         {'cost': 8, 'category': 'build', 'desc': 'Update MEMORY.md/daily log'},
    'skill_install':         {'cost': 10, 'category': 'build', 'desc': 'Install/configure new skill'},

    # Meta (overhead)
    'telegram_notify':       {'cost': 3, 'category': 'meta', 'desc': 'Send Telegram update to Ilya'},
    'session_status':        {'cost': 1, 'category': 'meta', 'desc': 'Check session status/time'},
}

# Typical heartbeat profile (HEARTBEAT.md requirements)
TYPICAL_HEARTBEAT = [
    'session_status',
    'clawk_notifications', 'clawk_timeline',
    'moltbook_dms', 'email_inbox', 'shellmates_activity',
    'keenable_search', 'keenable_fetch', 'keenable_feedback',
    'clawk_reply', 'clawk_reply', 'clawk_standalone',  # 3 writes
    'script_write',  # 1 build
    'memory_update',
    'telegram_notify',
]


def analyze_budget(activities: list[str], interval_min: int = 20) -> dict:
    total_cost = 0
    by_category = {}
    details = []

    for act in activities:
        if act not in ACTIVITIES:
            continue
        info = ACTIVITIES[act]
        total_cost += info['cost']
        cat = info['category']
        by_category[cat] = by_category.get(cat, 0) + info['cost']
        details.append({'activity': act, 'cost': info['cost'], 'category': cat})

    # Attention budget = interval in minutes (rough proxy: 1 unit ≈ 1 min of focused work)
    budget = interval_min
    utilization = (total_cost / budget * 100) if budget > 0 else 0

    return {
        'total_cost': total_cost,
        'budget': budget,
        'utilization': round(utilization, 1),
        'by_category': by_category,
        'details': details,
        'overbudget': total_cost > budget * 1.5,  # 150% = red zone
    }


def main():
    parser = argparse.ArgumentParser(description='Attention Budget Calculator')
    parser.add_argument('--interval', type=int, default=20, help='Heartbeat interval (minutes)')
    parser.add_argument('--json', action='store_true', help='Output as JSON')
    args = parser.parse_args()

    result = analyze_budget(TYPICAL_HEARTBEAT, args.interval)

    if args.json:
        print(json.dumps(result, indent=2))
        return

    print(f"\n{'='*55}")
    print(f"  ATTENTION BUDGET — {args.interval}min heartbeat")
    print(f"{'='*55}")
    print(f"  Total cost: {result['total_cost']} units")
    print(f"  Budget:     {result['budget']} units ({args.interval} min)")
    print(f"  Utilization: {result['utilization']}%", end='')
    if result['overbudget']:
        print('  ⚠️  OVERBUDGET')
    else:
        print('  ✓')

    print(f"\n  By category:")
    bar_max = max(result['by_category'].values()) if result['by_category'] else 1
    for cat, cost in sorted(result['by_category'].items(), key=lambda x: -x[1]):
        bar = '█' * int(cost / bar_max * 20)
        print(f"    {cat:>10}: {cost:>3} {bar}")

    print(f"\n  Simon's Law: attention is the bottleneck, not information.")
    print(f"  Optimize for fewer, deeper actions — not more shallow ones.")
    print(f"{'='*55}\n")


if __name__ == '__main__':
    main()
