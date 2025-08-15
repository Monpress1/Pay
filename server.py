import asyncio
import websockets
import json
import os

# Set of all connected WebSocket clients
connected_clients = set()
database_file = 'database.json'

def load_data():
    """Load data from the JSON file."""
    try:
        with open(database_file, 'r') as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        # Return an empty dictionary if the file doesn't exist or is empty
        return {}

def save_data(data):
    """Save data to the JSON file."""
    with open(database_file, 'w') as f:
        json.dump(data, f, indent=4)

async def handler(websocket, path):
    """Handles all incoming WebSocket connections and messages."""
    connected_clients.add(websocket)
    print(f"New client connected. Total clients: {len(connected_clients)}")

    try:
        # Loop forever, waiting for messages from the client
        async for message in websocket:
            print(f"Received message: {message}")
            
            try:
                data = json.loads(message)
                
                # Check for admin user based on a 'role' key
                is_admin = data.get("role") == "admin"

                # If the client is not an admin, save the data
                if not is_admin:
                    db = load_data()
                    user_key = data.get("phone_number", "unknown_user")
                    db[user_key] = data
                    save_data(db)
                    print(f"Data saved for user: {user_key}")

                # Forward the message to all other connected clients
                for client in connected_clients:
                    if client != websocket:
                        await client.send(message)
                        print(f"Message forwarded to another client.")
            
            except json.JSONDecodeError:
                print(f"Error decoding JSON: {message}")
            except Exception as e:
                print(f"An error occurred: {e}")

    finally:
        # Remove the client from our list when they disconnect
        connected_clients.remove(websocket)
        print(f"Client disconnected. Total clients: {len(connected_clients)}")

async def main():
    """Main function to start the WebSocket server."""
    # Use the port assigned by Render, defaulting to 8765 for local testing
    port = int(os.environ.get('PORT', 8765))
    
    server = await websockets.serve(handler, "0.0.0.0", port)
    print(f"WebSocket server started on port {port}")
    
    await server.wait_closed()

if __name__ == "__main__":
    asyncio.run(main())
