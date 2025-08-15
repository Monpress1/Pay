import asyncio
import websockets
import json

# List of all connected clients
connected_clients = set()

# Name of the file where we'll store the data
database_file = 'database.json'

# Function to load data from the database file
def load_data():
    try:
        with open(database_file, 'r') as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}

# Function to save data to the database file
def save_data(data):
    with open(database_file, 'w') as f:
        json.dump(data, f, indent=4)

async def handler(websocket, path):
    # Add the new client to our list
    connected_clients.add(websocket)
    print(f"New client connected. Total clients: {len(connected_clients)}")

    try:
        # Loop forever, waiting for messages from the client
        async for message in websocket:
            print(f"Received message: {message}")

            try:
                data = json.loads(message)

                # Check if this client is the admin
                is_admin = data.get("role") == "admin"

                if not is_admin:
                    # Load all existing data
                    db = load_data()
                    # Use the phone number as a unique ID to save the user's data
                    user_key = data.get("phone_number", "unknown_user")
                    db[user_key] = data
                    save_data(db)
                    print(f"Data saved for user: {user_key}")

                # Forward the message to the other connected clients
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

# Start the WebSocket server on all public network interfaces (0.0.0.0) on port 8765
start_server = websockets.serve(handler, "0.0.0.0", 8765)

print("WebSocket server started on port 8765")
asyncio.get_event_loop().run_until_complete(start_server)
asyncio.get_event_loop().run_forever()
