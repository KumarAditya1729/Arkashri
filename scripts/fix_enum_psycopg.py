import json
import psycopg
from arkashri.config import get_settings

REQUIRED_VALUES = [
    "FINANCIAL_AUDIT",
    "INTERNAL_AUDIT",
    "EXTERNAL_AUDIT",
    "STATUTORY_AUDIT",
    "COMPLIANCE_AUDIT",
    "OPERATIONAL_AUDIT",
    "TAX_AUDIT",
    "IT_AUDIT",
    "FORENSIC_AUDIT",
    "PERFORMANCE_AUDIT",
    "ENVIRONMENTAL_AUDIT",
    "PAYROLL_AUDIT",
    "QUALITY_AUDIT",
    "SINGLE_AUDIT",
]

def fix_enum():
    settings = get_settings()
    conn_str = settings.database_url.replace("postgresql+asyncpg://", "postgresql://")
    print(f"Connecting to Postgres with psycopg...")
    
    # Connect in autocommit mode so ALTER TYPE can run outside transactions
    with psycopg.connect(conn_str, autocommit=True) as conn:
        with conn.cursor() as cur:
            # 1. Get existing values
            cur.execute(
                "SELECT enumlabel FROM pg_enum JOIN pg_type ON pg_enum.enumtypid = pg_type.oid WHERE typname = 'engagement_type';"
            )
            existing_values = {row[0] for row in cur.fetchall()}
            print(f"Existing values: {existing_values}")
            
            # 2. Add missing values
            for val in REQUIRED_VALUES:
                if val not in existing_values:
                    print(f"Adding value: {val}")
                    try:
                        cur.execute(f"ALTER TYPE engagement_type ADD VALUE '{val}'")
                        print(f"Added: {val}")
                    except Exception as e:
                        print(f"Failed to add {val}: {e}")

if __name__ == "__main__":
    fix_enum()
