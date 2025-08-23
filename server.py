import json
import os
import random
import asyncio
from aiohttp import web
import aiohttp_cors

# --- Configuration ---
DATABASE_FILE = 'database.json'
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
            return data
    except (FileNotFoundError, json.JSONDecodeError):
        return {'users': {}, 'leaderboard': []}

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

def create_tictactoe_game(challenger_id, opponent_id):
    """Initialize a Tic Tac Toe game state on the server."""
    game_id = f"game_{random.randint(1000, 9999)}"
    
    challenger_name = connected_clients[challenger_id]['name']
    opponent_name = connected_clients[opponent_id]['name']

    # Server decides who is X and who is O. Challenger is always X.
    GAMES_IN_PROGRESS[game_id] = {
        "type": "tictactoe",
        "players": {
            challenger_id: {"ws": connected_clients[challenger_id]['ws'], "sign": "X"},
            opponent_id: {"ws": connected_clients[opponent_id]['ws'], "sign": "O"}
        },
        "board": [None] * 9,
        "turn": "X" # X always starts first
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

                # --- LOBBY/AUTH ACTIONS ---
                if action == "signup":
                    phone_number = message.get("phone_number")
                    name = message.get("name")
                    db = load_data()
                    if phone_number not in db['users']:
                        db['users'][phone_number] = {
                            "name": name, "coins": 100, "history": []
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

                    if opponent_id in connected_clients and opponent_id != challenger_id:
                        player_challenges[challenger_id] = {'opponent_id': opponent_id, 'game_type': game_type}
                        opponent_ws = connected_clients[opponent_id]['ws']
                        await opponent_ws.send_str(json.dumps({
                            "action": "challenge_received",
                            "challenger_name": connected_clients[challenger_id]['name'],
                            "game_type": game_type,
                            "challenger_id": challenger_id
                        }))
                    else:
                        await ws.send_str(json.dumps({"action": "challenge_failed", "reason": "Opponent not available."}))

                elif action == "accept_challenge":
                    challenger_id = message.get("challenger_id")
                    opponent_id = message.get("opponent_id")
                    
                    if challenger_id in player_challenges and player_challenges[challenger_id]['opponent_id'] == opponent_id:
                        game_id, challenger_name, opponent_name = create_tictactoe_game(challenger_id, opponent_id)
                        
                        # Tell both clients they've been matched and give them their sign
                        challenger_ws = connected_clients[challenger_id]['ws']
                        if not challenger_ws.closed:
                            await challenger_ws.send_str(json.dumps({
                                "action": "match_found",
                                "game_id": game_id,
                                "opponent_name": opponent_name,
                                "your_sign": "X",
                                "turn": "X" # X goes first
                            }))
                        
                        opponent_ws = connected_clients[opponent_id]['ws']
                        if not opponent_ws.closed:
                            await opponent_ws.send_str(json.dumps({
                                "action": "match_found",
                                "game_id": game_id,
                                "opponent_name": challenger_name,
                                "your_sign": "O",
                                "turn": "X" # X goes first
                            }))

                        del player_challenges[challenger_id]
                    else:
                        await ws.send_str(json.dumps({"action": "challenge_failed", "reason": "Challenge expired or invalid."}))

                # --- GAME ACTIONS ---
                elif action == "game_action":
                    game_id = message.get("game_id")
                    player_id = message.get("player_id")
                    move_index = message.get("move_index")

                    if game_id in GAMES_IN_PROGRESS:
                        game = GAMES_IN_PROGRESS[game_id]
                        player_sign = game["players"][player_id]["sign"]

                        # Validate the move
                        if game["turn"] == player_sign and game["board"][move_index] is None:
                            game["board"][move_index] = player_sign
                            game["turn"] = "O" if player_sign == "X" else "X"

                            winner = check_tictactoe_winner(game["board"])

                            # Broadcast the move and new game state to both players
                            for pid, pdata in game["players"].items():
                                if not pdata["ws"].closed:
                                    await pdata["ws"].send_str(json.dumps({
                                        "action": "move_made",
                                        "index": move_index,
                                        "symbol": player_sign,
                                        "next_turn": game["turn"],
                                        "winner": winner
                                    }))

                            # If game is over, remove it
                            if winner:
                                # Save game result here if needed
                                del GAMES_IN_PROGRESS[game_id]
                    
                elif action == "ping":
                    await ws.send_str(json.dumps({"action": "pong"}))
    
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
                            "action": "game_ended",
                            "message": f"{opponent_name} has disconnected. You win!",
                            "winner": game_data["players"][opponent_id]["sign"]
                        }))
                    
                    del GAMES_IN_PROGRESS[game_id]
                    break
            
            del connected_clients[user_id]

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
