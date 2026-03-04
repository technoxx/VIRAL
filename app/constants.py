GRID_SIZE = 15
MIN_PLAYERS = 2
MAX_PLAYERS = 4
GAME_DURATION = 90  # in seconds
COUNTDOWN_DURATION = 10  # in seconds
TOTAL_ROUNDS = 3

# Collectible settings
COLLECTIBLE_SPAWN_INTERVAL = 10  # spawn every 10 seconds
COLLECTIBLE_SPAWN_DELAY = 5  # wait 10 seconds before first spawn
SHIELD_DURATION = 5  # seconds of immunity
FREEZE_DURATION = 5  # seconds all infected are frozen
SHIELD_POINTS = 10
FREEZE_POINTS = 15
RED_WALL_POINTS = 20
COLLECTIBLE_WEIGHTS = {
    'shield': 3,
    'freeze': 3,
    'red_wall': 5,
    'score_booster': 2,
}
