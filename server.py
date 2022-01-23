import argparse
import asyncio
import websockets

DEFAULT_HOST = "0.0.0.0"
DEFAULT_PORT = 42069

async def handle_client(websocket, path):
  print("Client connected...")

  try:
    async for message in websocket:
      print(message)
  except websockets.exceptions.ConnectionClosedError:
    print("Client disconnected...")

if __name__ == "__main__":
  parser = argparse.ArgumentParser()
  parser.add_argument("--host", type=str, nargs="?", default=DEFAULT_HOST, help="Host to bind to (default: {DEFAULT_HOST})")
  parser.add_argument("--port", type=int, nargs="?", default=DEFAULT_PORT, help=f"Port to listen on (default: {DEFAULT_PORT})")

  args = parser.parse_args()

  print(f"Server starting at {args.host}:{args.port}...")

  server = websockets.serve(handle_client, args.host, args.port)

  asyncio.get_event_loop().run_until_complete(server)

  try:
    asyncio.get_event_loop().run_forever()
  except KeyboardInterrupt:
    print("Server shutting down...")
