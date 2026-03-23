from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from .room_manager import room_manager
from .player import Player
import json, logging
from fastapi.responses import RedirectResponse
from fastapi.middleware.cors import CORSMiddleware

FRONTEND_URL = "https://viral-simulation.vercel.app"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)

logger = logging.getLogger("game_server")

app = FastAPI()

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
        message = json.loads(data)

        if message["type"] == "join_random_room":
            player.username = message.get("username")
            # create room
            room = room_manager.get_available_room()
            if not room:
                room = room_manager.create_room()
            # assign room to player
            await room.add_player(player)
            # Send joining message to all players in room (only if game hasn't started)
            if room.status == "waiting":
                await player.websocket.send_json({"type":"room_joined"})

        elif message["type"] == "create_room":
            player.username = message.get("username")
            room = room_manager.create_custom_room(player)
            await room.add_player(player)
            # broadcast room creation to the room (creator only at this point)
            await player.websocket.send_json({
                "type": "room_created",
                "code": room.code,
                "creator_id": room.creator.id,
            })

        elif message["type"] == "join_room":
            player.username = message.get("username")
            code = message.get("code")
            room = room_manager.get_room_by_code(code)
            if not room:
                await player.websocket.send_json({
                "type": "error",
                "message": f"Room {code} not found!"
                })
                return
            
            if room.status != "waiting":
                await player.websocket.send_json({
                    "type": "error",
                    "message": f"Room {code} already started!"
                })
                return
            await room.add_player(player)
            # Send joining message to all players in room (only if game hasn't started)
            if room.status == "waiting":
                await player.websocket.send_json({"type":"room_joined", "code": room.code, "creator_id": room.creator.id})
        else:
            await player.websocket.send_json({"type": "error", "message": "Unknown join type."})
            return
        
        logger.info(f"Player {player.username} joined Room {room.id if not room.code else room.code} at coordinates ({player.x_coordinate}, {player.y_coordinate})")

        while True:
            data = await websocket.receive_text()
            message = json.loads(data)

            if message["type"] == "move":
                await room.move_player(player, message["direction"])

            elif message["type"] == "chat":
                await room.broadcast({"type":"chat", "username": player.username, "room_id": room.id, "message": message.get("value", "")})
            
            elif message["type"] == "start_game":
                # Only creator can start the game
                if room.creator and room.creator.id == player.id and room.is_room_ready():
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

            if len(room.players) == 0:
                room_manager.delete_room(room.id)
