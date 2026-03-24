import uuid
import time
from fastapi import WebSocket
from collections import deque

class Player:
    """Represents a connected player. All mutable game state lives here"""
    def __init__(self, websocket: WebSocket) -> None:
        self.websocket = websocket
        self.id = uuid.uuid4().hex[:8]
        self.username: str | None = None
        self.room_id: str | None = None
        self.x_coordinate: int = 0
        self.y_coordinate: int = 0
        self.infected: bool = False
        self.last_move_time: float = 0.0
        self.move_timestamps: deque[float] = deque()  # stores recent move times
        self.score: int = 0
        self.shield_active: bool = False
        self.shield_end_time:float | None = None
        self.frozen_until : float | None = None
    
    def activate_shield(self, duration: float) -> None:
        """Activate shield for specified duration (in seconds)"""
        self.shield_active = True
        self.shield_end_time = time.time() + duration
    
    def update_shield(self) -> None:
        """Expire shield if its time has passed"""
        if self.shield_active and self.shield_end_time:
            if time.time() >= self.shield_end_time:
                self.shield_active = False
                self.shield_end_time = None
    
    def is_shielded(self) -> bool:
        """Check if player currently has active shield"""
        self.update_shield()
        return self.shield_active
