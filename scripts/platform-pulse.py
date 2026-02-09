#!/usr/bin/env python3
"""platform-pulse.py — Lightweight platform status check returning JSON summary.

Checks all 4 platforms (Moltbook, Clawk, AgentMail, Shellmates) in parallel
and returns a unified JSON summary. Faster than 4 separate curls each heartbeat.

Usage:
    python3 scripts/platform-pulse.py          # Pretty JSON output
    python3 scripts/platform-pulse.py --compact # One-line JSON
    python3 scripts/platform-pulse.py --alert   # Only show platforms needing attention
"""

import json
import sys
import os
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.request import Request, urlopen
from urllib.error import URLError, HTTPError

def load_cred(path):
    """Load API key from credentials JSON file."""
    try:
        with open(os.path.expanduser(path)) as f:
            data = json.load(f)
            return data.get('api_key') or data.get('key') or data.get('token', '')
    except (FileNotFoundError, json.JSONDecodeError):
        return None

def api_get(url, key, timeout=8):
    """Make authenticated GET request, return (data, latency_ms, error)."""
    req = Request(url, headers={
        'Authorization': f'Bearer {key}',
        'Content-Type': 'application/json'
    })
    start = time.time()
    try:
        with urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read())
            latency = int((time.time() - start) * 1000)
            return data, latency, None
    except (URLError, HTTPError, json.JSONDecodeError, Exception) as e:
        latency = int((time.time() - start) * 1000)
        return None, latency, str(e)

def check_moltbook(key):
    """Check Moltbook DMs."""
    data, ms, err = api_get('https://www.moltbook.com/api/v1/agents/dm/check', key)
    if err:
        return {'platform': 'moltbook', 'status': 'error', 'error': err, 'latency_ms': ms}
    return {
        'platform': 'moltbook',
        'status': 'ok',
        'latency_ms': ms,
        'has_activity': data.get('has_activity', False),
        'unread_dms': data.get('messages', {}).get('total_unread', 0),
        'pending_requests': data.get('requests', {}).get('count', 0),
        'needs_attention': data.get('has_activity', False)
    }

def check_clawk(key):
    """Check Clawk notifications."""
    data, ms, err = api_get('https://www.clawk.ai/api/v1/notifications?limit=5', key)
    if err:
        return {'platform': 'clawk', 'status': 'error', 'error': err, 'latency_ms': ms}
    notifs = data.get('notifications', [])
    recent = [n for n in notifs if n.get('type') in ('reply', 'mention')]
    return {
        'platform': 'clawk',
        'status': 'ok',
        'latency_ms': ms,
        'total_notifications': len(notifs),
        'replies_mentions': len(recent),
        'latest_types': [n.get('type') for n in notifs[:5]],
        'needs_attention': len(recent) > 0
    }

def check_agentmail(key):
    """Check AgentMail inbox."""
    data, ms, err = api_get('https://api.agentmail.to/v0/inboxes/kit_fox@agentmail.to/messages?limit=5', key)
    if err:
        return {'platform': 'agentmail', 'status': 'error', 'error': err, 'latency_ms': ms}
    messages = data.get('messages', [])
    inbound = [m for m in messages if 'received' in (m.get('labels') or []) and 'unread' in (m.get('labels') or [])]
    return {
        'platform': 'agentmail',
        'status': 'ok',
        'latency_ms': ms,
        'total_recent': len(messages),
        'unread_inbound': len(inbound),
        'needs_attention': len(inbound) > 0
    }

def check_shellmates(key):
    """Check Shellmates activity."""
    data, ms, err = api_get('https://www.shellmates.app/api/v1/activity', key)
    if err:
        return {'platform': 'shellmates', 'status': 'error', 'error': err, 'latency_ms': ms}
    return {
        'platform': 'shellmates',
        'status': 'ok',
        'latency_ms': ms,
        'new_matches': data.get('new_matches', 0),
        'unread_messages': data.get('unread_messages', 0),
        'discover_count': data.get('discover_count', 0),
        'needs_attention': data.get('unread_messages', 0) > 0
    }

def clear_screen():
    """Clear terminal screen."""
    sys.stdout.write('\033[2J\033[H')
    sys.stdout.flush()

def run_pulse(compact=False, alert_only=False):
    """Run a single pulse check and return summary dict."""
    
    creds = {
        'moltbook': load_cred('~/.config/moltbook/credentials.json'),
        'clawk': load_cred('~/.config/clawk/credentials.json'),
        'agentmail': load_cred('~/.config/agentmail/credentials.json'),
        'shellmates': load_cred('~/.config/shellmates/credentials.json'),
    }
    
    checks = {
        'moltbook': (check_moltbook, creds['moltbook']),
        'clawk': (check_clawk, creds['clawk']),
        'agentmail': (check_agentmail, creds['agentmail']),
        'shellmates': (check_shellmates, creds['shellmates']),
    }
    
    results = {}
    start = time.time()
    
    with ThreadPoolExecutor(max_workers=4) as pool:
        futures = {}
        for name, (fn, key) in checks.items():
            if key:
                futures[pool.submit(fn, key)] = name
            else:
                results[name] = {'platform': name, 'status': 'no_credentials', 'needs_attention': False}
        
        for future in as_completed(futures):
            name = futures[future]
            try:
                results[name] = future.result()
            except Exception as e:
                results[name] = {'platform': name, 'status': 'error', 'error': str(e), 'needs_attention': False}
    
    total_ms = int((time.time() - start) * 1000)
    
    summary = {
        'timestamp': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
        'total_latency_ms': total_ms,
        'any_attention_needed': any(r.get('needs_attention') for r in results.values()),
        'platforms': list(results.values()) if not alert_only else [r for r in results.values() if r.get('needs_attention')]
    }
    
    return summary

def main():
    compact = '--compact' in sys.argv
    alert_only = '--alert' in sys.argv
    watch_mode = '--watch' in sys.argv
    
    # Parse interval: --watch or --watch=N (default 60s)
    interval = 60
    for arg in sys.argv:
        if arg.startswith('--watch='):
            try:
                interval = int(arg.split('=')[1])
            except ValueError:
                interval = 60
    
    indent = None if compact else 2
    prev_summary = None
    
    while True:
        summary = run_pulse(compact=compact, alert_only=alert_only)
        
        if watch_mode and prev_summary:
            # Compute diffs
            changes = []
            prev_platforms = {p['platform']: p for p in prev_summary.get('platforms', [])}
            for plat in summary.get('platforms', []):
                name = plat['platform']
                prev = prev_platforms.get(name, {})
                for key, val in plat.items():
                    if key in ('platform', 'status', 'latency_ms'):
                        continue
                    old_val = prev.get(key)
                    if old_val is not None and old_val != val:
                        changes.append(f"  {name}.{key}: {old_val} → {val}")
            
            if watch_mode:
                clear_screen()
                print(f"🔄 platform-pulse (every {interval}s) — {summary['timestamp']}")
                print(f"   Total: {summary['total_latency_ms']}ms | Attention: {summary['any_attention_needed']}")
                print()
                
                for plat in summary.get('platforms', []):
                    status_icon = '🟢' if plat['status'] == 'ok' else '🔴'
                    attn = ' ⚠️' if plat.get('needs_attention') else ''
                    details = {k: v for k, v in plat.items() if k not in ('platform', 'status', 'latency_ms', 'needs_attention')}
                    print(f"{status_icon} {plat['platform']:<12} {plat.get('latency_ms', '?')}ms{attn}  {json.dumps(details)}")
                
                if changes:
                    print(f"\n📊 Changes since last check:")
                    for c in changes:
                        print(c)
                else:
                    print(f"\n— No changes")
                print()
        else:
            if watch_mode:
                clear_screen()
                print(f"🔄 platform-pulse (every {interval}s) — {summary['timestamp']}")
                print(f"   Total: {summary['total_latency_ms']}ms | Attention: {summary['any_attention_needed']}")
                print()
                for plat in summary.get('platforms', []):
                    status_icon = '🟢' if plat['status'] == 'ok' else '🔴'
                    attn = ' ⚠️' if plat.get('needs_attention') else ''
                    details = {k: v for k, v in plat.items() if k not in ('platform', 'status', 'latency_ms', 'needs_attention')}
                    print(f"{status_icon} {plat['platform']:<12} {plat.get('latency_ms', '?')}ms{attn}  {json.dumps(details)}")
                print()
            else:
                print(json.dumps(summary, indent=indent))
        
        if not watch_mode:
            break
        
        prev_summary = summary
        try:
            time.sleep(interval)
        except KeyboardInterrupt:
            print("\n👋 Stopped.")
            break

if __name__ == '__main__':
    main()
