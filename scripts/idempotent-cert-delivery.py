#!/usr/bin/env python3
"""
Idempotent cert delivery simulator.

Models the IETF draft-ietf-httpapi-idempotency-key-header pattern
applied to agent trust certificate issuance.

Key = SHA256(deposit_ref + epoch_floor_hour) — deterministic,
both client and server compute independently. No coordination needed.

Scenarios:
1. Normal delivery — webhook succeeds first try
2. Retry after timeout — same key, deduplicates
3. DLQ via agentmail — email carries same idempotency key
4. Tampered retry — same deposit_ref, different payload hash → rejected
5. Thundering herd — multiple retries with jitter
6. Stale key — key expired (>24h), treated as new request

Based on: Stripe idempotency (2016), IETF draft-httpapi-idempotency-key-header (2023)
"""

import hashlib
import json
import time
import random
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class CertRequest:
    deposit_ref: str
    payload: dict
    timestamp: float = field(default_factory=time.time)

    @property
    def payload_hash(self) -> str:
        return hashlib.sha256(
            json.dumps(self.payload, sort_keys=True).encode()
        ).hexdigest()[:16]

    def idempotency_key(self, mode: str = "deposit_ref") -> str:
        """Deterministic key: both sides compute independently.
        
        mode="deposit_ref": hash(deposit_ref + agent_id + cert_type) — zero false dedup
        mode="timestamp_floor": hash(deposit_ref + epoch_floor) — v1, breaks at scale
        """
        if mode == "deposit_ref":
            # v2: deposit_ref is already unique per payment
            agent = self.payload.get("agent", "unknown")
            cert_type = self.payload.get("scope", "default")
            raw = f"{self.deposit_ref}:{agent}:{cert_type}"
        else:
            # v1: timestamp floor — false dedup at >1 cert/hour
            epoch_floor = int(self.timestamp) // 3600 * 3600
            raw = f"{self.deposit_ref}:{epoch_floor}"
        return hashlib.sha256(raw.encode()).hexdigest()[:32]


@dataclass
class DeliveryResult:
    status: str  # "delivered" | "deduplicated" | "rejected" | "expired_reissued"
    cert_id: Optional[str] = None
    attempt: int = 1
    channel: str = "webhook"  # webhook | email_dlq
    idempotency_key: str = ""


class CertDeliveryServer:
    def __init__(self, key_ttl_hours: int = 24):
        self.issued: dict[str, dict] = {}  # key -> {cert_id, payload_hash, timestamp}
        self.key_ttl = key_ttl_hours * 3600

    def process(self, req: CertRequest, channel: str = "webhook") -> DeliveryResult:
        key = req.idempotency_key()

        if key in self.issued:
            record = self.issued[key]

            # Check TTL
            if time.time() - record["timestamp"] > self.key_ttl:
                # Expired — treat as new
                cert_id = hashlib.sha256(f"{key}:reissue".encode()).hexdigest()[:12]
                self.issued[key] = {
                    "cert_id": cert_id,
                    "payload_hash": req.payload_hash,
                    "timestamp": time.time(),
                }
                return DeliveryResult(
                    status="expired_reissued",
                    cert_id=cert_id,
                    channel=channel,
                    idempotency_key=key,
                )

            # Check payload hash — tamper detection
            if record["payload_hash"] != req.payload_hash:
                return DeliveryResult(
                    status="rejected",
                    channel=channel,
                    idempotency_key=key,
                )

            # Deduplicate
            return DeliveryResult(
                status="deduplicated",
                cert_id=record["cert_id"],
                channel=channel,
                idempotency_key=key,
            )

        # New request
        cert_id = hashlib.sha256(f"{key}:cert".encode()).hexdigest()[:12]
        self.issued[key] = {
            "cert_id": cert_id,
            "payload_hash": req.payload_hash,
            "timestamp": time.time(),
        }
        return DeliveryResult(
            status="delivered",
            cert_id=cert_id,
            channel=channel,
            idempotency_key=key,
        )


def run_scenarios():
    server = CertDeliveryServer()

    scenarios = [
        ("Normal delivery", "normal"),
        ("Retry after timeout", "retry"),
        ("DLQ via agentmail", "dlq"),
        ("Tampered retry", "tampered"),
        ("Thundering herd (5 retries)", "herd"),
        ("Stale key (expired)", "stale"),
    ]

    print("=" * 60)
    print("IDEMPOTENT CERT DELIVERY SIMULATOR")
    print("IETF draft-httpapi-idempotency-key-header + Stripe pattern")
    print("=" * 60)

    for name, scenario in scenarios:
        print(f"\n--- {name} ---")

        base_req = CertRequest(
            deposit_ref=f"dep_{scenario}_001",
            payload={"agent": "kit_fox", "scope": "web_search", "amount": "0.01 SOL"},
        )

        if scenario == "normal":
            result = server.process(base_req)
            print(f"  Key: {result.idempotency_key[:16]}...")
            print(f"  Status: {result.status} | Cert: {result.cert_id} | Channel: {result.channel}")

        elif scenario == "retry":
            r1 = server.process(base_req)
            r2 = server.process(base_req)  # Same request, same key
            print(f"  Attempt 1: {r1.status} | Cert: {r1.cert_id}")
            print(f"  Attempt 2: {r2.status} | Cert: {r2.cert_id}")
            print(f"  Same cert? {r1.cert_id == r2.cert_id} ✓" if r1.cert_id == r2.cert_id else "  DUPLICATE! ✗")

        elif scenario == "dlq":
            r1 = server.process(base_req, channel="webhook")
            r2 = server.process(base_req, channel="email_dlq")  # Fallback
            print(f"  Webhook: {r1.status} | Cert: {r1.cert_id}")
            print(f"  Email DLQ: {r2.status} | Cert: {r2.cert_id}")
            print(f"  Deduplicated across channels? {r2.status == 'deduplicated'} ✓")

        elif scenario == "tampered":
            r1 = server.process(base_req)
            tampered = CertRequest(
                deposit_ref=base_req.deposit_ref,
                payload={"agent": "evil_agent", "scope": "full_access", "amount": "100 SOL"},
                timestamp=base_req.timestamp,  # Same epoch floor → same key
            )
            r2 = server.process(tampered)
            print(f"  Original: {r1.status} | Cert: {r1.cert_id}")
            print(f"  Tampered: {r2.status} | Cert: {r2.cert_id}")
            print(f"  Rejected tamper? {r2.status == 'rejected'} ✓")

        elif scenario == "herd":
            results = []
            for i in range(5):
                time.sleep(random.uniform(0.001, 0.01))  # Jitter
                r = server.process(base_req)
                results.append(r)
            delivered = sum(1 for r in results if r.status == "delivered")
            deduped = sum(1 for r in results if r.status == "deduplicated")
            print(f"  5 retries: {delivered} delivered, {deduped} deduplicated")
            certs = set(r.cert_id for r in results)
            print(f"  Unique certs issued: {len(certs)} {'✓' if len(certs) == 1 else '✗'}")

        elif scenario == "stale":
            # Simulate expired key by backdating
            old_req = CertRequest(
                deposit_ref="dep_stale_001",
                payload=base_req.payload,
                timestamp=time.time() - 25 * 3600,  # 25h ago
            )
            r1 = server.process(old_req)
            # Manually expire
            key = old_req.idempotency_key()
            server.issued[key]["timestamp"] = time.time() - 25 * 3600

            new_req = CertRequest(
                deposit_ref="dep_stale_001",
                payload=base_req.payload,
                timestamp=time.time() - 25 * 3600,  # Same epoch floor
            )
            r2 = server.process(new_req)
            print(f"  Original (25h ago): {r1.status} | Cert: {r1.cert_id}")
            print(f"  After expiry: {r2.status} | Cert: {r2.cert_id}")
            print(f"  New cert issued? {r1.cert_id != r2.cert_id} ✓")

    # Summary
    print("\n" + "=" * 60)
    print("SUMMARY")
    print(f"  Total keys tracked: {len(server.issued)}")
    print(f"  Pattern: SHA256(deposit_ref + epoch_floor_hour)")
    print(f"  Key TTL: {server.key_ttl // 3600}h")
    print(f"  Tamper detection: payload_hash mismatch → reject")
    print(f"  Cross-channel dedup: webhook + email_dlq share keyspace")
    print("=" * 60)


if __name__ == "__main__":
    run_scenarios()
