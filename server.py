import asyncio
import json
import os
import random
from datetime import datetime
from aiohttp import web
import aiohttp_cors

# --- Game-specific imports ---
from games.snake import SnakeGame
# You will add other imports here as you create the files, e.g.,
# from games.asteroids import AsteroidsGame
# from games.trivia import TriviaGame
# from games.drawing import DrawingGame
# from games.twotruths import TwoTruthsGame

# --- Configuration ---
DATABASE_FILE = 'database.json'
MATCHMAKING_QUEUE = []
ADMIN_SESSIONS = set()
GAMES_IN_PROGRESS = {}

# --- Utility Functions ---

def load_data():
    """Load data from the JSON file."""
    try:
        with open(DATABASE_FILE, 'r') as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {'users': {}, 'leaderboard': [], 'admin_chat': []}

def save_data(data):
    """Save data to the JSON file."""
    with open(DATABASE_FILE, 'w') as f:
        json.dump(data, f, indent=4)

async def broadcast(message):
    """Broadcast a message to all connected clients."""
    for client in connected_clients:
        await client.send_str(json.dumps(message))

# --- Matchmaking Logic ---

async def start_matchmaking_loop():
    """Continuously tries to match players in the queue."""
    while True:
        if len(MATCHMAKING_QUEUE) >= 2:
            player1 = MATCHMAKING_QUEUE.pop(0)
            player2 = MATCHMAKING_QUEUE.pop(0)

            game_id = f"game_{random.randint(1000, 9999)}"
            game_type = player1['game_type']
            
            # Create an instance of the appropriate game class
            game_instance = None
            if game_type == 'snake':
                game_instance = SnakeGame(player1['id'], player2['id'])
            # Add elif blocks for other games as you implement them
            
            if game_instance:
                GAMES_IN_PROGRESS[game_id] = {
                    'game_instance': game_instance,
                    'players': {
                        player1['id']: player1['ws'],
                        player2['id']: player2['ws']
                    },
                    'state': 'in_progress',
                    'start_time': datetime.now().isoformat()
                }

                await player1['ws'].send_str(json.dumps({
                    "action": "match_found",
                    "game_id": game_id,
                    "game_type": game_type,
                    "opponent": player2['name']
                }))
                await player2['ws'].send_str(json.dumps({
                    "action": "match_found",
                    "game_id": game_id,
                    "game_type": game_type,
                    "opponent": player1['name']
                }))
                print(f"Match found for {game_type}: {player1['name']} vs {player2['name']} (Game ID: {game_id})")
        await asyncio.sleep(5)

# --- WebSocket & Admin Handlers ---

connected_clients = set()

async def websocket_handler(request):
    """Handles WebSocket connections and messages."""
    ws = web.WebSocketResponse()
    await ws.prepare(request)
    connected_clients.add(ws)

    user_info = {'ws': ws, 'id': None, 'name': 'Guest'}
    is_admin = False

    try:
        async for msg in ws:
            if msg.type == web.WSMsgType.TEXT:
                message = json.loads(msg.data)
                action = message.get("action")

                if action == "login_admin":
                    if message.get("password") == "your_admin_password":
                        is_admin = True
                        ADMIN_SESSIONS.add(ws)
                        db = load_data()
                        await ws.send_str(json.dumps({
                            "action": "admin_auth_success",
                            "users": db['users'],
                            "admin_chat": db['admin_chat']
                        }))
                        print("Admin logged in.")
                    else:
                        await ws.send_str(json.dumps({"action": "auth_failed"}))
                        
                elif is_admin:
                    if action == "increase_coins":
                        user_id = message.get("user_id")
                        coins_to_add = message.get("coins")
                        db = load_data()
                        if user_id in db['users']:
                            db['users'][user_id]['coins'] += coins_to_add
                            save_data(db)
                            await ws.send_str(json.dumps({"action": "coins_updated", "user_id": user_id, "new_coins": db['users'][user_id]['coins']}))
                            print(f"Increased coins for {user_id} by {coins_to_add}.")
                    
                    elif action == "send_admin_message":
                        db = load_data()
                        chat_message = {
                            "sender": "Admin",
                            "message": message.get("message"),
                            "timestamp": datetime.now().isoformat()
                        }
                        db['admin_chat'].append(chat_message)
                        save_data(db)
                        await broadcast({"action": "new_admin_message", "message": chat_message})

                elif action == "signup":
                    phone_number = message.get("phone_number")
                    name = message.get("name")
                    db = load_data()
                    if phone_number not in db['users']:
                        db['users'][phone_number] = {
                            "name": name,
                            "coins": 100,
                            "history": []
                        }
                        user_info['id'] = phone_number
                        user_info['name'] = name
                        save_data(db)
                        await ws.send_str(json.dumps({"action": "signup_success", "name": name, "coins": 100}))
                        print(f"New user signed up: {name}")
                    else:
                        await ws.send_str(json.dumps({"action": "signup_failed", "reason": "User already exists"}))
                
                elif action == "join_matchmaking":
                    user_info['id'] = message.get('user_id')
                    user_info['name'] = message.get('name')
                    user_info['game_type'] = message.get('game_type')
                    MATCHMAKING_QUEUE.append(user_info)
                    await ws.send_str(json.dumps({"action": "matchmaking_started"}))
                    print(f"User {user_info['name']} joined the {user_info['game_type']} matchmaking queue.")
                
                # --- Game-specific logic handling ---
                elif action == "game_win":
                    winner_id = message.get("winner_id")
                    score = message.get("score")
                    game_id = message.get("game_id")
                    
                    if game_id in GAMES_IN_PROGRESS:
                        db = load_data()
                        if winner_id in db['users']:
                            db['users'][winner_id]['history'].append({
                                "type": "win",
                                "score": score,
                                "timestamp": datetime.now().isoformat()
                            })
                            db['leaderboard'].append({"user_id": winner_id, "score": score, "timestamp": datetime.now().isoformat()})
                            save_data(db)
                            
                            await broadcast({"action": "leaderboard_updated", "leaderboard": db['leaderboard']})
                        
                        del GAMES_IN_PROGRESS[game_id]
                        print(f"Game {game_id} ended. Winner: {winner_id}")
                
                elif action == "move_snake":
                    game_id = message.get("game_id")
                    player_id = message.get("player_id")
                    direction = message.get("direction")
                    
                    if game_id in GAMES_IN_PROGRESS:
                        game = GAMES_IN_PROGRESS[game_id]['game_instance']
                        game.update_direction(player_id, direction)
                        game_state = game.get_state()
                        
                        for client_ws in GAMES_IN_PROGRESS[game_id]['players'].values():
                            await client_ws.send_str(json.dumps({"action": "game_state", "state": game_state}))
                            
                        if game_state.get('winner'):
                            # Logic to handle a game ending and sending final data
                            pass
                
                elif action == "ping":
                    await ws.send_str(json.dumps({"action": "pong"}))
    
    finally:
        connected_clients.remove(ws)
        if ws in ADMIN_SESSIONS:
            ADMIN_SESSIONS.remove(ws)

# --- Main Application Setup ---

async def main():
    app = web.Application()
    
    # Configure CORS for your WebSocket route
    cors = aiohttp_cors.setup(app, defaults={
        "*": aiohttp_cors.ResourceOptions(
            allow_credentials=True,
            expose_headers="*",
            allow_headers="*",
            allow_methods="*",
        )
    })

    app.router.add_get('/ws', websocket_handler)
    
    # Add CORS to the WebSocket route
    resource = cors.add(app.router.add_resource("/ws"))
    cors.add(resource.add_route("GET", websocket_handler))


    runner = web.AppRunner(app)
    await runner.setup()
    
    port = int(os.environ.get('PORT', 8080))
    site = web.TCPSite(runner, '0.0.0.0', port)
    
    asyncio.create_task(start_matchmaking_loop())

    try:
        await site.start()
        await asyncio.Event().wait()
    except Exception as e:
        print(f"Error starting server: {e}")

if __name__ == '__main__':
    asyncio.run(main())
