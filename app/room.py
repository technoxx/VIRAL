import time
import uuid, random, asyncio
from .player import Player
from .constants import *

class Room:
    def __init__(self, code:str = None, creator: Player = None) -> None:
        self.id = uuid.uuid4().hex[:8]
        self.code = code
        self.creator = creator
        self.status = "waiting"
        self.players: dict[str, Player] = {}
        self._countdown_task: asyncio.Task | None = None
        self._game_timer_task: asyncio.Task | None = None
        self._starting = False
        self._ending = False
        self.current_round = 0
        self.total_rounds = 3
        self.countdown_duration = 30
        self.initial_infected_history: set[str] = set()
        self._collectible_spawner_task: asyncio.Task | None = None
        self.collectibles: dict = {}
        # fast O(1) position lookup instead of O(n) scan on every move
        self._occupied_positions: set[tuple[int, int]] = set()

    #  Helpers

    def is_room_ready(self):
        return len(self.players) >= MIN_PLAYERS

    def is_room_full(self):
        return len(self.players) >= MAX_PLAYERS

    def is_room_empty(self):
        return len(self.players) == 0

    def is_room_joinable(self):
        return self.status == "waiting" and not self.is_room_full()

    def is_position_occupied(self, x, y):
        # O(1) set lookup instead of O(n) any() scan
        return (x, y) in self._occupied_positions

    def get_player_at_position(self, x, y):
        for player in self.players.values():
            if player.x_coordinate == x and player.y_coordinate == y:
                return player
        return None

    def healthy_players_count(self):
        return sum(1 for p in self.players.values() if not p.infected)

    def is_adjacent_or_same(self, x1, y1, x2, y2):
        return abs(x1 - x2) <= 1 and abs(y1 - y2) <= 1

    def _player_state(self, p: Player) -> dict:
        return {
            "player_id": p.id,
            "x_coordinate": p.x_coordinate,
            "y_coordinate": p.y_coordinate,
            "infected": p.infected,
            "score": p.score,
            "username": p.username,
            "shield_active": p.shield_active,
        }


    #  Broadcast
    async def broadcast(self, message: dict):
        if not self.players:
            return

        async def _send(player_id: str, player: Player):
            try:
                await player.websocket.send_json(message)
            except Exception:
                return player_id
            return None

        results = await asyncio.gather(
            *(_send(pid, p) for pid, p in list(self.players.items())),
            return_exceptions=False,
        )

        for player_id in results:
            if player_id is not None:
                self.remove_player(player_id)


    async def add_player(self, player: Player):
        player.room_id = self.id
        self.players[player.id] = player
        self._occupied_positions.add((player.x_coordinate, player.y_coordinate))

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
                while remaining_time > 0 and self.status == "waiting":
                    await self.broadcast({
                        "type": "countdown_timer",
                        "remaining_time": remaining_time,
                    })
                    await asyncio.sleep(1)
                    remaining_time -= 1

                    if self.is_room_ready() and remaining_time > 20:
                        remaining_time = self.countdown_duration

                if not self.is_room_ready():
                    for p in self.players.values():
                        await p.websocket.send_json({
                            "type": "no_players_found",
                            "message": "No players found at the moment",
                        })
                    for p in list(self.players.values()):
                        p.room_id = None
                    self.players.clear()
                    self._occupied_positions.clear()
                    return

                await self.start_game()
                return

        except asyncio.CancelledError:
            pass

    def remove_player(self, player_id: str):
        if player_id in self.players:
            p = self.players[player_id]
            self._occupied_positions.discard((p.x_coordinate, p.y_coordinate))
            p.room_id = None
            del self.players[player_id]

        self.initial_infected_history.discard(player_id)

        asyncio.create_task(self.broadcast({
            "type": "player_count",
            "count": len(self.players),
        }))

        if self.status == "in_progress" and not self._ending and len(self.players) < MIN_PLAYERS:
            asyncio.create_task(self.end_game())


    def is_rate_limited(self, player: Player, limit=20, window=1.0):
        now = time.time()
        while player.move_timestamps and now - player.move_timestamps[0] > window:
            player.move_timestamps.popleft()
        if len(player.move_timestamps) >= limit:
            return True
        player.move_timestamps.append(now)
        return False


    async def move_player(self, player: Player, direction: str):
        if self.status != "in_progress":
            return
        now = time.time()
        if now - player.last_move_time < MOVE_COOLDOWN:
            return
        if self.is_rate_limited(player):
            return
        player.last_move_time = now

        if player.frozen_until and time.time() < player.frozen_until:
            return

        movement = {
            "left": (-1, 0),
            "right": (1, 0),
            "up": (0, -1),
            "down": (0, 1),
        }
        if direction not in movement:
            return

        dx, dy = movement[direction]
        new_x = player.x_coordinate + dx
        new_y = player.y_coordinate + dy

        if not (0 <= new_x < GRID_SIZE and 0 <= new_y < GRID_SIZE):
            return
        if self.is_position_occupied(new_x, new_y):
            return
        if player.infected and (new_x, new_y) in self.collectibles:
            return

        # update position set atomically
        self._occupied_positions.discard((player.x_coordinate, player.y_coordinate))
        player.x_coordinate = new_x
        player.y_coordinate = new_y
        self._occupied_positions.add((new_x, new_y))

        collectible_event = await self._collect_item(player)
        
        newly_infected, game_should_end = self._compute_infections()

        for p in newly_infected:
            p.infected = True

        # one combined broadcast 
        payload: dict = {
            "type": "state_update",
            "players": [self._player_state(player)],
        }

        # Add any newly infected players
        for p in newly_infected:
            payload["players"].append(self._player_state(p))
            
        if collectible_event:
            payload.update(collectible_event)

        await self.broadcast(payload)

        if game_should_end:
            await self.end_game()

    def _compute_infections(self) -> tuple[list[Player], bool]:

        offsets = [(-1, 0), (1, 0), (0, -1), (0, 1)]
        infected_players = [p for p in self.players.values() if p.infected]

        # Frozen infected players cannot spread
        now = time.time()
        active_infected = [
            p for p in infected_players
            if not (p.frozen_until and now < p.frozen_until)
        ]

        to_infect_ids: set[str] = set()
        for p in active_infected:
            for dx, dy in offsets:
                nx, ny = p.x_coordinate + dx, p.y_coordinate + dy
                if not (0 <= nx < GRID_SIZE and 0 <= ny < GRID_SIZE):
                    continue
                other = self.get_player_at_position(nx, ny)
                if other and not other.infected and not other.is_shielded():
                    to_infect_ids.add(other.id)
                    p.score += SPREAD_INFECTION_POINTS

        newly_infected: list[Player] = []
        for pid in to_infect_ids:
            other = self.players.get(pid)
            if other and not other.infected:
                newly_infected.append(other)


        cnt = 1 if len(self.players) <= 2 else 2
        future_healthy = self.healthy_players_count() - len(newly_infected)
        game_should_end = future_healthy < cnt

        return newly_infected, game_should_end


    #  Collectibles                                                        
    async def _collect_item(self, player: Player) -> dict | None:
        if player.infected:
            return None

        pos = (player.x_coordinate, player.y_coordinate)
        collectible = self.collectibles.pop(pos, None)
        if not collectible:
            return None

        ctype = collectible["type"]
        extra: dict = {}

        if ctype == "red_wall":
            if not player.infected and not player.is_shielded():
                player.infected = True
                for p in self.players.values():
                    if p.infected and p.id != player.id:
                        p.score += RED_WALL_POINTS

        elif ctype == "shield":
            player.activate_shield(SHIELD_DURATION)
            player.score += SHIELD_POINTS
            extra["shield_event"] = {
                "player_id": player.id,
                "duration": SHIELD_DURATION,
            }

        elif ctype == "freeze":
            freeze_until = time.time() + FREEZE_DURATION
            for p in self.players.values():
                if p.infected:
                    p.frozen_until = freeze_until
            player.score += FREEZE_POINTS
            extra["freeze_event"] = {"duration": FREEZE_DURATION}

        elif ctype == "score_booster":
            player.score += BOOSTER_POINTS

        # Always attach the updated collectibles list
        extra["collectibles"] = [
            {"x": p[0], "y": p[1], "type": d["type"]}
            for p, d in self.collectibles.items()
        ]

        return extra if extra else None


    async def _run_collectible_spawner(self):
        try:
            while self.status == "in_progress":
                num_players = len(self.players)
                count = random.randint(7, 11) if num_players == 2 else random.randint(6, 10)

                while True:
                    spawned_types = random.choices(
                        list(COLLECTIBLE_WEIGHTS.keys()),
                        weights=list(COLLECTIBLE_WEIGHTS.values()),
                        k=count,
                    )
                    if len(set(spawned_types)) > 1 or count == 1:
                        break

                for ctype in spawned_types:
                    while True:
                        x = random.randint(0, GRID_SIZE - 1)
                        y = random.randint(0, GRID_SIZE - 1)
                        if not self.is_position_occupied(x, y) and (x, y) not in self.collectibles:
                            break
                    self.collectibles[(x, y)] = {
                        "type": ctype,
                        "expires_at": time.time() + COLLECTIBLE_LIFETIME,
                    }

                await self.broadcast({
                    "type": "collectibles_update",
                    "collectibles": [
                        {"x": pos[0], "y": pos[1], "type": data["type"]}
                        for pos, data in self.collectibles.items()
                    ],
                })

                await asyncio.sleep(COLLECTIBLE_SPAWN_INTERVAL)

                now = time.time()
                expired = [pos for pos, data in self.collectibles.items() if data["expires_at"] <= now]
                for pos in expired:
                    del self.collectibles[pos]

                if expired:
                    await self.broadcast({
                        "type": "collectibles_update",
                        "collectibles": [
                            {"x": pos[0], "y": pos[1], "type": data["type"]}
                            for pos, data in self.collectibles.items()
                        ],
                    })

        except asyncio.CancelledError:
            pass


    #  Game timer
    async def _run_game_timer(self):
        start_time = time.time()
        end_time = start_time + GAME_DURATION

        try:
            while self.status == "in_progress":
                remaining_time = int(end_time - time.time())
                if remaining_time <= 0:
                    break

                expired_shield_players = []
                for p in self.players.values():
                    was_shielded = p.shield_active
                    p.update_shield()
                    if was_shielded and not p.shield_active:
                        expired_shield_players.append(p)

                if expired_shield_players:
                    await self.broadcast({
                        "type": "state_update",
                        "players": [self._player_state(p) for p in expired_shield_players],
                    })

                await self.broadcast({
                    "type": "timer",
                    "remaining_time": remaining_time,
                })

                await asyncio.sleep(1)

            if self.status == "in_progress":
                await self.end_game()

        except asyncio.CancelledError:
            pass


    async def start_game(self):
        if self.status != "waiting" or self._starting:
            return

        self._starting = True
        self._ending = False
        self.status = "in_progress"
        self.current_round += 1
        self.collectibles = {}

        if len(self.players) == 2:
            self.total_rounds = 2

        placed_positions = []
        self._occupied_positions.clear()

        for p in self.players.values():
            p.infected = False
            p.shield_active = False
            p.shield_end_time = None
            p.frozen_until = None
            for _ in range(50):
                x = random.randint(0, GRID_SIZE - 1)
                y = random.randint(0, GRID_SIZE - 1)
                valid = all(
                    not self.is_adjacent_or_same(x, y, px, py)
                    for px, py in placed_positions
                )
                if valid:
                    p.x_coordinate = x
                    p.y_coordinate = y
                    placed_positions.append((x, y))
                    self._occupied_positions.add((x, y))
                    break

        if self.players:
            eligible = [p for p in self.players.values() if p.id not in self.initial_infected_history]
            if not eligible:
                self.initial_infected_history.clear()
                eligible = list(self.players.values())
            infected_player = random.choice(eligible)
            infected_player.infected = True
            self.initial_infected_history.add(infected_player.id)

        await self.broadcast({
            "type": "game_start",
            "round": self.current_round,
            "players": [self._player_state(p) for p in self.players.values()],
        })

        await self.broadcast({
            "type": "round_starting",
            "round": self.current_round,
        })

        await asyncio.sleep(2)

        if not self._game_timer_task or self._game_timer_task.done():
            self._game_timer_task = asyncio.create_task(self._run_game_timer())

        if not self._collectible_spawner_task or self._collectible_spawner_task.done():
            self._collectible_spawner_task = asyncio.create_task(self._run_collectible_spawner())

        self._starting = False


    async def end_game(self):
        if self._ending or self.status != "in_progress":
            return

        self._ending = True

        for task_attr in ("_collectible_spawner_task", "_game_timer_task"):
            task: asyncio.Task | None = getattr(self, task_attr)
            if task and not task.done():
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
            setattr(self, task_attr, None)

        if self.status != "in_progress":
            return

        self.status = "finished"

        if not self.is_room_ready():
            await asyncio.sleep(2)
            await self.broadcast({
                "type": "game_end",
                "message": "Not enough players to continue.",
            })
            return

        healthy_players = [p for p in self.players.values() if not p.infected]
        if len(healthy_players) == 1:
            healthy_players[0].score += HEALTHY_SURVIVAL_POINTS + LAST_SURVIVOR_BONUS
        else:
            for p in healthy_players:
                p.score += HEALTHY_SURVIVAL_POINTS

        if self.current_round < self.total_rounds:
            self.status = "waiting"
            await asyncio.sleep(2)
            await self.start_game()
        else:
            if not self.players:
                return

            await asyncio.sleep(2)
            winner = max(self.players.values(), key=lambda p: p.score)
            result = [
                {
                    "player_id": p.id,
                    "score": p.score,
                    "infected": p.infected,
                    "username": p.username,
                }
                for p in self.players.values()
            ]
            await self.broadcast({
                "type": "game_end",
                "result": result,
                "winner": {
                    "player_id": winner.id,
                    "score": winner.score,
                    "username": winner.username,
                },
            })