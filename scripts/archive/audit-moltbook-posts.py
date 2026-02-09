#!/usr/bin/env python3
"""Audit moltbook-posts.md — verify all tracked post IDs are still valid."""
import json, re, subprocess, time, sys

def get_key():
    with open('/home/yallen/.config/moltbook/credentials.json') as f:
        return json.load(f)['api_key']

def extract_uuids(filepath):
    pattern = re.compile(r'[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}')
    with open(filepath) as f:
        return list(set(pattern.findall(f.read())))

def check_post(post_id, key):
    import urllib.request
    req = urllib.request.Request(
        f'https://www.moltbook.com/api/v1/posts/{post_id}',
        headers={'Authorization': f'Bearer {key}'}
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read())
            title = data.get('post', {}).get('title', 'untitled')
            return {'id': post_id, 'status': 'ok', 'title': title[:60]}
    except urllib.error.HTTPError as e:
        return {'id': post_id, 'status': f'error_{e.code}', 'title': None}
    except Exception as e:
        return {'id': post_id, 'status': f'error_{type(e).__name__}', 'title': None}

def main():
    tracker = 'memory/moltbook-posts.md'
    key = get_key()
    uuids = extract_uuids(tracker)
    print(f"Found {len(uuids)} unique post IDs in {tracker}")
    
    results = {'ok': [], 'missing': [], 'error': []}
    for uid in sorted(uuids):
        r = check_post(uid, key)
        time.sleep(0.3)
        if r['status'] == 'ok':
            results['ok'].append(r)
            print(f"  ✅ {uid[:8]} — {r['title']}")
        elif 'error_404' in r['status']:
            results['missing'].append(r)
            print(f"  ❌ {uid[:8]} — 404 NOT FOUND")
        else:
            results['error'].append(r)
            print(f"  ⚠️  {uid[:8]} — {r['status']}")
    
    print(f"\nSummary: {len(results['ok'])} valid, {len(results['missing'])} missing, {len(results['error'])} errors")
    
    if '--json' in sys.argv:
        print(json.dumps(results, indent=2))
    
    return len(results['missing'])

if __name__ == '__main__':
    sys.exit(main())
