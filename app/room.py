import time
import uuid, random, asyncio
from .player import Player
from .constants import *
from app import player

class Room:
    def __init__(self, code:str = None, creator: Player = None):
        self.id = uuid.uuid4().hex[:8]
        self.code = code  # None for random room
        self.creator = creator  # None for random room
        self.status = "waiting"    # allowed values: waiting, in_progress, finished
        self.players : dict[str, Player] = {}   # {player_1_id : Player(), player_2_id : Player()}
        self._countdown_task: asyncio.Task | None = None
        self._game_timer_task: asyncio.Task | None = None
        self.current_round = 0
        self.total_rounds = 3

        self._collectible_spawner_task: asyncio.Task | None = None
        self.collectibles: dict = {}  # {(x, y): 'shield' or 'freeze'}

    def is_room_ready(self):
        no_of_players = len(self.players)
        return no_of_players >= MIN_PLAYERS
    
    def is_room_full(self):
        return len(self.players) >= MAX_PLAYERS
    
    def is_room_Empty(self):
        return len(self.players) == 0
    
    def is_room_joinable(self):
        return self.status == "waiting" and not self.is_room_full()
    
    def is_position_occupied(self, x, y):
        return any(player.x_coordinate == x and player.y_coordinate == y for player in self.players.values())
    
    
    async def add_player(self, player:Player):
        player.room_id = self.id
        self.players[player.id] = player

        # if room becomes full while waiting, start the game immediately
        if self.status == "waiting" and self.is_room_ready():
            if not self.code:
                if not self._countdown_task or self._countdown_task.done():
                    self._countdown_task = asyncio.create_task(self._run_countdown_timer())


    async def _run_countdown_timer(self):
        start_time = time.time()
        end_time = start_time + COUNTDOWN_DURATION
        
        try:
            while True:
                remaining_time = int(end_time - time.time())
                if remaining_time <= 0:
                    break
                    
                await self.broadcast({
                    "type": "countdown_timer",
                    "remaining_time":remaining_time,
                    })
                await asyncio.sleep(1)

            await self.start_game()
        
        except asyncio.CancelledError:
            pass


    def remove_player(self, player_id:str):
        if player_id in self.players:
            self.players[player_id].room_id = None
            del self.players[player_id]

    def get_player_at_position(self, x, y):
        for player in self.players.values():
            if player.x_coordinate == x and player.y_coordinate == y:
                return player
        return None

    def healthy_players_count(self):
        return sum(1 for p in self.players.values() if not p.infected)

    def is_adjacent_or_same(self, x1, y1, x2, y2):
        return abs(x1 - x2) <= 1 and abs(y1 - y2) <= 1


    #check for left, right, up, down, and diagonals
    async def update_infections(self):
        
        offsets = [(-1,0),(1,0),(0,-1),(0,1),(-1,-1),(-1,1),(1,-1),(1,1)]

        infected_players = [p for p in self.players.values() if p.infected]

        # collect ids of players that should become infected
        to_infect_ids: set[str] = set()

        for p in infected_players:
            for dx, dy in offsets:
                nx = p.x_coordinate + dx
                ny = p.y_coordinate + dy
                if not (0 <= nx < GRID_SIZE and 0 <= ny < GRID_SIZE):
                    continue
                other = self.get_player_at_position(nx, ny)
                if other and not other.infected and not other.is_shielded():
                    to_infect_ids.add(other.id)
                    p.score += 50

        # now apply infections (this prevents chain infections within same cycle)
        newly_infected: list[Player] = []
        for pid in to_infect_ids:
            other = self.players.get(pid)
            if other and not other.infected:
                other.infected = True
                newly_infected.append(other)

        # broadcast everyone who just became infected
        for infected_player in newly_infected:
            await self.broadcast({
                'player_data': {
                    'player_id': infected_player.id,
                    'x_coordinate': infected_player.x_coordinate,
                    'y_coordinate': infected_player.y_coordinate,
                    'infected': infected_player.infected,
                    'score': infected_player.score,
                    'username': infected_player.username,
                }
            })

        if len(self.players) <= 2:
            cnt = 1
        else:
            cnt = 2
        if self.healthy_players_count() < cnt:
            await self.end_game()


    async def move_player(self, player:Player, direction:str):

        if player.frozen_until and time.time() < player.frozen_until:
            return  # player is frozen, cannot move
        
        movement = {'left': (-1,0),
                    'right': (1,0),
                    'up': (0,-1),
                    'down': (0,1)
                    }
        
        if direction not in movement:
            return
        
        dx, dy = movement[direction]
        new_x = player.x_coordinate + dx
        new_y = player.y_coordinate + dy

        if not (0 <= new_x < GRID_SIZE and 0<= new_y < GRID_SIZE):
            return 
        
        if self.is_position_occupied(new_x, new_y):
            return
        
        # Prevent infected players from moving onto collectibles
        if player.infected and (new_x, new_y) in self.collectibles:
            return
        
        player.x_coordinate = new_x
        player.y_coordinate = new_y
    
        # Check if player collected a collectible
        await self.check_collectible_collection(player)
    
        # broadcast the moving player's new position/status
        await self.broadcast({
            'player_data': {
                'player_id': player.id,
                'x_coordinate': player.x_coordinate,
                'y_coordinate': player.y_coordinate,
                'infected': player.infected,
                'score': player.score,
                'username': player.username,
                'shield_active': player.shield_active,
            }})

        await self.update_infections()


    async def broadcast(self, message:dict):
        disconnected = []
        for player_id, player in self.players.items():
            try:
                await player.websocket.send_json(message)
            except Exception:
                disconnected.append(player_id)
        
        for p_id in disconnected:
            self.remove_player(p_id)


    async def start_game(self):
        if self.status != "waiting":
            return
        
        self.status = "in_progress"
        self.current_round += 1
        self.collectibles = {}  # Reset collectibles for new round
        self.freeze_active = False
        self.freeze_end_time = None
        
        if len(self.players) ==2:
            self.total_rounds = 2

        placed_positions = []

        # reset all players to healthy and score to 0, and optionally reposition them randomly
        for p in self.players.values():
            p.infected = False
            p.shield_active = False
            p.shield_end_time = None
            while True:
                x = random.randint(0, GRID_SIZE-1)
                y = random.randint(0, GRID_SIZE-1)

                valid = True
                for (px, py) in placed_positions:
                    if self.is_adjacent_or_same(x, y, px, py):
                        valid = False
                        break

                if valid:
                    p.x_coordinate = x
                    p.y_coordinate = y
                    placed_positions.append((x, y))
                    break

        if self.players:
            infected_player = random.choice(list(self.players.values()))
            infected_player.infected = True

        await self.broadcast({
            "type": "game_start",
            "round": self.current_round,
            "players": [{
                'player_id': p.id,
                'x_coordinate': p.x_coordinate,
                'y_coordinate': p.y_coordinate,
                'infected': p.infected,
                'score': p.score,
                'username': p.username,
                'shield_active': p.shield_active
            } for p in self.players.values()]
        })

        await self.broadcast({
            "type": "round_starting",
            "round": self.current_round  
        })

        await asyncio.sleep(2)  # 2-second “round starting” message

        if not self._game_timer_task or self._game_timer_task.done():
            self._game_timer_task = asyncio.create_task(self._run_game_timer())
        
        if not self._collectible_spawner_task or self._collectible_spawner_task.done():
            self._collectible_spawner_task = asyncio.create_task(self._run_collectible_spawner())

    async def _run_game_timer(self):
        start_time = time.time()
        end_time = start_time + GAME_DURATION
        
        try:
            while self.status == "in_progress":
                remaining_time = int(end_time - time.time())
                if remaining_time <= 0:
                    break
                    
                # also check for any shield expirations and broadcast updates
                for p in self.players.values():
                    # calling update_shield will clear flags if expired
                    was_shielded = p.shield_active
                    p.update_shield()
                    if was_shielded and not p.shield_active:
                        # tell clients to remove shield
                        await self.broadcast({
                            'player_data': {
                                'player_id': p.id,
                                'x_coordinate': p.x_coordinate,
                                'y_coordinate': p.y_coordinate,
                                'infected': p.infected,
                                'score': p.score,
                                'username': p.username,
                                'shield_active': p.shield_active,
                            }
                        })
                
                await self.broadcast({
                    "type": "timer",
                    "remaining_time":remaining_time,
                    })
                if remaining_time <= 0:
                    break
                await asyncio.sleep(1)

            if self.status == "in_progress":
                await self.end_game()
        
        except asyncio.CancelledError:
            pass


    async def _run_collectible_spawner(self):
        """Spawn collectibles every 20 seconds, starting after 10 seconds into the round"""
        try:
            # Wait for 10 seconds before first spawn
            await asyncio.sleep(COLLECTIBLE_SPAWN_DELAY)
            
            while self.status == "in_progress":
                if self.collectibles:
                    self.collectibles.clear()
                    await self.broadcast({
                        'type': 'collectibles_update',
                        'collectibles': []
                    })

                # Spawn random collectibles
                count = random.randint(2, 3) 
                
                for _ in range(count):
                    # Find a random empty position
                    while True:
                        x = random.randint(0, GRID_SIZE - 1)
                        y = random.randint(0, GRID_SIZE - 1)
                        
                        # Check if position is empty (no player, no collectible)
                        if not self.is_position_occupied(x, y) and (x, y) not in self.collectibles:
                            break
                    
                    collectible_type = random.choices(
                        list(COLLECTIBLE_WEIGHTS.keys()),
                        weights=list(COLLECTIBLE_WEIGHTS.values()),
                        k=1
                    )[0]
                    self.collectibles[(x, y)] = collectible_type
                
                await self.broadcast({
                    'type': 'collectibles_update',
                    'collectibles': [
                        {'x': pos[0], 'y': pos[1], 'type': ctype}
                        for pos, ctype in self.collectibles.items()
                    ]
                })
                
                # Wait until next spawn time
                await asyncio.sleep(COLLECTIBLE_SPAWN_INTERVAL)
        
        except asyncio.CancelledError:
            pass

    async def check_collectible_collection(self, player: Player):
        """Check if player is on a collectible and apply its effect"""

        if player.infected:
                return  # Infected players cannot collect items
        
        pos = (player.x_coordinate, player.y_coordinate)
        
        if pos  not in self.collectibles:
            return
        
        collectible_type = self.collectibles[pos]

        if collectible_type == 'red_wall':
            if not player.infected and not player.is_shielded():
                player.infected = True

                for p in self.players.values():
                    if p.infected and p.id != player.id:
                        p.score += RED_WALL_POINTS
        
        elif collectible_type == 'shield':
            # Activate shield for the player
            player.activate_shield(SHIELD_DURATION)
            player.score += SHIELD_POINTS
            await self.broadcast({
                'type': 'player_shield_activated',
                'player_id': player.id,
                'duration': SHIELD_DURATION
            })
        
        elif collectible_type == 'freeze':
            # Freeze all infected players
            for p in self.players.values():
                if p.infected:
                    p.frozen_until = time.time() + FREEZE_DURATION

            player.score += FREEZE_POINTS
            await self.broadcast({
                'type': 'freeze_activated',
                'duration': FREEZE_DURATION
            })

        elif collectible_type == 'score_booster':
            player.score += 50
        
        # Remove the collected collectible
        del self.collectibles[pos]

        # Broadcast updated player score/state
        await self.broadcast({
            'player_data': {
                'player_id': player.id,
                'x_coordinate': player.x_coordinate,
                'y_coordinate': player.y_coordinate,
                'infected': player.infected,
                'score': player.score,
                'username': player.username,
                'shield_active': player.shield_active,
            }
        })
        
        # Broadcast updated collectibles
        await self.broadcast({
            'type': 'collectibles_update',
            'collectibles': [
                {'x': p[0], 'y': p[1], 'type': ctype}
                for p, ctype in self.collectibles.items()
            ]
        })

    async def end_game(self):
        # Cancel timer safely if it’s still running
        if self._game_timer_task and not self._game_timer_task.done():
            self._game_timer_task.cancel()
            try:
                await self._game_timer_task
            except asyncio.CancelledError:
                pass

        self._game_timer_task = None    

        # Cancel collectible spawner if it's still running
        if self._collectible_spawner_task and not self._collectible_spawner_task.done():
            self._collectible_spawner_task.cancel()
            try:
                await self._collectible_spawner_task
            except asyncio.CancelledError:
                pass
        
        self._collectible_spawner_task = None   

        if self.status != "in_progress":
            return
        self.status = "finished"

        if self.current_round < self.total_rounds:
            self.status = "waiting"  # prepare for next round
            await self.start_game()
        else:

            await asyncio.sleep(2)  # 2-second wait before showing results
            winner = max(self.players.values(), key=lambda p: p.score)
            
            result = [{
                        "player_id" : player.id,
                        "score": player.score,
                        "infected": player.infected,
                        "username": player.username,
                    } for player in self.players.values()]
            
            await self.broadcast({
                    "type": "game_end",
                    "result": result,
                    "winner": {
                        "player_id": winner.id,
                        "score": winner.score,
                        "username": winner.username
                    }
            })  

