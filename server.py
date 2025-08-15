import asyncio
import websockets
import json
import os
from aiohttp import web

# --- WebSocket Server Setup ---

connected_clients = set()
database_file = 'database.json'

def load_data():
    """Load data from the JSON file."""
    try:
        with open(database_file, 'r') as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}

def save_data(data):
    """Save data to the JSON file."""
    with open(database_file, 'w') as f:
        json.dump(data, f, indent=4)

async def websocket_handler(request):
    """Handles WebSocket connections."""
    ws = web.WebSocketResponse()
    await ws.prepare(request)
    connected_clients.add(ws)
    print(f"New WebSocket client connected. Total clients: {len(connected_clients)}")

    try:
        async for msg in ws:
            if msg.type == web.WSMsgType.TEXT:
                message = msg.data
                print(f"Received WebSocket message: {message}")
                try:
                    data = json.loads(message)
                    is_admin = data.get("role") == "admin"
                    if not is_admin:
                        db = load_data()
                        user_key = data.get("phone_number", "unknown_user")
                        db[user_key] = data
                        save_data(db)
                        print(f"Data saved for user: {user_key}")

                    for client in connected_clients:
                        if client != ws:
                            await client.send_str(message)
                            print(f"WebSocket message forwarded.")
                except json.JSONDecodeError:
                    print(f"Error decoding JSON: {message}")
    finally:
        connected_clients.remove(ws)
        print(f"WebSocket client disconnected. Total clients: {len(connected_clients)}")
    return ws

# --- Health Check Endpoint ---

async def health_check(request):
    """A simple HTTP endpoint for Render's health checks."""
    print("Received health check request.")
    return web.Response(text="OK")

# --- Main Application Setup ---

async def main():
    app = web.Application()
    app.router.add_get('/', health_check)  # This handles the root URL for health checks
    app.router.add_get('/ws', websocket_handler) # This is the dedicated WebSocket endpoint

    runner = web.AppRunner(app)
    await runner.setup()
    
    port = int(os.environ.get('PORT', 8080))
    site = web.TCPSite(runner, '0.0.0.0', port)
    
    print(f"Server started on port {port}")
    await site.start()
    
    # Wait indefinitely for the server to be shut down
    await asyncio.get_event_loop().create_future()

if __name__ == '__main__':
    asyncio.run(main())
