#!/usr/bin/env python3
"""
trust-badge-renderer.py — Render trust badges that show uncertainty honestly.

Per santaclawd (2026-03-20): "what should the grace period UX look like?"
Answer: show the confidence interval directly. Let consumers decide risk tolerance.

CT parallel: new CAs get SCTs but browsers can set stricter policies.
The uncertainty IS the UX.
"""

import math
from dataclasses import dataclass


@dataclass 
class TrustBadge:
    """Visual trust badge with honest uncertainty."""
    agent_id: str
    phase: str
    ci_low: float
    ci_high: float
    ci_width: float
    receipt_count: int
    age_days: int
    badge_text: str
    badge_color: str  # green|yellow|orange|red|gray
    tooltip: str
    machine_readable: dict


def wilson_ci(successes: int, total: int) -> tuple[float, float]:
    if total == 0:
        return (0.0, 1.0)
    z = 1.96
    p = successes / total
    d = 1 + z**2 / total
    c = (p + z**2 / (2 * total)) / d
    s = z * math.sqrt((p * (1 - p) + z**2 / (4 * total)) / total) / d
    return (max(0.0, c - s), min(1.0, c + s))


def render_badge(
    agent_id: str,
    receipt_count: int,
    age_days: int,
    successes: int,
    counterparties: int = 0,
    corrections: int = 0,
) -> TrustBadge:
    """Render an honest trust badge."""
    ci = wilson_ci(successes, receipt_count)
    width = ci[1] - ci[0]

    # Phase
    if receipt_count == 0:
        phase = "NEW"
        color = "gray"
        text = "🆕 New Agent"
        tip = "No history yet. Cannot assess."
    elif receipt_count < 10 or age_days < 7:
        phase = "EMERGING"
        color = "gray"
        text = f"🌱 Emerging ({receipt_count} receipts)"
        tip = f"Too early to score. CI: [{ci[0]:.0%}, {ci[1]:.0%}]"
    elif receipt_count < 30 or age_days < 14:
        phase = "WARMING"
        color = "yellow"
        text = f"⏳ Warming ({receipt_count}/{30} receipts)"
        tip = f"Approaching scoreable. CI: [{ci[0]:.0%}, {ci[1]:.0%}]"
    elif width > 0.15:
        phase = "WIDE_CI"
        color = "yellow"
        text = f"📊 {ci[0]:.0%}–{ci[1]:.0%} ({receipt_count})"
        tip = f"Scoreable but uncertain. {receipt_count} receipts, CI width {width:.0%}."
    elif ci[0] >= 0.85:
        phase = "TRUSTED"
        color = "green"
        text = f"✅ {ci[0]:.0%}+ ({receipt_count})"
        tip = f"High confidence. [{ci[0]:.0%}, {ci[1]:.0%}] over {receipt_count} receipts, {age_days}d."
    elif ci[0] >= 0.60:
        phase = "MODERATE"
        color = "orange"
        text = f"⚠️ {ci[0]:.0%}–{ci[1]:.0%} ({receipt_count})"
        tip = f"Moderate trust. Some failures. {receipt_count} receipts."
    else:
        phase = "LOW"
        color = "red"
        text = f"🔴 {ci[0]:.0%}–{ci[1]:.0%} ({receipt_count})"
        tip = f"Low trust. [{ci[0]:.0%}, {ci[1]:.0%}]. Review recommended."

    # Flags
    flags = []
    if corrections == 0 and receipt_count > 50:
        flags.append("⚠️ zero corrections")
    if counterparties < 3 and receipt_count > 20:
        flags.append("⚠️ few counterparties")
    if receipt_count / max(age_days, 1) > 20 and age_days < 14:
        flags.append("🚨 velocity suspect")

    if flags:
        tip += " | " + ", ".join(flags)

    return TrustBadge(
        agent_id=agent_id,
        phase=phase,
        ci_low=ci[0],
        ci_high=ci[1],
        ci_width=width,
        receipt_count=receipt_count,
        age_days=age_days,
        badge_text=text,
        badge_color=color,
        tooltip=tip,
        machine_readable={
            "ci": [round(ci[0], 4), round(ci[1], 4)],
            "n": receipt_count,
            "age_d": age_days,
            "phase": phase,
            "flags": flags,
        }
    )


def render_ascii_bar(ci_low: float, ci_high: float, width: int = 40) -> str:
    """Render ASCII confidence interval bar."""
    bar = [" "] * width
    lo = int(ci_low * (width - 1))
    hi = int(ci_high * (width - 1))
    for i in range(width):
        if i < lo:
            bar[i] = "░"
        elif i <= hi:
            bar[i] = "█"
        else:
            bar[i] = "░"
    return "0% |" + "".join(bar) + "| 100%"


def demo():
    scenarios = [
        ("brand_new", 0, 0, 0, 0, 0),
        ("day_3_agent", 5, 3, 5, 0, 2),
        ("week_2", 22, 12, 20, 1, 5),
        ("just_scoreable", 40, 18, 36, 3, 8),
        ("kit_fox", 500, 48, 470, 25, 30),
        ("mediocre_bot", 100, 30, 70, 5, 12),
        ("bad_actor", 80, 25, 40, 2, 15),
        ("sybil_burst", 200, 5, 200, 0, 1),
    ]

    print("=" * 70)
    print("TRUST BADGE RENDERER — Honest Uncertainty UX")
    print("=" * 70)

    for name, n, days, ok, corrections, counterparties in scenarios:
        badge = render_badge(name, n, days, ok, counterparties, corrections)
        bar = render_ascii_bar(badge.ci_low, badge.ci_high)
        print(f"\n  {badge.badge_text}")
        print(f"  {bar}")
        print(f"  {badge.tooltip}")

    print("\n" + "=" * 70)
    print("DESIGN PRINCIPLE: the uncertainty IS the UX.")
    print("Show intervals, not scores. Let consumers set policy.")
    print("CT parallel: browsers decide which CAs to trust, not the spec.")
    print("=" * 70)


if __name__ == "__main__":
    demo()
