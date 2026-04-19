# pyre-ignore-all-errors
from __future__ import annotations

import csv
import io
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol
from urllib.parse import urljoin

import httpx
import structlog

from arkashri.config import get_settings
from arkashri.models import ERPConnection, ERPSystem
from arkashri.services.crypto import decrypt_dict

logger = structlog.get_logger(__name__)


class ERPConnectorError(ValueError):
    pass


@dataclass
class ERPFetchResult:
    records: list[dict[str, Any]]
    source: str
    metadata: dict[str, Any]


class ERPConnector(Protocol):
    async def fetch_journal_entries(
        self,
        connection: ERPConnection,
        *,
        date_range_from: str | None,
        date_range_to: str | None,
    ) -> ERPFetchResult: ...

    async def fetch_trial_balance(
        self,
        connection: ERPConnection,
        *,
        fiscal_year: int | None,
    ) -> dict[str, Any]: ...

    async def fetch_chart_of_accounts(self, connection: ERPConnection) -> dict[str, Any]: ...


def _resolve_connection_config(connection: ERPConnection) -> dict[str, Any]:
    config = connection.connection_config or {}
    encrypted_payload = config.get("aes_gcm_payload")
    if isinstance(encrypted_payload, str) and encrypted_payload:
        resolved = decrypt_dict(encrypted_payload)
        if resolved:
            return resolved
    return config


def _extract_result(payload: Any, path: str | None) -> Any:
    if not path:
        return payload

    current = payload
    for part in path.split("."):
        if isinstance(current, dict) and part in current:
            current = current[part]
            continue
        raise ERPConnectorError(f"Response path '{path}' was not found in the ERP payload.")
    return current


def _coerce_records(payload: Any, *, label: str) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        records = payload
    elif isinstance(payload, dict):
        for key in ("records", "items", "entries", "data", label):
            value = payload.get(key)
            if isinstance(value, list):
                records = value
                break
        else:
            raise ERPConnectorError(f"ERP response did not contain a list of {label}.")
    else:
        raise ERPConnectorError(f"ERP response for {label} was not a JSON object or array.")

    normalized: list[dict[str, Any]] = []
    for record in records:
        if not isinstance(record, dict):
            raise ERPConnectorError(f"ERP response for {label} contained a non-object record.")
        normalized.append(record)
    return normalized


class HTTPEngineConnector:
    def __init__(self, system: ERPSystem):
        self.system = system

    async def fetch_journal_entries(
        self,
        connection: ERPConnection,
        *,
        date_range_from: str | None,
        date_range_to: str | None,
    ) -> ERPFetchResult:
        config = _resolve_connection_config(connection)
        params = {}
        if date_range_from:
            params["date_from"] = date_range_from
        if date_range_to:
            params["date_to"] = date_range_to

        payload = await self._request_json(
            config,
            endpoint_key="journal_entries_endpoint",
            params=params,
        )
        result = _extract_result(payload, config.get("journal_entries_result_path"))
        records = _coerce_records(result, label="journal_entries")

        logger.info(
            "erp_records_fetched",
            source="ERP_API",
            erp_system=self.system.value,
            connection_id=str(connection.id),
            record_count=len(records),
        )
        return ERPFetchResult(
            records=records,
            source="ERP_API",
            metadata={"erp_system": self.system.value, "record_count": len(records)},
        )

    async def fetch_trial_balance(
        self,
        connection: ERPConnection,
        *,
        fiscal_year: int | None,
    ) -> dict[str, Any]:
        config = _resolve_connection_config(connection)
        params = {"fiscal_year": fiscal_year} if fiscal_year is not None else None
        payload = await self._request_json(
            config,
            endpoint_key="trial_balance_endpoint",
            params=params,
        )
        logger.info(
            "erp_trial_balance_fetched",
            source="ERP_API",
            erp_system=self.system.value,
            connection_id=str(connection.id),
        )
        return {
            "erp_system": self.system.value,
            "source": "ERP_API",
            "trial_balance": _extract_result(payload, config.get("trial_balance_result_path")),
        }

    async def fetch_chart_of_accounts(self, connection: ERPConnection) -> dict[str, Any]:
        config = _resolve_connection_config(connection)
        payload = await self._request_json(
            config,
            endpoint_key="chart_of_accounts_endpoint",
            params=None,
        )
        logger.info(
            "erp_chart_of_accounts_fetched",
            source="ERP_API",
            erp_system=self.system.value,
            connection_id=str(connection.id),
        )
        return {
            "erp_system": self.system.value,
            "source": "ERP_API",
            "accounts": _extract_result(payload, config.get("chart_of_accounts_result_path")),
        }

    async def _request_json(
        self,
        config: dict[str, Any],
        *,
        endpoint_key: str,
        params: dict[str, Any] | None,
    ) -> Any:
        base_url = str(config.get("base_url") or "").strip()
        endpoint = str(config.get(endpoint_key) or "").strip()
        if not base_url or not endpoint:
            raise ERPConnectorError(
                f"{self.system.value} connection is missing '{endpoint_key}' or 'base_url' configuration."
            )

        headers = {"Accept": "application/json"}
        configured_headers = config.get("headers")
        if isinstance(configured_headers, dict):
            for key, value in configured_headers.items():
                headers[str(key)] = str(value)

        bearer_token = config.get("bearer_token")
        api_key = config.get("api_key")
        if bearer_token:
            headers["Authorization"] = f"Bearer {bearer_token}"
        elif api_key:
            headers["X-API-Key"] = str(api_key)

        timeout_seconds = get_settings().erp_request_timeout_seconds
        async with httpx.AsyncClient(timeout=timeout_seconds, follow_redirects=True) as client:
            response = await client.get(
                urljoin(base_url.rstrip("/") + "/", endpoint.lstrip("/")),
                headers=headers,
                params={k: v for k, v in (params or {}).items() if v is not None},
            )
            response.raise_for_status()
            try:
                return response.json()
            except json.JSONDecodeError as exc:
                raise ERPConnectorError(
                    f"{self.system.value} endpoint '{endpoint_key}' returned non-JSON content."
                ) from exc


class GenericCSVConnector:
    async def fetch_journal_entries(
        self,
        connection: ERPConnection,
        *,
        date_range_from: str | None,
        date_range_to: str | None,
    ) -> ERPFetchResult:
        config = _resolve_connection_config(connection)
        content = config.get("csv_content")
        file_path = config.get("csv_file_path")
        if content is None and not file_path:
            raise ERPConnectorError("GENERIC_CSV connection requires 'csv_content' or 'csv_file_path'.")

        if file_path:
            csv_text = Path(str(file_path)).read_text(encoding="utf-8")
        else:
            csv_text = str(content)

        reader = csv.DictReader(io.StringIO(csv_text))
        records = [dict(row) for row in reader]
        if not records:
            raise ERPConnectorError("GENERIC_CSV connection did not provide any rows.")

        filtered_records: list[dict[str, Any]] = []
        for row in records:
            row_date = str(row.get("date") or row.get("DATE") or "").strip()
            if date_range_from and row_date and row_date < date_range_from:
                continue
            if date_range_to and row_date and row_date > date_range_to:
                continue
            filtered_records.append(row)

        logger.info(
            "erp_records_fetched",
            source="CSV_UPLOAD",
            erp_system=ERPSystem.GENERIC_CSV.value,
            connection_id=str(connection.id),
            record_count=len(filtered_records),
        )
        return ERPFetchResult(
            records=filtered_records,
            source="CSV_UPLOAD",
            metadata={"erp_system": ERPSystem.GENERIC_CSV.value, "record_count": len(filtered_records)},
        )

    async def fetch_trial_balance(
        self,
        connection: ERPConnection,
        *,
        fiscal_year: int | None,
    ) -> dict[str, Any]:
        raise ERPConnectorError("GENERIC_CSV connections do not expose a trial balance endpoint.")

    async def fetch_chart_of_accounts(self, connection: ERPConnection) -> dict[str, Any]:
        raise ERPConnectorError("GENERIC_CSV connections do not expose a chart of accounts endpoint.")


CONNECTORS: dict[ERPSystem, ERPConnector] = {
    ERPSystem.SAP_S4HANA: HTTPEngineConnector(ERPSystem.SAP_S4HANA),
    ERPSystem.ORACLE_FUSION: HTTPEngineConnector(ERPSystem.ORACLE_FUSION),
    ERPSystem.TALLY_PRIME: HTTPEngineConnector(ERPSystem.TALLY_PRIME),
    ERPSystem.ZOHO_BOOKS: HTTPEngineConnector(ERPSystem.ZOHO_BOOKS),
    ERPSystem.QUICKBOOKS: HTTPEngineConnector(ERPSystem.QUICKBOOKS),
    ERPSystem.GENERIC_CSV: GenericCSVConnector(),
}


def get_connector(erp_system: ERPSystem) -> ERPConnector:
    connector = CONNECTORS.get(erp_system)
    if connector is None:
        raise ERPConnectorError(f"No ERP connector is registered for {erp_system.value}.")
    return connector
