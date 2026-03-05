"""
Generates synthetic Prior Authorization data and populates the DB.
Run via: python -m care_orchestrator.seeds.generate_synthetic_pa
"""

import asyncio
import json
import uuid
from datetime import UTC, datetime, timedelta
import random

from care_orchestrator.database import AsyncSessionLocal, create_tables
from care_orchestrator.models_db import PARecord

async def seed_synthetic_pa() -> None:
    await create_tables()
    
    statuses = ["approved", "denied", "pending", "pending_info"]
    cpt_pools = [
        ["73221"],  # MRI Joint
        ["99214", "99396"], # E&M
        ["27447"], # Knee arthroplasty
        ["J9312"], # Rituximab
    ]
    icd10_pools = [
        ["M23.51"], # Chronic instability of knee
        ["I10"],    # Hypertension
        ["E11.9"],  # Type 2 diabetes
        ["C85.90"], # Non-Hodgkin lymphoma
    ]
    
    records = []
    base_time = datetime.now(tz=UTC) - timedelta(days=30)
    
    for i in range(25):
        status = random.choice(statuses)
        idx = random.randint(0, 3)
        cpt = cpt_pools[idx]
        icd = icd10_pools[idx]
        
        # Turnaround is realistically between 5 minutes and 72 hours
        turnaround = random.uniform(5.0, 4320.0) if status != "pending" else 0.0
        
        pa_num = f"PA-{base_time.strftime('%Y%m')}-{random.randint(1000, 9999)}-{i}"
        created = base_time + timedelta(days=i + random.uniform(0.1, 1.5))
        
        summary = f"Synthetic PA requested for {cpt} by synthetic patient. Status: {status}."
        
        record = PARecord(
            id=str(uuid.uuid4()),
            pa_number=pa_num,
            patient_id=f"PAT-{random.randint(10000, 99999)}",
            status=status,
            cpt_codes=cpt,
            icd10_codes=icd,
            turnaround_minutes=turnaround,
            created_at=created,
            result_json={"notes": "Synthetic auto-generated record for local UI testing."},
            summary=summary
        )
        records.append(record)

    async with AsyncSessionLocal() as session:
        session.add_all(records)
        await session.commit()
        
    print(f"Successfully seeded {len(records)} synthetic Prior Authorization records into the local database.")

if __name__ == "__main__":
    asyncio.run(seed_synthetic_pa())
