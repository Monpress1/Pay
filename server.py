import asyncio
import websockets
import json
import os

connected_clients = set()
database_file = 'database.json'

def load_data():
    try:
        with open(database_file, 'r') as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}

def save_data(data):
    with open(database_file, 'w') as f:
        json.dump(data, f, indent=4)

async def handler(websocket, path):
    connected_clients.add(websocket)
    print(f"New WebSocket client connected. Total: {len(connected_clients)}")

    try:
        async for message in websocket:
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
                    if client != websocket:
                        await client.send(message)
                        print(f"WebSocket message forwarded.")
            
            except json.JSONDecodeError:
                print(f"Error decoding JSON: {message}")
            except Exception as e:
                print(f"An error occurred in WebSocket handler: {e}")

    finally:
        connected_clients.remove(websocket)
        print(f"WebSocket client disconnected. Total: {len(connected_clients)}")

async def main():
    # Use the port assigned by Render, defaulting to 8765
    port = int(os.environ.get('PORT', 8765))
    
    server = await websockets.serve(handler, "0.0.0.0", port)
    print(f"WebSocket server started on port {port}")
    await server.wait_closed()

if __name__ == "__main__":
    asyncio.run(main())
