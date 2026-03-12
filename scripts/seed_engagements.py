#!/usr/bin/env python3
"""
Arkashri — Engagement Seed Script
===================================
Seeds all 14 engagements from the frontend registry into the backend DB.
Prints a JSON mapping of shortId → uuid to paste into lib/engagementRegistry.ts.

Usage:
    cd /Users/adityashrivastava/Desktop/company_1
    python3 scripts/seed_engagements.py

Prerequisites:
    • Backend running:  make run   (or uvicorn arkashri.main:app --reload)
    • DB migrated:      make migrate
"""
from __future__ import annotations

import json
import sys
import urllib.request
import urllib.error

BASE_URL = "http://localhost:8000"
TENANT   = "default_tenant"

ENGAGEMENTS = [
    {"shortId": "1092", "client_name": "Acme Corp",           "engagement_type": "forensic",     "jurisdiction": "IN"},
    {"shortId": "8841", "client_name": "Globex Inc",          "engagement_type": "financial",    "jurisdiction": "US"},
    {"shortId": "3329", "client_name": "Hooli",               "engagement_type": "esg",          "jurisdiction": "IFRS"},
    {"shortId": "2201", "client_name": "Initech",             "engagement_type": "internal",     "jurisdiction": "UK"},
    {"shortId": "4412", "client_name": "Umbrella Corp",       "engagement_type": "external",     "jurisdiction": "IN"},
    {"shortId": "5503", "client_name": "Stark Industries",    "engagement_type": "statutory",    "jurisdiction": "US"},
    {"shortId": "6614", "client_name": "Wayne Enterprises",   "engagement_type": "tax",          "jurisdiction": "IFRS"},
    {"shortId": "7725", "client_name": "Cyberdyne Systems",   "engagement_type": "compliance",   "jurisdiction": "UK"},
    {"shortId": "8836", "client_name": "Oscorp Industries",   "engagement_type": "operational",  "jurisdiction": "IN"},
    {"shortId": "9947", "client_name": "Massive Dynamic",     "engagement_type": "it",           "jurisdiction": "US"},
    {"shortId": "1058", "client_name": "Pied Piper",          "engagement_type": "payroll",      "jurisdiction": "IFRS"},
    {"shortId": "2169", "client_name": "Dunder Mifflin",      "engagement_type": "performance",  "jurisdiction": "UK"},
    {"shortId": "3270", "client_name": "Vandelay Industries", "engagement_type": "quality",      "jurisdiction": "IN"},
    {"shortId": "4381", "client_name": "Soylent Corp",        "engagement_type": "environmental","jurisdiction": "US"},
]


def post(path: str, data: dict) -> dict:
    url     = f"{BASE_URL}{path}"
    payload = json.dumps(data).encode("utf-8")
    req     = urllib.request.Request(
        url,
        data=payload,
        headers={
            "Content-Type":       "application/json",
            "X-Arkashri-Tenant":  TENANT,
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=10) as resp:
        return json.loads(resp.read().decode("utf-8"))


def main() -> None:
    print("🌱  Seeding 14 engagements into Arkashri backend…\n")
    mapping: dict[str, str] = {}
    errors: list[str] = []

    for eng in ENGAGEMENTS:
        short_id = eng["shortId"]
        try:
            result = post("/api/v1/engagements", {
                "tenant_id":       TENANT,
                "jurisdiction":    eng["jurisdiction"],
                "client_name":     eng["client_name"],
                "engagement_type": eng["engagement_type"],
            })
            uuid = result["id"]
            mapping[short_id] = uuid
            print(f"  ✅  {short_id}  {eng['client_name']:<30}  {uuid}")
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8", errors="replace")
            errors.append(f"  ❌  {short_id}  HTTP {e.code}: {body[:120]}")
            print(errors[-1])
        except Exception as exc:
            errors.append(f"  ❌  {short_id}  {exc}")
            print(errors[-1])

    print(f"\n{'─'*60}")
    print("📋  Paste the uuid values below into lib/engagementRegistry.ts:\n")
    for short_id, uuid in mapping.items():
        print(f"  {{ shortId: '{short_id}', uuid: '{uuid}',")

    print(f"\n{'─'*60}")
    print(f"✅  Seeded {len(mapping)}/14 engagements.")
    if errors:
        print(f"⚠️  {len(errors)} error(s). Check that backend is running and EngagementType enum matches.")
        sys.exit(1)


if __name__ == "__main__":
    main()
