from __future__ import annotations

import structlog
from typing import List, Optional
from circuitbreaker import circuit

import aiobotocore.session
from botocore.exceptions import ClientError

from arkashri.config import get_settings

logger = structlog.get_logger("services.email")
settings = get_settings()

@circuit(failure_threshold=5, recovery_timeout=60)
async def send_email(
    to_addresses: List[str],
    subject: str,
    body_text: str,
    body_html: Optional[str] = None,
    cc_addresses: Optional[List[str]] = None,
    bcc_addresses: Optional[List[str]] = None,
) -> bool:
    """
    Send an email via AWS SES using aiobotocore for non-blocking asynchronous I/O.
    """
    if not settings.aws_access_key_id or not settings.aws_secret_access_key:
        logger.warning(
            "aws_ses_credentials_missing",
            event="skipping_email_dispatch",
            to=to_addresses,
            subject=subject
        )
        return False

    session = aiobotocore.session.get_session()
    
    # Construct AWS SES target routing properties
    destination = {"ToAddresses": to_addresses}
    if cc_addresses:
        destination["CcAddresses"] = cc_addresses
    if bcc_addresses:
        destination["BccAddresses"] = bcc_addresses

    # Construct Message Structure
    message = {
        "Subject": {"Data": subject, "Charset": "UTF-8"},
        "Body": {
            "Text": {"Data": body_text, "Charset": "UTF-8"}
        }
    }
    if body_html:
        message["Body"]["Html"] = {"Data": body_html, "Charset": "UTF-8"} # type: ignore

    source_email = settings.smtp_from

    try:
        async with session.create_client(
            "ses",
            region_name=settings.aws_region,
            aws_access_key_id=settings.aws_access_key_id,
            aws_secret_access_key=settings.aws_secret_access_key,
        ) as client:
            
            response = await client.send_email(
                Source=source_email,
                Destination=destination,
                Message=message,
            )
            
            logger.info(
                "email_dispatched_successfully",
                message_id=response.get("MessageId"),
                to=to_addresses,
                subject=subject
            )
            return True

    except ClientError as e:
        logger.error(
            "aws_ses_client_error",
            error=e.response["Error"]["Message"],
            error_code=e.response["Error"]["Code"],
            to=to_addresses,
            subject=subject
        )
        return False
    except Exception as e:
        logger.error(
            "unexpected_email_failure",
            error=str(e),
            to=to_addresses,
            subject=subject
        )
        return False

