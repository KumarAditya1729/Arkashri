# pyre-ignore-all-errors
import structlog
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Query, HTTPException

from arkashri.services.jwt_service import decode_ws_ticket

logger = structlog.get_logger("api.websockets")

router = APIRouter()

class ConnectionManager:
    def __init__(self):
        # Maps a channel string to a list of active WebSocket connections
        self.active_connections: dict[str, list[WebSocket]] = {}

    async def connect(self, channel: str, websocket: WebSocket):
        await websocket.accept()
        if channel not in self.active_connections:
            self.active_connections[channel] = []
        self.active_connections[channel].append(websocket)
        logger.info("websocket_connected", channel=channel)

    def disconnect(self, channel: str, websocket: WebSocket):
        if channel in self.active_connections:
            self.active_connections[channel].remove(websocket)
            if not self.active_connections[channel]:
                del self.active_connections[channel]
            logger.info("websocket_disconnected", channel=channel)

    async def broadcast(self, channel: str, message: dict):
        if channel in self.active_connections:
            for connection in self.active_connections[channel]:
                try:
                    await connection.send_json(message)
                except Exception as e:
                    logger.warning("websocket_broadcast_failed", error=str(e))

manager = ConnectionManager()

@router.websocket("/ws/test")
async def test_websocket(websocket: WebSocket):
    """
    Simple test WebSocket endpoint
    """
    await websocket.accept()
    await websocket.send_text("WebSocket connection successful!")
    try:
        while True:
            data = await websocket.receive_text()
            await websocket.send_text(f"Echo: {data}")
    except WebSocketDisconnect:
        logger.info("Test WebSocket disconnected")

@router.websocket("/ws/audit/{tenant_id}/{jurisdiction}")
async def audit_stream(
    websocket: WebSocket, 
    tenant_id: str, 
    jurisdiction: str,
    ticket: str | None = Query(default=None),
):
    """
    Establish a persistent real-time connection to stream audit progress 
    events to multiple frontend client dashboards simultaneously.
    """
    channel = f"audit:{tenant_id}:{jurisdiction}"
    try:
        if not ticket:
            await websocket.close(code=4401, reason="Missing WebSocket ticket")
            return

        try:
            claims = decode_ws_ticket(ticket)
        except HTTPException as exc:
            logger.warning("websocket_auth_failed", tenant_id=tenant_id, detail=exc.detail)
            await websocket.close(code=4401, reason="Invalid WebSocket ticket")
            return

        if claims.get("tenant_id") != tenant_id or str(claims.get("jurisdiction", "")).upper() != jurisdiction.upper():
            logger.warning("websocket_scope_mismatch", tenant_id=tenant_id, jurisdiction=jurisdiction)
            await websocket.close(code=4403, reason="Ticket scope does not match requested channel")
            return

        # manager.connect accepts the WebSocket — do NOT call accept() here too
        await manager.connect(channel, websocket)
        logger.info(
            "websocket_auth_success",
            tenant_id=tenant_id,
            jurisdiction=jurisdiction,
            user_id=claims.get("user_id"),
        )

        try:
            while True:
                # Keep alive — receive so we detect client disconnects
                await websocket.receive_text()
        except WebSocketDisconnect:
            manager.disconnect(channel, websocket)

    except WebSocketDisconnect:
        manager.disconnect(channel, websocket)
    except Exception as e:
        logger.error("websocket_connection_error", error=str(e), tenant_id=tenant_id)
        manager.disconnect(channel, websocket)
        try:
            await websocket.close(code=4000, reason=f"Connection error: {str(e)}")
        except Exception:
            pass  # Already closed
