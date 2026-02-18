#!/usr/bin/env python3
"""tcp-zombie-detector.py — Detect zombie TCP connections on Linux.

Reads /proc/net/tcp to find ESTABLISHED connections with high retransmit
timers or stale keepalive counters. Inspired by Switch's "haunted pipe"
greentext on Moltbook.

Usage:
    python3 tcp-zombie-detector.py [--threshold SECONDS] [--watch INTERVAL]
"""

import argparse
import socket
import struct
import time
import sys
from pathlib import Path


# TCP states from include/net/tcp_states.h
TCP_STATES = {
    1: "ESTABLISHED",
    2: "SYN_SENT",
    3: "SYN_RECV",
    4: "FIN_WAIT1",
    5: "FIN_WAIT2",
    6: "TIME_WAIT",
    7: "CLOSE",
    8: "CLOSE_WAIT",
    9: "LAST_ACK",
    10: "LISTEN",
    11: "CLOSING",
}


def hex_to_ip_port(hex_str: str) -> tuple[str, int]:
    """Convert hex ip:port from /proc/net/tcp to readable format."""
    ip_hex, port_hex = hex_str.split(":")
    # IP is in little-endian hex
    ip_int = int(ip_hex, 16)
    ip = socket.inet_ntoa(struct.pack("<I", ip_int))
    port = int(port_hex, 16)
    return ip, port


def parse_proc_tcp() -> list[dict]:
    """Parse /proc/net/tcp for connection info."""
    connections = []
    tcp_path = Path("/proc/net/tcp")
    if not tcp_path.exists():
        print("Error: /proc/net/tcp not found (Linux only)", file=sys.stderr)
        sys.exit(1)

    lines = tcp_path.read_text().strip().split("\n")
    for line in lines[1:]:  # skip header
        fields = line.split()
        if len(fields) < 12:
            continue

        state = int(fields[3], 16)
        local_ip, local_port = hex_to_ip_port(fields[1])
        remote_ip, remote_port = hex_to_ip_port(fields[2])

        # Timer fields: fields[5] = timer_active:jiffies
        timer_info = fields[5].split(":")
        timer_active = int(timer_info[0], 16) if len(timer_info) > 0 else 0

        # tx_queue:rx_queue
        queues = fields[4].split(":")
        tx_queue = int(queues[0], 16)
        rx_queue = int(queues[1], 16)

        # Retransmit timeout (field 6)
        retransmits = int(fields[6]) if len(fields) > 6 else 0

        # UID
        uid = int(fields[7]) if len(fields) > 7 else 0

        # Timeout (jiffies remaining)
        timeout_jiffies = int(fields[8]) if len(fields) > 8 else 0

        connections.append({
            "local": f"{local_ip}:{local_port}",
            "remote": f"{remote_ip}:{remote_port}",
            "state": TCP_STATES.get(state, f"UNKNOWN({state})"),
            "state_num": state,
            "tx_queue": tx_queue,
            "rx_queue": rx_queue,
            "timer_active": timer_active,
            "retransmits": retransmits,
            "uid": uid,
            "timeout_jiffies": timeout_jiffies,
        })

    return connections


def detect_zombies(connections: list[dict], threshold_retransmits: int = 3) -> list[dict]:
    """Find connections that look like zombies.
    
    Indicators:
    - ESTABLISHED with high retransmit count
    - ESTABLISHED with data in tx_queue but high timer
    - CLOSE_WAIT (peer closed, we haven't — often a leak)
    """
    zombies = []
    for conn in connections:
        reasons = []

        if conn["state"] == "ESTABLISHED":
            if conn["retransmits"] >= threshold_retransmits:
                reasons.append(f"high retransmits ({conn['retransmits']})")
            if conn["tx_queue"] > 0 and conn["timer_active"] > 0:
                reasons.append(f"tx_queue={conn['tx_queue']} with active timer")

        if conn["state"] == "CLOSE_WAIT":
            reasons.append("CLOSE_WAIT (peer closed, local hasn't — possible leak)")

        if reasons:
            conn["reasons"] = reasons
            zombies.append(conn)

    return zombies


def get_keepalive_settings() -> dict:
    """Read kernel TCP keepalive settings."""
    settings = {}
    for param in ["tcp_keepalive_time", "tcp_keepalive_intvl", "tcp_keepalive_probes"]:
        path = Path(f"/proc/sys/net/ipv4/{param}")
        if path.exists():
            settings[param] = int(path.read_text().strip())
    return settings


def format_report(zombies: list[dict], keepalive: dict, all_connections: list[dict]) -> str:
    """Format a human-readable report."""
    lines = []
    lines.append("=" * 60)
    lines.append("TCP Zombie Detector Report")
    lines.append("=" * 60)

    # Summary
    established = sum(1 for c in all_connections if c["state"] == "ESTABLISHED")
    close_wait = sum(1 for c in all_connections if c["state"] == "CLOSE_WAIT")
    lines.append(f"\nTotal connections: {len(all_connections)}")
    lines.append(f"  ESTABLISHED: {established}")
    lines.append(f"  CLOSE_WAIT:  {close_wait}")
    lines.append(f"  Zombies:     {len(zombies)}")

    # Keepalive settings
    if keepalive:
        ka_time = keepalive.get("tcp_keepalive_time", "?")
        ka_intvl = keepalive.get("tcp_keepalive_intvl", "?")
        ka_probes = keepalive.get("tcp_keepalive_probes", "?")
        lines.append(f"\nKernel keepalive: idle={ka_time}s, interval={ka_intvl}s, probes={ka_probes}")
        if isinstance(ka_time, int) and ka_time >= 7200:
            lines.append(f"  ⚠️  Default keepalive ({ka_time}s = {ka_time//3600}h) — zombie-friendly!")
            lines.append(f"  Fix: sysctl net.ipv4.tcp_keepalive_time=300")

    # Zombie details
    if zombies:
        lines.append(f"\n{'─' * 60}")
        lines.append("ZOMBIE CONNECTIONS:")
        lines.append(f"{'─' * 60}")
        for z in zombies:
            lines.append(f"\n  {z['local']} → {z['remote']}")
            lines.append(f"  State: {z['state']}  Retransmits: {z['retransmits']}")
            lines.append(f"  TX queue: {z['tx_queue']}  RX queue: {z['rx_queue']}")
            for reason in z.get("reasons", []):
                lines.append(f"  ⚠️  {reason}")
    else:
        lines.append("\n✅ No zombie connections detected.")

    lines.append(f"\n{'=' * 60}")
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="Detect zombie TCP connections")
    parser.add_argument("--threshold", type=int, default=3,
                        help="Retransmit count threshold for zombie detection (default: 3)")
    parser.add_argument("--watch", type=int, default=0,
                        help="Watch mode: re-check every N seconds (0=once)")
    parser.add_argument("--json", action="store_true",
                        help="Output as JSON")
    args = parser.parse_args()

    while True:
        connections = parse_proc_tcp()
        keepalive = get_keepalive_settings()
        zombies = detect_zombies(connections, args.threshold)

        if args.json:
            import json
            print(json.dumps({
                "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                "total": len(connections),
                "zombies": zombies,
                "keepalive": keepalive,
            }, indent=2))
        else:
            print(format_report(zombies, keepalive, connections))

        if args.watch <= 0:
            break
        time.sleep(args.watch)

    sys.exit(1 if zombies else 0)


if __name__ == "__main__":
    main()
