# pyre-ignore-all-errors
from fastapi import APIRouter
from pydantic import BaseModel

from arkashri.services.ai_fabric import client as ai_client
from arkashri.services.blockchain_adapter import ADAPTERS

router = APIRouter()

class CircuitStatus(BaseModel):
    name: str
    is_broken: bool

class EngineStatus(BaseModel):
    ai_fabric: bool
    polkadot: bool
    adapters: list[CircuitStatus]

@router.get("/status/engine", response_model=EngineStatus)
async def get_engine_status():
    """Returns the current broken/working status of AI and blockchain providers."""
    adapter_status = []
    for adapter_key, adapter in sorted(ADAPTERS.items()):
        healthy = await adapter.check_health()
        adapter_status.append(CircuitStatus(name=adapter_key, is_broken=not healthy))

    polkadot_status = next(
        (not status.is_broken for status in adapter_status if status.name == "POLKADOT"),
        False,
    )

    return EngineStatus(
        ai_fabric=bool(ai_client),
        polkadot=polkadot_status,
        adapters=adapter_status,
    )
