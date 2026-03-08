import json
import structlog
from datetime import datetime, timezone

from arkashri.config import get_settings

logger = structlog.get_logger("services.archive")
settings = get_settings()

try:
    from aiobotocore.session import get_session
except ImportError:
    get_session = None
    logger.warning("aiobotocore missing; S3 archiving disabled.")


async def archive_completed_audit(
    run_id: str,
    tenant_id: str,
    jurisdiction: str,
    evidence_payload: dict,
    run_hash: str,
) -> str | None:
    """
    Submits the finalized audit scorecard and compiled evidence to an AWS S3
    bucket configured for Object Lock (Write Once Read Many).
    
    Returns the generated S3 `s3://` URI upon success, or None if disabled/failed.
    """
    if not get_session or not settings.s3_worm_bucket:
        logger.info(
            "s3_archive_skipped",
            run_id=run_id,
            tenant_id=tenant_id,
            reason="Bucket unconfigured or SDK missing."
        )
        return None

    session = get_session()
    
    # Format metadata prefix keys logically based on the business domain
    # Example path: overrides/us/0000-1111/timestamp/report.json
    now = datetime.now(timezone.utc)
    date_prefix = now.strftime("%Y/%m/%d")
    object_key = f"audits/{jurisdiction.lower()}/{tenant_id}/{date_prefix}/{run_id}_{run_hash[:8]}.json"

    json_body = json.dumps(
        {
            "metadata": {
                "run_id": run_id,
                "tenant_id": tenant_id,
                "jurisdiction": jurisdiction,
                "run_hash": run_hash,
                "archived_at": now.isoformat(),
                "compliance_layer": "SEC-17a-4 WORM Protocol",
            },
            "evidence": evidence_payload,
        },
        indent=2
    ).encode("utf-8")

    try:
        async with session.create_client(
            "s3",
            region_name=settings.aws_region,
            aws_access_key_id=settings.aws_access_key_id,
            aws_secret_access_key=settings.aws_secret_access_key,
        ) as client:
            
            await client.put_object(
                Bucket=settings.s3_worm_bucket,
                Key=object_key,
                Body=json_body,
                ContentType="application/json",
            )
            
            s3_uri = f"s3://{settings.s3_worm_bucket}/{object_key}"
            logger.info("s3_archived_successfully", run_id=run_id, s3_uri=s3_uri)
            return s3_uri

    except Exception as exc:
        logger.error(
            "s3_archive_failed",
            run_id=run_id,
            error=str(exc)
        )
        return None
