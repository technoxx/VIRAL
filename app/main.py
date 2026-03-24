from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from .room_manager import room_manager
from .player import Player
import json, logging, os
from fastapi.responses import RedirectResponse
from fastapi.middleware.cors import CORSMiddleware

FRONTEND_URL = os.getenv("FRONTEND_URL")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)

logger = logging.getLogger("game_server")

app = FastAPI(title="VIRAL - Infection Simulator")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        FRONTEND_URL
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
def root():
    return RedirectResponse(FRONTEND_URL)

@app.get("/health")
async def health():
    return {"status": "ok"}

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    origin = websocket.headers.get("origin")

    allowed_origins = [
        FRONTEND_URL
    ]

    if origin not in allowed_origins:
        await websocket.close(code=1008)
        return
    
    await websocket.accept()

    # create player
    player = Player(websocket)
    logger.info(f"Player {player.id} welcome!")

    room = None

    try:
        data = await websocket.receive_text()

        try:
            message = json.loads(data)
        except json.JSONDecodeError:
            await websocket.send_json({"type": "error", "message": "Invalid JSON."})
            await websocket.close()
            return
        
        msg_type = message.get("type")
        username  = message.get("username")
 
        if not username:
            await websocket.send_json({"type": "error", "message": "Username is required."})
            await websocket.close()
            return
 
        player.username = username

        if msg_type == "join_random_room":
            # create room
            room = room_manager.get_available_room()
            if not room:
                room = room_manager.create_room()
            # assign room to player
            await room.add_player(player)
            # Send joining message to all players in room (only if game hasn't started)
            if room.status == "waiting":
                await player.websocket.send_json({"type":"room_joined"})

        elif msg_type == "create_room":
            room = room_manager.create_custom_room(player)
            await room.add_player(player)
            # broadcast room creation to the room (creator only at this point)
            await player.websocket.send_json({
                "type": "room_created",
                "code": room.code,
                "creator_id": room.creator.id,
            })

        elif msg_type == "join_room":
            code = message.get("code")
            if not code:
                await websocket.send_json({"type": "error", "message": "Room code is required."})
                await websocket.close()
                return

            room = room_manager.get_room_by_code(code)
            if not room:
                await player.websocket.send_json({
                "type": "error",
                "message": f"Room {code} not found!"
                })
                await websocket.close()
                return
            
            if room.status != "waiting":
                await player.websocket.send_json({
                    "type": "error",
                    "message": f"Room {code} already started!"
                })
                await websocket.close()
                return
            await room.add_player(player)
            # Send joining message to all players in room (only if game hasn't started)
            await player.websocket.send_json({"type":"room_joined", "code": room.code, "creator_id": room.creator.id})
        else:
            await websocket.send_json({"type": "error", "message": "Unknown message type."})
            await websocket.close()
            return
        
        logger.info(f"Player {player.username} joined Room {room.id if not room.code else room.code} at coordinates ({player.x_coordinate}, {player.y_coordinate})")

        while True:
            data = await websocket.receive_text()
            try:
                message = json.loads(data)
            except json.JSONDecodeError:
                await websocket.send_json({"type": "error", "message": "Invalid JSON."})
                continue

            msg_type = message.get("type")

            if msg_type == "move":
                direction = message.get("direction", "")
                if direction in ("up", "down", "left", "right"):
                    await room.move_player(player, direction)

            elif msg_type == "chat":
                await room.broadcast({"type":"chat", "username": player.username, "room_id": room.id, "message": message.get("value", "")})
            
            elif msg_type == "start_game":
                # Only creator can start the game
                if (room.creator and room.creator.id == player.id and room.is_room_ready()):
                    await room.start_game()
                else:
                    await player.websocket.send_json({
                        "type": "error",
                        "message": "A room must have atleast 2 players!"
                    })

    except WebSocketDisconnect:
        if room:
            room.remove_player(player.id)
            logger.info(f"Player {player.id} just left Room {room.id}!")
            await room.broadcast({"type":"chat", "username": player.username, "room_id": room.id, "message": "left!"})
            await room.broadcast({"type": "player_disconnected", "player_id": player.id})

            if room.is_room_empty():
                room_manager.delete_room(room.id)
    except Exception as exc:
        logger.exception("Unexpected error for player %s: %s", player.id, exc)
        if room:
            room.remove_player(player.id)
