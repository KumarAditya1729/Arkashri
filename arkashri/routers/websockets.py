import structlog
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Query
from arkashri.dependencies import require_api_client
from arkashri.utils.error_handling import handle_errors

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
    api_key: str = Query(default=None, alias="X-Arkashri-Key")
):
    """
    Establish a persistent real-time connection to stream audit progress 
    events to multiple frontend client dashboards simultaneously.
    """
    try:
        # Accept the WebSocket connection first
        await websocket.accept()
        
        # For now, allow connections without strict authentication
        # In production, you might want to validate the api_key here
        if api_key:
            logger.info("websocket_auth_attempt", tenant_id=tenant_id, api_key_provided=True)
        else:
            logger.info("websocket_auth_attempt", tenant_id=tenant_id, api_key_provided=False)
        
        channel = f"audit:{tenant_id}:{jurisdiction}"
        await manager.connect(channel, websocket)
        
        try:
            while True:
                # The client doesn't need to send us data, it just listens.
                # However, we must continuously receive to keep the socket alive
                # and catch client disconnections.
                await websocket.receive_text()
        except WebSocketDisconnect:
            manager.disconnect(channel, websocket)
            
    except Exception as e:
        logger.error("websocket_connection_error", error=str(e), tenant_id=tenant_id)
        await websocket.close(code=4000, reason=f"Connection error: {str(e)}")
