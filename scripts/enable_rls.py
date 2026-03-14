# pyre-ignore-all-errors
import asyncio
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy import text

from arkashri.config import get_settings

# Core tables containing sensitive tenant data that must be isolated at the dB kernel layer
RLS_TABLES = [
    "financial_transaction",
    "decision",
    "audit_event",
    "exception_case",
    "report_job",
    "chain_anchor",
    "audit_run",
    "audit_run_step",
    "approval_request",
    "rag_query_log",
    "idempotency_record",
    "engagement",
    "materiality_assessment",
    "audit_opinion"
]

async def apply_row_level_security():
    """
    Connects to the PostgreSQL instance and strictly enforces Row-Level Security policies.
    This guarantees that even if a developer writes `session.query(Transaction).all()`, 
    the database will only return rows where `tenant_id` matches `app.current_tenant`
    set contextually by the FastAPI router.
    """
    settings = get_settings()
    engine = create_async_engine(settings.database_url, isolation_level="AUTOCOMMIT")

    async with engine.connect() as conn:
        print("Starting Row-Level Security Application...")
        for table in RLS_TABLES:
            try:
                # 1. Enable RLS
                await conn.execute(text(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY;"))
                
                # 2. Force RLS for table owners (crucial for Postgres administration safety)
                await conn.execute(text(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY;"))
                
                # 3. Drop existing policy if running idempotently
                await conn.execute(text(f"DROP POLICY IF EXISTS tenant_isolation_policy ON {table};"))
                
                # 4. Create the strict tenant isolation policy
                # If app.current_tenant is not set, or is empty, no rows will be visible.
                # Adding a bypass for system operations if the tenant context is explicitly _system_admin.
                policy_ddl = f"""
                CREATE POLICY tenant_isolation_policy ON {table}
                USING (
                    tenant_id = current_setting('app.current_tenant', true)
                    OR current_setting('app.current_tenant', true) = '_system_admin'
                );
                """
                await conn.execute(text(policy_ddl))
                print(f"✅ RLS successfully enforced on: {table}")
                
            except Exception as e:
                print(f"❌ Failed to apply RLS on {table}: {e}")

    await engine.dispose()
    print("Row-Level Security Hardening Complete.")

if __name__ == "__main__":
    asyncio.run(apply_row_level_security())
