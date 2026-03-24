# VIRAL 

**Race, Spread, Survive** - A real-time multiplayer infection simulation game

<table>
<tr>
<td>
  <a href="images/Screenshot%202026-03-06%20211155.png">
    <img src="images/Screenshot%202026-03-06%20211155.png" width="200">
  </a>
</td>
<td>
  <a href="images/Screenshot%202026-03-06%20215901.png">
    <img src="images/Screenshot%202026-03-06%20215901.png" width="200">
  </a>
</td>
</tr>
<tr>
<td>
  <a href="images/Screenshot%202026-03-06%20214015.png">
    <img src="images/Screenshot%202026-03-06%20214015.png" width="200">
  </a>
</td>
<td>
  <a href="images/Screenshot%202026-03-06%20214856.png">
    <img src="images/Screenshot%202026-03-06%20214856.png" width="200">
  </a>
</td>
</tr>
</table>

## 🎮 About

VIRAL is an exciting real-time multiplayer game where players navigate a 15×15 grid, trying to avoid infection while collecting power-ups and scoring points. Built with modern web technologies, it features WebSocket-powered real-time gameplay for up to 4 players per room.

**Live Demo** 🎬

Try VIRAL right now in your browser!  

[▶️ Click to Play](https://viralgame.up.railway.app/)  

Note: This is a multiplayer game. To test it yourself, open the game in 2–4 browser tabs or different devices, and then join. But better to invite your friends and play together :D



## ✨ Features

- **Real-time Multiplayer**: Join random rooms or create custom rooms with room codes
- **Strategic Gameplay**: Move around the grid, collect power-ups, and spread infection
- **Player Avatars**: Unique identicon avatars used for each player
- **Power-up System**:
  - 🛡️ **Shield**: Temporary immunity from infection
  - ❄️ **Freeze**: Temporarily freeze all infected players
  - ⭐ **Score Booster**: Instant points
  - 🚧 **Red Wall**: Infects players if they step on it
- **Chat System**: Communicate with other players in real-time
- **Room Management**: Create private rooms or join public lobbies
- **Multiple Rounds**: 2-3 rounds per game depending on player count
- **Dynamic Collectibles**: Power-ups spawn randomly every 5 seconds after a 2-second delay
- **Advanced Scoring**: Points for survival, power-up collection, and infection spread

### Technical Features

- **Real-time WebSocket Communication**: Bidirectional messaging for instant game updates
- **Dynamic Collectible Spawning**: Power-ups spawn randomly every 5 seconds after initial delay
- **Round-based Gameplay**: Multiple rounds with fresh starts and randomized positioning
- **Player Persistence**: Tracks infection history to ensure fair initial infections
- **Responsive UI**: Modern CSS with custom properties and smooth animations
- **Error Handling**: Comprehensive error handling for network issues and invalid moves

### Backend Stability & Performance
The game server is designed to handle real-time multiplayer gameplay safely using asyncio.

- **Rate Limiting**: Prevents movement spam (20 moves/sec per player)
- **Movement Cooldowns**: Ensures smooth grid-based movement
- **Race Condition Protection**: Prevents duplicate game start/end, infection bugs, and shared  state conflicts using internal state flags (_starting, _ending)
- **Safe Async Handling**: WebSocket broadcasts and game loops are protected against concurrent updates

## 🎯 How to Play

### Objective
Navigate the 15×15 grid, avoid getting infected, collect power-ups, and score the highest points across multiple rounds!

### Game Mechanics

1. **Movement**: Use arrow keys to move up, down, left, or right
2. **Infection Spread**: Infection spreads to adjacent players
3. **Power-ups**: Walk over collectibles to activate special abilities
4. **Scoring**: Earn points by staying healthy, collecting items, and infecting others
5. **Rounds**: Multiple rounds with randomized starting positions and fresh collectible spawns
6. **Game End**: Game ends when only 1-2 healthy players remain or time runs out

### Power-ups Explained

- **🛡️ Shield (Green)**: 7 seconds of immunity + 30 points
- **❄️ Freeze (Blue)**: Freezes all infected players for 7 seconds + 60 points  
- **⭐ Score Booster (Gold)**: Instant 50 points
- **🚧 Red Wall (Red)**: Infects healthy players who touch it + 40 points to each infected player

### Scoring System

- **Healthy Survival**: 70 points for surviving a round as healthy
- **Last Survivor Bonus**: Additional 50 points for being the last healthy player
- **Infection Spread**: 80 points each time you infect another player
- **Power-up Collection**: Varies by power-up type

## 🛠️ Tech Stack

### Backend
- **FastAPI**: High-performance async web framework
- **WebSockets**: Real-time bidirectional communication
- **Python 3.8+**: Core language

### Frontend
- **HTML5/CSS3**: Modern responsive UI with custom CSS variables
- **JavaScript (ES6+)**: Client-side game logic and WebSocket handling
- **DiceBear API**: Dynamic player avatar generation
- **WebSocket API**: Real-time communication

### Deployment
- **Vercel**: Frontend
- **Railway**: FastAPI backend
- **Gunicorn/Uvicorn**: ASGI server
- **WebSocket API**: Real-time communication


## 🚀 Installation & Setup

### Prerequisites
- Python 3.8 or higher
- Git

### Local Development

1. **Clone the repository**
   ```bash
   git clone https://github.com/technoxx/viral-game.git
   cd viral-game
   ```

2. **Create a virtual environment**
   ```bash
   python -m venv venv
   # On Windows:
   venv\Scripts\activate
   # On macOS/Linux:
   source venv/bin/activate
   ```

3. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

4. **Run the development server**
   ```bash
   uvicorn app.main:app --reload
   ```

## 🎮 Game Controls

- **Arrow Keys**: Move your player (Up, Down, Left, Right)
- **Chat**: Type messages in the chat input and press Enter or click Send
- **Room Creation**: Create custom rooms with unique codes
- **Game Start**: Room creator can start the game when minimum players are ready

## 🏗️ Architecture

### Backend Structure
```
app/
├── main.py          # FastAPI app and WebSocket endpoints
├── room_manager.py  # Room creation and management
├── room.py          # Game room logic and state management
├── player.py        # Player model and mechanics
└── constants.py     # Game configuration and constants
```

### Frontend Structure
```
frontend/
├── index.html       # Main HTML structure and UI
├── index.css        # Styling with CSS custom properties
└── websocket.js     # Client-side game logic and WebSocket handling
```

**Have fun playing VIRAL! 🎮**
