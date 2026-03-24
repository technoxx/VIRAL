GRID_SIZE = 15
MIN_PLAYERS = 2
MAX_PLAYERS = 4
GAME_DURATION = 60  # in seconds
TOTAL_ROUNDS = 3
MOVE_COOLDOWN = 0.1  # seconds (10 moves/sec)

# Collectible settings
COLLECTIBLE_SPAWN_INTERVAL = 5  # spawn every 5 seconds
COLLECTIBLE_SPAWN_DELAY = 2  # wait 2 seconds before first spawn
COLLECTIBLE_LIFETIME = 7
SHIELD_DURATION = 7  # seconds of immunity
FREEZE_DURATION = 7  # seconds all infected are frozen
SHIELD_POINTS = 30
FREEZE_POINTS = 60
BOOSTER_POINTS = 50
RED_WALL_POINTS = 40 # given to infected players
HEALTHY_SURVIVAL_POINTS = 70
LAST_SURVIVOR_BONUS = 50
SPREAD_INFECTION_POINTS = 80
COLLECTIBLE_WEIGHTS = {
    'shield': 1.2,
    'freeze': 0.5,
    'red_wall': 6,
    'score_booster': 5,
}
