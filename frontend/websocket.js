// Track all player positions and their data
const playerPositions = {};
const assignedAvatars = new Set();
let ws;
const playerData = {};   // stores { health, score, infected, name, shield_active } keyed by player_id
const collectibles = {}; // stores collectible positions: {(x,y): 'shield'|'freeze'}
let freezeActiveUntil = 0; // timestamp until which infected are frozen

// ── Screen visibility system  ──
function showScreen(screenId) {
    document.querySelectorAll('.screen').forEach(s => s.classList.remove('active'));
    const screen = document.getElementById(screenId);
    if (screen) screen.classList.add('active');
}

function getActiveScreen() {
    const active = document.querySelector('.screen.active');
    return active?.id || null;
}


// ── Build grid ──
function buildGrid() {
    const gridSize = 15;
    const grid = document.getElementById("grid");
    for (let y = 0; y < gridSize; y++) {
        for (let x = 0; x < gridSize; x++) {
            const cell = document.createElement("div");
            cell.className = "cell";
            cell.id = `cell-${x}-${y}`;
            grid.appendChild(cell);
        }
    }
}

function stringToColor(str) {
    let hash = 0;
    for (let i = 0; i < str.length; i++) {
        hash = str.charCodeAt(i) + ((hash << 5) - hash);
    }

    const hue = Math.abs(hash) % 360;

    return `hsl(${hue}, 90%, 55%)`;
}

function getAvatarForPlayer(player_id, size = 20) {
    const color = stringToColor(player_id);
    return `https://api.dicebear.com/9.x/identicon/png?seed=${encodeURIComponent(player_id)}&size=${size}&color=${color}`;
}

// Place Player on the grid
function place_player(player) {
    const id = player.player_id;

    // Clear old position
    if (playerPositions[id]) {
        const old = document.getElementById(`cell-${playerPositions[id].x}-${playerPositions[id].y}`);
        if (old) {
            old.className = "cell"; // reset classes
            old.innerHTML = "";     // remove avatar
        }
    }

    const cell = document.getElementById(`cell-${player.x_coordinate}-${player.y_coordinate}`);
    if (!cell) return;

    // Base classes for infected/healthy
    cell.classList.add("player");
    cell.classList.add(player.infected ? "infected" : "healthy");

    if (player.shield_active) cell.classList.add("shielded");
    if (player.infected && Date.now() < freezeActiveUntil) cell.classList.add("frozen");

    const avatarImg = document.createElement("img");
    avatarImg.className = "player-avatar";
    avatarImg.src = getAvatarForPlayer(player.player_id);
    avatarImg.alt = player.username;

    cell.innerHTML = "";
    cell.appendChild(avatarImg);

    playerPositions[id] = { x: player.x_coordinate, y: player.y_coordinate };
}

// ── Render collectibles on grid ──
function renderCollectibles(collectiblesArray) {
    // Clear all collectibles from grid
    Object.keys(collectibles).forEach(key => {
        const [x, y] = key.split(',').map(Number);
        const cell = document.getElementById(`cell-${x}-${y}`);
        if (cell) cell.classList.remove('shield', 'freeze', 'red_wall', 'score_booster');
    });

    // Clear old collectibles
    for (const key in collectibles) delete collectibles[key];
    
    // Render new collectibles
    if (collectiblesArray && Array.isArray(collectiblesArray)) {
        collectiblesArray.forEach(c => {
            const key = `${c.x},${c.y}`;
            collectibles[key] = c.type;
            const cell = document.getElementById(`cell-${c.x}-${c.y}`);
            if (cell) {
                cell.classList.add(c.type); // 'shield' or 'freeze'
            }
        });
    }
}

// ── Refresh left sidebar player list ──
function refreshPlayerPanel() {
    const players = Object.entries(playerData).map(([id, p]) => ({
        id,
        name:     p.name,
        score:    p.score,
        infected: p.infected,
    }));

    // Sort: healthy first, then by score descending
    players.sort((a, b) => {
        if (a.infected !== b.infected) return a.infected ? 1 : -1;
        return (b.score ?? 0) - (a.score ?? 0);
    });

    window.updatePlayers(players);
}

function sanitizeUsername(username) {
    return username.replace(/[^a-zA-Z0-9_.]/g, "");
}

function getUsername() {
    let username = document.getElementById("username-input").value.trim();
    const MAX_LENGTH = 20;
    if (username === "") return showError("Enter a username!");
    username = sanitizeUsername(username);

    if (username.length === 0) {
        showError("Username contains invalid characters!");
        return;
    }
    if (username.length > MAX_LENGTH) {
        showError(`Username must be under ${MAX_LENGTH} characters`);
        return;
    }
    showError("");
    return username;
}

// ── Update game screen and place players ──
function updatePlayersOnGrid(playersOrSingle) {
    // Convert single object to array if needed
    const players = Array.isArray(playersOrSingle) ? playersOrSingle : [playersOrSingle];

    // Update all player positions
    players.forEach(player => {
        if (!player) return;

        playerData[player.player_id] = {
            name: player.username,
            score: player.score ?? 0,
            infected: player.infected ?? false,
            shield_active: player.shield_active ?? false
        };

        place_player(player);
    });

    refreshPlayerPanel();
}

// ── Handle errors ──
function showError(msg) {
    // Detect which screen is visible
    const activeScreen = getActiveScreen();
    let errorDiv = null;

    if (activeScreen === 'lobby-screen') {
        errorDiv = document.getElementById("lobby-error");
    } else if (activeScreen === 'waiting-screen') {
        errorDiv = document.getElementById("waiting-error");
    } else {
        // No known screen visible; exit
        return;
    }

    if (!errorDiv) return;

    if (!msg) {
        errorDiv.style.display = "none";
        return;
    }

    errorDiv.innerText = msg;
    errorDiv.style.display = "block";
}

window.updatePlayers = function(players) {
    const list  = document.getElementById('player-list');
    const count = document.getElementById('player-count');
    if (!list) return;

    count.textContent = players.length;

    list.innerHTML = players.map(p => `
        <div class="player-card ${p.infected ? 'is-infected' : ''}">
            <div class="player-card-top">
                <div class="player-info">
                    <div class="player-avatar-small">
                        <img 
                        src="${getAvatarForPlayer(p.id, 40)}" 
                        alt="${p.name}" 
                        class="player-avatar-small-img"/>
                    </div>
                    <div class="player-name">${p.name}</div>
                    <div class="player-score">Score <span>${p.score ?? 0}</span></div>
                </div>
            </div>
        </div>
    `).join('');
};

window.joinRandomRoom = function() {
    const username = getUsername();
    if (!username) return;
    ws.send(JSON.stringify({ type: "join_random_room", username: username }));
    showError("");
}

window.createRoom = function() {
    const username = getUsername();
    if (!username) return;
    ws.send(JSON.stringify({ type: "create_room", username: username }));
    showError("");
}

window.joinRoom = function() {
    const username = getUsername();
    if (!username) return;
    const code = document.getElementById("room-code-input").value.trim();
    if (code === "") return showError("Enter a room code!");
    ws.send(JSON.stringify({ type: "join_room", code: code, username: username }));
    showError("");
}

window.startGame = function() {
    ws.send(JSON.stringify({ type: "start_game" }));
}

window.onload = function() {
    buildGrid();
    ws = new WebSocket("wss://viralgame.up.railway.app/ws");

    ws.onopen = function() {
        console.log("WebSocket connection established.");
    }

    ws.onclose = function() {
        console.log("WebSocket closed.");
    }

    ws.onerror = function(err) {
        console.warn('WebSocket error', err);
    }

    // Keyboard movement
    window.addEventListener("keydown", function(event) {
        const keys = {
            "ArrowUp":    "up",
            "ArrowDown":  "down",
            "ArrowLeft":  "left",
            "ArrowRight": "right",
        };
        if (keys[event.key]) {
            event.preventDefault();
            ws.send(JSON.stringify({ type: "move", direction: keys[event.key] }));
        }
    });

    ws.onmessage = function(event) {
        const data = JSON.parse(event.data);

        if (data.type === "room_created"){
            creatorId = data.creator_id;
            showScreen("waiting-screen");
            
            const info = document.getElementById("waiting-message");
            info.innerHTML = ""; // clear old messages
            const msg = document.createElement("div");
            msg.innerHTML = `Room code: <b>${data.code}</b> <br> Share with friends!`;
            info.appendChild(msg);
            // If we already know our player id, show start button for creator
            const startBtn = document.getElementById("start-game-btn");
            startBtn.style.display = "block";
        }

        else if (data.type === "room_joined") {
            showScreen("waiting-screen");

            const info = document.getElementById("waiting-message");
            info.innerHTML = "";

            const msg = document.createElement("div");
            msg.innerHTML = data.code
                ? `Waiting for creator of room ${data.code} to start the game.`
                : "Assigned a room! <br>Waiting for others to join...";

            info.appendChild(msg);

            //  Hide start button for non-creators
            const startBtn = document.getElementById("start-game-btn");
            if (startBtn) startBtn.style.display = "none";
        }

        else if (data.type === 'countdown_timer') {
            document.getElementById("countdown-timer").innerText = data.remaining_time;
        }

        // ── Chat ──
        else if (data.type === 'chat') {

            const log = document.getElementById("chat-log");
            const msg = document.createElement("div");
            const sender = playerData[data.username];
            msg.className = "message " + (sender?.infected ? "infected" : "player");
            const strong = document.createElement("strong");
            strong.textContent = data.username + ": ";
            msg.appendChild(strong);
            msg.appendChild(document.createTextNode(data.message));
            log.appendChild(msg);
            log.scrollTop = log.scrollHeight;
        }

        else if (data.type === "no_players_found") {
            // Go back to lobby
            showScreen("lobby-screen");

            const notification = document.createElement("div");
            notification.className = "notification no-players-found";
            notification.innerText = `⛈ No players available at the moment!`;
            document.body.appendChild(notification);
            
            setTimeout(() => notification.remove(), 2 * 1000);
        }

        // ── Player disconnected ──
        else if (data.type === 'player_disconnected') {
            const id = data.player_id;
            if (playerPositions[id]) {
                const cell = document.getElementById(`cell-${playerPositions[id].x}-${playerPositions[id].y}`);
                if (cell) cell.classList.remove('player', 'infected');
                delete playerPositions[id];
            }
            delete playerData[id];
            refreshPlayerPanel();
        }

        // ── Game start ──
        else if (data.type === 'game_start') {
            showScreen("game-screen");
            document.getElementById("round").innerText = data.round;
            // Clear all collectibles from grid
            Object.keys(collectibles).forEach(key => {
                const [x, y] = key.split(',').map(Number);
                const cell = document.getElementById(`cell-${x}-${y}`);
                if (cell) cell.classList.remove('shield', 'freeze', 'red_wall', 'score_booster');
            });

            // Clear old collectibles
            for (const key in collectibles) delete collectibles[key];
            
            updatePlayersOnGrid(data.players);
        }

        // ── Game end ──
        else if (data.type === 'game_end') {
            showScreen("result-screen");
            let resultText;
            if(!data.result){
                resultText = data.message;
            }else{
                const results = data.result;
                const winner  = data.winner;

                resultText = "🏆 WINNER\n";
                resultText += `${winner.username} wins with score ${winner.score}\n\n`;
                resultText += "Scoreboard:\n";

                results.forEach(p => {
                    resultText += `${p.username} - Score: ${p.score}\n`;
                });
            }
            document.getElementById("result-data").innerText = resultText;
        }

        // ── Timer ──
        else if (data.type === 'timer') {
            document.getElementById("timer").innerText = data.remaining_time;
        }

        else if (data.type === "round_starting") {
            const notification = document.createElement("div");
            notification.className = "notification round-start";
            notification.innerText = `⛈ Round ${data.round} !`;
            document.body.appendChild(notification);
            
            setTimeout(() => notification.remove(), 2 * 1000);
        }

        // ── Collectibles ──
        else if (data.type === 'collectibles_update') {
            renderCollectibles(data.collectibles);
        }

        else if (data.type === "player_count") {
            const counter = document.getElementById("room-player-count");
            if (counter) {
                const minPlayers = 2;
                counter.innerText = data.count;
                if (data.count >= minPlayers) {
                    counter.innerText += " \n Game is about to begin :)";
                }
            }
        }

        // Batched state update
        else if (data.type === 'state_update') {
            // Update all changed players in one pass
            if (data.players && data.players.length) {
                updatePlayersOnGrid(data.players);
            }

            // Collectibles
            if (data.collectibles) {
                renderCollectibles(data.collectibles);
            }

            // Shield activated for a player
            if (data.shield_event) {
                applyShieldActivated(data.shield_event.player_id, data.shield_event.duration);
            }

            // Freeze activated
            if (data.freeze_event) {
                applyFreezeActivated(data.freeze_event.duration);
            }
        }

        // Shield activated 
        else if (data.type === 'player_shield_activated') {
            applyShieldActivated(data.player_id, data.duration);
        }

        // Freeze activated
        else if (data.type === 'freeze_activated') {
            applyFreezeActivated(data.duration);
        }

        else if (data.type === 'error'){
            showError(data.message || "An unknown error occurred");
            return;
        }

        // Player position / state update
        if (data.player_data) {
            updatePlayersOnGrid(data.player_data);
        }
    };

    // Shield helper 
    function applyShieldActivated(player_id, duration) {
        const player = playerData[player_id];
        if (!player) return;
        player.shield_active = true;
        player.shield_remaining = duration;
        const pos = playerPositions[player_id];
        if (!pos) return;
        const cell = document.getElementById(`cell-${pos.x}-${pos.y}`);
        if (!player.infected && cell) {
            cell.classList.add('shielded');
            setTimeout(() => {
                player.shield_active = false;
                const c = document.getElementById(`cell-${playerPositions[player_id]?.x}-${playerPositions[player_id]?.y}`);
                if (c) c.classList.remove('shielded');
            }, duration * 1000);
        }
    }

    // Freeze helper 
    function applyFreezeActivated(duration) {
        const notification = document.createElement("div");
        notification.className = "notification freeze-activated";
        notification.innerText = `Freeze mode activated! All infected players cannot move.`;
        document.body.appendChild(notification);
        setTimeout(() => notification.remove(), 2 * 1000);

        freezeActiveUntil = Date.now() + duration * 1000;

        Object.entries(playerPositions).forEach(([pid, pos]) => {
            const p = playerData[pid];
            if (p && p.infected) {
                const cell = document.getElementById(`cell-${pos.x}-${pos.y}`);
                if (cell) cell.classList.add('frozen');
            }
        });

        setTimeout(() => {
            Object.entries(playerPositions).forEach(([pid, pos]) => {
                const cell = document.getElementById(`cell-${pos.x}-${pos.y}`);
                if (cell) cell.classList.remove('frozen');
            });
        }, duration * 1000);
    }

    // Send chat 
    window.send_mess = function() {
        const input = document.getElementById("input-field");
        const text  = input.value.trim();
        if (text !== "") {
            ws.send(JSON.stringify({ type: "chat", value: text }));
            input.value = "";
        }
    };

    // Also send on Enter key
    document.getElementById("input-field").addEventListener("keydown", function(e) {
        if (e.key === "Enter") window.send_mess();
    });
};