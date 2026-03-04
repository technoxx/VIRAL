import random, string
from .room import Room
from .player import Player

def generate_room_code():
    return ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))

class RoomManager:
    def __init__(self):
        self.rooms : dict[str, Room] = {}  # {room_1_id:Room, room_2_id:Room}

    def get_available_room(self):
        for room in self.rooms.values():
            if room.code is None and room.is_room_joinable():
                print(f"Room {room.id} available!")
                return room
        return None

    def create_room(self):
        room = Room()
        print(f"Room {room.id} created!")
        self.rooms[room.id] = room
        return room
    
    def create_custom_room(self, creator: Player):
        code = generate_room_code()
        room = Room(creator=creator, code=code)
        self.rooms[room.id] = room
        return room
    
    def get_room_by_code(self, code: str):
        for room in self.rooms.values():
            if room.code == code:
                return room
        return None
    
    def delete_room(self, room_id:str):
        if room_id in self.rooms:
            del self.rooms[room_id]
            print(f"Room {room_id} deleted!")

room_manager = RoomManager()
