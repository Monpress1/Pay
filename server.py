import asyncio
import websockets
import json
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler

# --- WebSocket Server Setup (from before) ---

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

# --- HTTP Server for Health Checks (The new part) ---

class KeepAliveHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        # This is the endpoint that will be "pinged"
        self.send_response(200)
        self.send_header('Content-type', 'text/html')
        self.end_headers()
        self.wfile.write(b"Server is awake!")

def run_http_server():
    httpd = HTTPServer(('0.0.0.0', 8000), KeepAliveHandler)
    print("HTTP Keep-Alive server started on port 8000")
    httpd.serve_forever()

# --- Main Entry Point ---

if __name__ == "__main__":
    # Start the HTTP server in a separate thread
    http_thread = threading.Thread(target=run_http_server)
    http_thread.daemon = True
    http_thread.start()

    # Start the WebSocket server in the main thread
    websocket_server = websockets.serve(handler, "0.0.0.0", 8765)
    print("WebSocket server started on port 8765")
    asyncio.get_event_loop().run_until_complete(websocket_server)
    asyncio.get_event_loop().run_forever()
