"""
Payer config seed script.

Loads existing JSON policy files from config/policies/ into the
payer_configs database table. Idempotent: uses INSERT OR IGNORE for
SQLite; UPDATE on conflict for PostgreSQL.

Usage:
    python -m care_orchestrator.seeds.load_payer_configs

Designed to run once after `alembic upgrade head` on a fresh deployment.
"""

from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path

from care_orchestrator.database import AsyncSessionLocal, create_tables
from care_orchestrator.models_db import PayerConfig

_POLICIES_DIR = Path(os.getenv("POLICIES_DIR", "config/policies"))

# Map JSON filename stem → display name
_DISPLAY_NAMES: dict[str, str] = {
    "commercial": "Commercial / Private Insurance",
    "medicare": "Medicare (CMS Part A/B)",
    "medicaid": "Medicaid (State Plans)",
    "bcbs": "Blue Cross Blue Shield",
    "aetna": "Aetna",
    "cigna": "Cigna",
    "united": "UnitedHealth Group",
    "humana": "Humana",
}


async def seed_payer_configs(policies_dir: Path = _POLICIES_DIR) -> int:
    """
    Load JSON policy files into payer_configs table.

    Args:
        policies_dir: Directory containing <payer_id>.json files.

    Returns:
        Number of payer configs upserted.
    """
    await create_tables()
    json_files = sorted(policies_dir.glob("*.json"))

    if not json_files:
        print(f"No JSON policy files found in {policies_dir}")
        return 0

    count = 0
    async with AsyncSessionLocal() as session:
        for path in json_files:
            payer_id = path.stem
            try:
                rules = json.loads(path.read_text())
            except json.JSONDecodeError as exc:
                print(f"  SKIP {path.name}: invalid JSON — {exc}")
                continue

            display_name = _DISPLAY_NAMES.get(payer_id, payer_id.replace("_", " ").title())

            # Check if row already exists
            from sqlalchemy import select

            existing = (
                await session.execute(select(PayerConfig).where(PayerConfig.payer_id == payer_id))
            ).scalar_one_or_none()

            if existing:
                existing.rules_json = rules
                existing.display_name = display_name
                print(f"  UPDATE {payer_id}")
            else:
                session.add(
                    PayerConfig(
                        payer_id=payer_id,
                        display_name=display_name,
                        rules_json=rules,
                        active=True,
                    )
                )
                print(f"  INSERT {payer_id}")

            count += 1

        await session.commit()

    print(f"Seeded {count} payer configs.")
    return count


if __name__ == "__main__":
    asyncio.run(seed_payer_configs())
