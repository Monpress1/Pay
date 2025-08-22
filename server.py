import asyncio
import json
import os
import random
from datetime import datetime
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
    """Load data from the JSON file."""
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
    """Save data to the JSON file."""
    with open(DATABASE_FILE, 'w') as f:
        json.dump(data, f, indent=4)

async def broadcast_online_players():
    """Broadcast the list of online players to all clients."""
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
    """Handles challenge expiration."""
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

# --- Standard HTTP Handler ---
async def handle_status_check(request):
    """Handles standard HTTP GET requests for health checks."""
    return web.Response(text="Server is running and ready for WebSocket connections.")

# --- WebSocket Handler ---

async def websocket_handler(request):
    """Handles WebSocket connections and messages."""
    ws = web.WebSocketResponse()
    await ws.prepare(request)
    
    user_id = None
    
    try:
        async for msg in ws:
            if msg.type == web.WSMsgType.TEXT:
                message = json.loads(msg.data)
                action = message.get("action")
                
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
                        connected_clients[user_id] = {'ws': ws, 'name': name}
                        await ws.send_str(json.dumps({
                            "action": "signup_success", 
                            "name": name, 
                            "coins": 100, 
                            "user_id": user_id
                        }))
                    else:
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

                    if opponent_id in connected_clients and opponent_id not in player_challenges.values():
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
                        game_id = f"game_{random.randint(1000, 9999)}"
                        
                        GAMES_IN_PROGRESS[game_id] = {
                            'players': {
                                challenger_id: connected_clients[challenger_id]['ws'],
                                opponent_id: connected_clients[opponent_id]['ws']
                            }
                        }
                        await connected_clients[challenger_id]['ws'].send_str(json.dumps({
                            "action": "match_found",
                            "game_id": game_id,
                            "game_type": game_type,
                            "opponent_name": connected_clients[opponent_id]['name']
                        }))
                        await connected_clients[opponent_id]['ws'].send_str(json.dumps({
                            "action": "match_found",
                            "game_id": game_id,
                            "game_type": game_type,
                            "opponent_name": connected_clients[challenger_id]['name']
                        }))
                        del player_challenges[challenger_id]
                    else:
                        await ws.send_str(json.dumps({"action": "challenge_failed", "reason": "Challenge expired or invalid."}))

                elif action == "game_action":
                    game_id = message.get("game_id")
                    player_id = message.get("player_id")
                    
                    if game_id in GAMES_IN_PROGRESS:
                        players_in_game = GAMES_IN_PROGRESS[game_id]['players']
                        opponent_id = next(p for p in players_in_game if p != player_id)
                        
                        opponent_ws = players_in_game.get(opponent_id)
                        if opponent_ws and not opponent_ws.closed:
                            await opponent_ws.send_str(json.dumps(message))

                elif action == "game_ended":
                    game_id = message.get("game_id")
                    if game_id in GAMES_IN_PROGRESS:
                        del GAMES_IN_PROGRESS[game_id]
                
                elif action == "ping":
                    await ws.send_str(json.dumps({"action": "pong", "timestamp": message.get('timestamp')}))
    
    finally:
        if user_id in connected_clients:
            del connected_clients[user_id]
        if ws in ADMIN_SESSIONS:
            ADMIN_SESSIONS.discard(ws)
    return ws

# --- Main Application Setup ---
async def main():
    app = web.Application()
    cors = aiohttp_cors.setup(app, defaults={"*": aiohttp_cors.ResourceOptions(allow_credentials=True, expose_headers="*", allow_headers="*", allow_methods="*")})

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
