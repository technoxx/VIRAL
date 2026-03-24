import time
import uuid, random, asyncio
from .player import Player
from .constants import *

class Room:
    def __init__(self, code:str = None, creator: Player = None) -> None:
        self.id = uuid.uuid4().hex[:8]
        self.code = code  # None for random room
        self.creator = creator  # None for random room
        self.status = "waiting"    # allowed values: waiting, in_progress, finished
        self.players : dict[str, Player] = {}   # {player_1_id : Player(), player_2_id : Player()}
        self._countdown_task: asyncio.Task | None = None
        self._game_timer_task: asyncio.Task | None = None
        self._starting = False
        self._ending = False
        self.current_round = 0
        self.total_rounds = 3
        self.countdown_duration = 30
        self.initial_infected_history: set[str] = set()
        self._collectible_spawner_task: asyncio.Task | None = None
        self.collectibles: dict = {}  # {(x, y): 'shield' or 'freeze'}

    def is_room_ready(self):
        no_of_players = len(self.players)
        return no_of_players >= MIN_PLAYERS
    
    def is_room_full(self):
        return len(self.players) >= MAX_PLAYERS
    
    def is_room_empty(self):
        return len(self.players) == 0
    
    def is_room_joinable(self):
        return self.status == "waiting" and not self.is_room_full()
    
    def is_position_occupied(self, x, y):
        return any(player.x_coordinate == x and player.y_coordinate == y for player in self.players.values())
    
    
    async def add_player(self, player:Player):
        player.room_id = self.id
        self.players[player.id] = player

        await self.broadcast({
            "type": "player_count",
            "count": len(self.players),
        })

        if len(self.players) == 1 and self.status == "waiting":
            self.countdown_duration = 30
            if not self.code:
                if self._countdown_task and not self._countdown_task.done():
                    return
                
                self._countdown_task = asyncio.create_task(self._run_countdown_timer())

        if self.status == "waiting" and self.is_room_ready():
            self.countdown_duration = 10


    async def _run_countdown_timer(self):

        try:
            while self.status == "waiting":
                remaining_time = self.countdown_duration
                while remaining_time>0 and self.status == "waiting":
                    await self.broadcast({
                        "type": "countdown_timer",
                        "remaining_time":remaining_time,
                        })
                    await asyncio.sleep(1)
                    remaining_time -= 1

                    if self.is_room_ready() and remaining_time > 20:
                        remaining_time = self.countdown_duration
                
                if not self.is_room_ready():
                    for p in self.players.values():
                        await p.websocket.send_json({
                            "type": "no_players_found",
                            "message": "No players found at the moment"
                        })

                    # remove players from room
                    for p in list(self.players.values()):
                        p.room_id = None

                    self.players.clear()
                    return
                
                await self.start_game()
                return
        
        except asyncio.CancelledError:
            pass


    def remove_player(self, player_id:str):
        if player_id in self.players:
            self.players[player_id].room_id = None
            del self.players[player_id]

        self.initial_infected_history.discard(player_id)

        asyncio.create_task(self.broadcast({
            "type": "player_count",
            "count": len(self.players),
        }))

        if self.status == "in_progress" and not self._ending and len(self.players) < MIN_PLAYERS:
            asyncio.create_task(self.end_game())

    def get_player_at_position(self, x, y):
        for player in self.players.values():
            if player.x_coordinate == x and player.y_coordinate == y:
                return player
        return None

    def healthy_players_count(self):
        return sum(1 for p in self.players.values() if not p.infected)

    def is_adjacent_or_same(self, x1, y1, x2, y2):
        return abs(x1 - x2) <= 1 and abs(y1 - y2) <= 1


    #check for left, right, up, down
    async def update_infections(self):
        
        offsets = [(-1,0),(1,0),(0,-1),(0,1)]

        infected_players = [p for p in self.players.values() if p.infected]

        # if frozen, can't infect
        for player in infected_players:
            if player.frozen_until and time.time() < player.frozen_until:
                return
        
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
                    p.score += SPREAD_INFECTION_POINTS

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

        now = time.time()
        if now - player.last_move_time < MOVE_COOLDOWN:
            return  # ignore extra inputs
        
        # RATE LIMIT CHECK
        if self.is_rate_limited(player):
            return # ignore

        player.last_move_time = now

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

    
    def is_rate_limited(self, player: Player, limit=20, window=1.0):
        now = time.time()

        # Remove timestamps older than the window
        while player.move_timestamps and now - player.move_timestamps[0] > window:
            player.move_timestamps.popleft()

        if len(player.move_timestamps) >= limit:
            return True

        player.move_timestamps.append(now)
        return False


    async def broadcast(self, message:dict):
        disconnected = []
        for player_id, player in list(self.players.items()):
            try:
                await player.websocket.send_json(message)
            except Exception:
                disconnected.append(player_id)
        
        for p_id in disconnected:
            self.remove_player(p_id)


    async def start_game(self):
        if self.status != "waiting" or self._starting:
            return
        
        self._starting = True
        self._ending = False
        self.status = "in_progress"
        self.current_round += 1
        self.collectibles = {}  # Reset collectibles for new round
        
        if len(self.players) == 2:
            self.total_rounds = 2

        placed_positions = []

        # reset all players to healthy, and optionally reposition them randomly
        for p in self.players.values():
            p.infected = False
            p.shield_active = False
            p.shield_end_time = None
            p.frozen_until = None
            for _ in range(50):
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
            eligible_players = [
                p for p in self.players.values()
                if p.id not in self.initial_infected_history
            ]

            if not eligible_players:
                self.initial_infected_history.clear()
                eligible_players = list(self.players.values())

            infected_player = random.choice(eligible_players)
            infected_player.infected = True
            self.initial_infected_history.add(infected_player.id)

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

        self._starting = False

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
                
                await asyncio.sleep(1)

            if self.status == "in_progress":
                await self.end_game()
        
        except asyncio.CancelledError:
            pass


    async def _run_collectible_spawner(self):
        try:
            
            while self.status == "in_progress":
                # Spawn random collectibles
                num_players = len(self.players)
                if num_players == 2:
                    count = random.randint(5,10)
                else:  # 3 or 4 players
                    count = random.randint(3, 7)

                while True:
                    spawned_types = random.choices(
                        list(COLLECTIBLE_WEIGHTS.keys()),
                        weights=list(COLLECTIBLE_WEIGHTS.values()),
                        k=count
                    )
                    # if all types are the same, redraw
                    if len(set(spawned_types)) > 1 or count == 1:
                        break
                
                for ctype in spawned_types:
                    # Find a random empty position
                    while True:
                        x = random.randint(0, GRID_SIZE - 1)
                        y = random.randint(0, GRID_SIZE - 1)
                        
                        # Check if position is empty (no player, no collectible)
                        if not self.is_position_occupied(x, y) and (x, y) not in self.collectibles:
                            break
            
                    self.collectibles[(x, y)] = {
                        'type': ctype,
                        'expires_at': time.time() + COLLECTIBLE_LIFETIME
                    }
                
                await self.broadcast({
                    'type': 'collectibles_update',
                    'collectibles': [
                        {'x': pos[0], 'y': pos[1], 'type': data["type"]}
                        for pos, data in self.collectibles.items()
                    ]
                })
                
                # Wait until next spawn time
                await asyncio.sleep(COLLECTIBLE_SPAWN_INTERVAL)

                # Remove expired collectibles individually
                now = time.time()
                expired = [pos for pos, data in self.collectibles.items() if data['expires_at'] <= now]
                for pos in expired:
                    del self.collectibles[pos]

                if expired:
                    await self.broadcast({
                        'type': 'collectibles_update',
                        'collectibles': [
                            {'x': pos[0], 'y': pos[1], 'type': data['type']}
                            for pos, data in self.collectibles.items()
                        ]
                    })
        
        except asyncio.CancelledError:
            pass

    async def check_collectible_collection(self, player: Player):
        """Check if player is on a collectible and apply its effect"""

        if player.infected:
                return  # Infected players cannot collect items
        
        pos = (player.x_coordinate, player.y_coordinate)
        
        collectible = self.collectibles.pop(pos, None)
        if not collectible:
            return
        collectible_type = collectible['type'] 

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
            player.score += BOOSTER_POINTS
        

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
                {'x': p[0], 'y': p[1], 'type': data['type']}
                for p, data in self.collectibles.items()
            ]
        })

    async def end_game(self):
        if self._ending or self.status != "in_progress":
            return

        self._ending = True
        # Cancel timer safely if it’s still running
        if self._collectible_spawner_task and not self._collectible_spawner_task.done():
            self._collectible_spawner_task.cancel()
            try:
                await self._collectible_spawner_task
            except asyncio.CancelledError:
                pass
        
        self._collectible_spawner_task = None 

        if self._game_timer_task and not self._game_timer_task.done():
            self._game_timer_task.cancel()
            try:
                await self._game_timer_task
            except asyncio.CancelledError:
                pass

        self._game_timer_task = None    

        if self.status != "in_progress":
            return
        
        self.status = "finished"

        if not self.is_room_ready():
            await asyncio.sleep(2)
            await self.broadcast({
                "type": "game_end",
                "message": "Not enough players to continue."
            })
            return
        
        # Reward players who survived the round healthy
        healthy_players = [p for p in self.players.values() if not p.infected]

        # If exactly one healthy player → last survivor
        if len(healthy_players) == 1:
            last_survivor = healthy_players[0]
            last_survivor.score += HEALTHY_SURVIVAL_POINTS + LAST_SURVIVOR_BONUS

        # If multiple survivors (timer ended)
        else:
            for p in healthy_players:
                p.score += HEALTHY_SURVIVAL_POINTS

        if self.current_round < self.total_rounds:
            self.status = "waiting"  # prepare for next round
            await self.start_game()
        else:

            if not self.players:
                return

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

