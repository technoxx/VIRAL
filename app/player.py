import uuid
import time
from fastapi import WebSocket

class Player:
    def __init__(self, websocket: WebSocket):
        self.websocket = websocket
        self.id = uuid.uuid4().hex[:8]
        self.username = None
        self.room_id = None
        self.x_coordinate = 0
        self.y_coordinate = 0
        self.infected = False
        self.score = 0
        self.shield_active = False
        self.shield_end_time = None
        self.frozen_until : float | None = None
    
    def activate_shield(self, duration: float):
        """Activate shield for specified duration (in seconds)"""
        self.shield_active = True
        self.shield_end_time = time.time() + duration
    
    def update_shield(self):
        """Update shield status based on elapsed time"""
        if self.shield_active and self.shield_end_time:
            if time.time() >= self.shield_end_time:
                self.shield_active = False
                self.shield_end_time = None
    
    def is_shielded(self) -> bool:
        """Check if player currently has active shield"""
        self.update_shield()
        return self.shield_active
       
        
