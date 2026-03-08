import structlog
from fastapi import APIRouter, WebSocket, WebSocketDisconnect

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

@router.websocket("/ws/audit/{tenant_id}/{jurisdiction}")
async def audit_stream(websocket: WebSocket, tenant_id: str, jurisdiction: str):
    """
    Establish a persistent real-time connection to stream audit progress 
    events to multiple frontend client dashboards simultaneously.
    """
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
