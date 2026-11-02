"""Launch FORMA on localhost."""
import os
from server import create_server

host = os.environ.get("FORMA_HOST", "127.0.0.1")
port = int(os.environ.get("FORMA_PORT", "8000"))
server = create_server(host, port)
print(f"FORMA is running at http://{host}:{port}")
print(f"SQLite database: {server.forma_store.db_path}")
print("Press Ctrl+C to stop. This local build has no login or cloud synchronization.")
try:
    server.serve_forever()
except KeyboardInterrupt:
    print("\nShutting down FORMA...")
finally:
    server.server_close()
