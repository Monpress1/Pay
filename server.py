import json
import os
import random
import asyncio
from aiohttp import web
import aiohttp_cors

# --- Configuration ---
DATABASE_FILE = 'database.json'
ADMIN_SESSIONS = set()
GAMES_IN_PROGRESS = {}
connected_clients = {}
player_challenges = {}

# --- Utility Functions ---
def load_data():
    try:
        with open(DATABASE_FILE, 'r') as f:
            data = json.load(f)
            if 'users' not in data: data['users'] = {}
            if 'leaderboard' not in data: data['leaderboard'] = []
            if 'admin_chat' not in data: data['admin_chat'] = []
            return data
    except (FileNotFoundError, json.JSONDecodeError):
        return {'users': {}, 'leaderboard': [], 'admin_chat': []}

def save_data(data):
    with open(DATABASE_FILE, 'w') as f:
        json.dump(data, f, indent=4)

async def broadcast_online_players():
    while True:
        online_list = [
            {'id': user_id, 'name': client['name']}
            for user_id, client in connected_clients.items()
        ]
        message = {"action": "users_online", "players": online_list}
        
        for client in connected_clients.values():
            if not client['ws'].closed:
                await client['ws'].send_str(json.dumps(message))
        
        await asyncio.sleep(10)

async def challenge_timeout(challenger_id, opponent_id):
    await asyncio.sleep(15)
    if challenger_id in player_challenges and player_challenges[challenger_id]['opponent_id'] == opponent_id:
        challenger_ws = connected_clients.get(challenger_id, {}).get('ws')
        opponent_ws = connected_clients.get(opponent_id, {}).get('ws')
        
        if challenger_ws and not challenger_ws.closed:
            await challenger_ws.send_str(json.dumps({
                "action": "challenge_timeout",
                "opponent_name": connected_clients.get(opponent_id, {}).get('name')
            }))
        if opponent_ws and not opponent_ws.closed:
            await opponent_ws.send_str(json.dumps({
                "action": "challenge_timeout",
                "challenger_name": connected_clients.get(challenger_id, {}).get('name')
            }))
        
        if challenger_id in player_challenges:
            del player_challenges[challenger_id]

# --- Game Logic Helpers ---
def create_tictactoe_game(challenger_id, opponent_id):
    """Initialize a Tic Tac Toe game state."""
    game_id = f"game_{random.randint(1000, 9999)}"
    
    challenger_name = connected_clients[challenger_id]['name']
    opponent_name = connected_clients[opponent_id]['name']

    GAMES_IN_PROGRESS[game_id] = {
        "type": "tictactoe",
        "players": {
            challenger_id: {"ws": connected_clients[challenger_id]['ws'], "sign": None},
            opponent_id: {"ws": connected_clients[opponent_id]['ws'], "sign": None}
        },
        "board": [None] * 9,
        "turn": None # No initial turn, client will decide
    }

    return game_id, challenger_name, opponent_name

def check_tictactoe_winner(board):
    wins = [
        [0,1,2],[3,4,5],[6,7,8], # rows
        [0,3,6],[1,4,7],[2,5,8], # cols
        [0,4,8],[2,4,6]          # diagonals
    ]
    for a,b,c in wins:
        if board[a] and board[a] == board[b] == board[c]:
            return board[a]
    if all(board):
        return "draw"
    return None

# --- HTTP Handler ---
async def handle_status_check(request):
    return web.Response(text="Server is running and ready for WebSocket connections.")

# --- WebSocket Handler ---
async def websocket_handler(request):
    ws = web.WebSocketResponse()
    await ws.prepare(request)
    
    user_id = None
    
    try:
        async for msg in ws:
            if msg.type == web.WSMsgType.TEXT:
                try:
                    message = json.loads(msg.data)
                except json.JSONDecodeError:
                    continue
                
                action = message.get("action")
                game_id = message.get("game_id")

                # --- AUTH / LOBBY ---
                if action == "signup":
                    phone_number = message.get("phone_number")
                    name = message.get("name")
                    db = load_data()
                    if phone_number not in db['users']:
                        db['users'][phone_number] = {
                            "name": name,
                            "coins": 100,
                            "history": []
                        }
                        save_data(db)
                    user_id = phone_number
                    connected_clients[user_id] = {'ws': ws, 'name': db['users'][phone_number]['name']}
                    await ws.send_str(json.dumps({
                        "action": "login_success", 
                        "name": db['users'][phone_number]['name'], 
                        "coins": db['users'][phone_number]['coins'],
                        "user_id": user_id
                    }))

                elif action == "challenge_request":
                    challenger_id = message.get("challenger_id")
                    opponent_id = message.get("opponent_id")
                    game_type = message.get("game_type")

                    if opponent_id in connected_clients and opponent_id not in [v['opponent_id'] for v in player_challenges.values()]:
                        player_challenges[challenger_id] = {'opponent_id': opponent_id, 'game_type': game_type}
                        opponent_ws = connected_clients[opponent_id]['ws']
                        await opponent_ws.send_str(json.dumps({
                            "action": "challenge_received",
                            "challenger_name": connected_clients[challenger_id]['name'],
                            "game_type": game_type,
                            "challenger_id": challenger_id
                        }))
                        asyncio.create_task(challenge_timeout(challenger_id, opponent_id))
                    else:
                        await ws.send_str(json.dumps({"action": "challenge_failed", "reason": "Opponent not available."}))

                elif action == "accept_challenge":
                    challenger_id = message.get("challenger_id")
                    opponent_id = message.get("opponent_id")
                    
                    if challenger_id in player_challenges and player_challenges[challenger_id]['opponent_id'] == opponent_id:
                        game_type = player_challenges[challenger_id]['game_type']
                        
                        if game_type == "tictactoe":
                            game_id, challenger_name, opponent_name = create_tictactoe_game(challenger_id, opponent_id)
                            
                            # Notify Challenger
                            challenger_ws = connected_clients[challenger_id]['ws']
                            if not challenger_ws.closed:
                                await challenger_ws.send_str(json.dumps({
                                    "action": "match_found",
                                    "game_id": game_id,
                                    "game_type": "tictactoe",
                                    "opponent_name": opponent_name
                                }))
                            
                            # Notify Opponent
                            opponent_ws = connected_clients[opponent_id]['ws']
                            if not opponent_ws.closed:
                                await opponent_ws.send_str(json.dumps({
                                    "action": "match_found",
                                    "game_id": game_id,
                                    "game_type": "tictactoe",
                                    "opponent_name": challenger_name
                                }))

                        del player_challenges[challenger_id]
                    else:
                        await ws.send_str(json.dumps({"action": "challenge_failed", "reason": "Challenge expired or invalid."}))

                # --- GAME ACTIONS ---
                # A centralized point to forward game-related messages to the opponent
                elif action == "game_action" and game_id in GAMES_IN_PROGRESS:
                    game = GAMES_IN_PROGRESS[game_id]
                    player_id = message.get("player_id")
                    
                    # Find the opponent
                    if player_id in game['players']:
                        opponent_id = next(iter(p_id for p_id in game['players'] if p_id != player_id))
                        opponent_ws = connected_clients.get(opponent_id, {}).get('ws')

                        if opponent_ws and not opponent_ws.closed:
                            # Forward the entire message to the opponent
                            await opponent_ws.send_str(json.dumps(message))

                    # Process the message on the server (if needed)
                    if message.get("type") == "make_move":
                        move = message.get("move")
                        player_sign = message.get("player_sign")
                        
                        if move is not None:
                            index = move - 1 # Adjust for 0-based array
                            if game["board"][index] is None:
                                game["board"][index] = player_sign
                                
                                winner = check_tictactoe_winner(game["board"])

                                # Server-side check for winner (optional, but good practice)
                                if winner:
                                    # This is where the server can handle post-game logic like updating scores
                                    pass

                elif action == "game_ended":
                    game_id = message.get("game_id")
                    if game_id in GAMES_IN_PROGRESS:
                        del GAMES_IN_PROGRESS[game_id]
                
                elif action == "ping":
                    await ws.send_str(json.dumps({"action": "pong", "timestamp": message.get('timestamp')}))
    
    finally:
        if user_id in connected_clients:
            # Check if the user was in a game
            for game_id, game_data in GAMES_IN_PROGRESS.items():
                if user_id in game_data['players']:
                    opponent_id = next(iter(p_id for p_id in game_data['players'] if p_id != user_id))
                    opponent_ws = connected_clients.get(opponent_id, {}).get('ws')
                    
                    if opponent_ws and not opponent_ws.closed:
                        opponent_name = connected_clients[user_id]['name']
                        await opponent_ws.send_str(json.dumps({
                            "action": "game_action",
                            "game_id": game_id,
                            "type": "opponent_left",
                            "message": f"{opponent_name} has left the game."
                        }))
                    
                    del GAMES_IN_PROGRESS[game_id]
                    break
            
            del connected_clients[user_id]
        if ws in ADMIN_SESSIONS:
            ADMIN_SESSIONS.discard(ws)
    return ws

# --- Main Application Setup ---
async def main():
    app = web.Application()
    cors = aiohttp_cors.setup(app, defaults={"*": aiohttp_cors.ResourceOptions(
        allow_credentials=True, expose_headers="*", allow_headers="*", allow_methods="*"
    )})

    app.router.add_get('/', handle_status_check)
    resource = cors.add(app.router.add_resource('/ws'))
    resource.add_route('GET', websocket_handler)

    runner = web.AppRunner(app)
    await runner.setup()
    port = int(os.environ.get('PORT', 8080))
    site = web.TCPSite(runner, '0.0.0.0', port)
    
    asyncio.create_task(broadcast_online_players())

    try:
        await site.start()
        print(f"Server started on port {port}")
        await asyncio.Event().wait()
    except Exception as e:
        print(f"Error starting server: {e}")

if __name__ == '__main__':
    asyncio.run(main())

