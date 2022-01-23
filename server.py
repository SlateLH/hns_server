import argparse
import asyncio
import json
import sqlite3 as sq

import websockets

DEFAULT_HOST = "0.0.0.0"
DEFAULT_PORT = 42069


class Client:
    def __init__(self, uuid: str, websocket):
        self._uuid = uuid
        self._sock = websocket

    @property
    def uuid(self):
        return self._uuid

    async def update_name(self, name):
        await self._sock.send(json.dumps({"cmd": ["update_name", name]}))


class UserMan:
    def __init__(self):
        self._con = sq.connect('users.db')
        self._cur = self._con.cursor()
        self._cur.execute('''CREATE TABLE IF NOT EXISTS users (uuid text, name text) UNIQUE(uuid)''')
        self._con.commit()

    def connect(self, uuid):
        random_name = "Anonymous"
        self._cur.execute(f'''INSERT OR IGNORE INTO users(uuid, name) VALUES({uuid}, {random_name})''')
        self._con.commit()

    def get_name(self, uuid):
        self._cur.execute(f'''SELECT name FROM users WHERE uuid={uuid}''')
        return self._cur.fetchone()[0]

    def __del__(self):
        self._con.close()


class Server:
    def __init__(self):
        self._clients = {}
        self._rooms = {}
        self._um = UserMan()
        pass

    async def connect_request(self, websocket, path):
        print("Client connection request...")
        me = None
        try:
            async for message in websocket:
                try:
                    message = json.loads(message)
                except json.decoder.JSONDecodeError:
                    message = None
                if message is not None:
                    if me:
                        if "cmd" in message:
                            for cmd in message["cmd"]:
                                if cmd[0] == "get_name":
                                    await me.update_name(self._um.get_name(me.uuid))
                        else:
                            print(f"invalid message from {me.uuid}: {message}")

                    elif "uuid" in message:
                        me = Client(message["uuid"], websocket)
                        self._um.connect(me.uuid)
                        self._clients[me.uuid] = me
                    else:
                        print("Invalid Connection Request")
                        raise Exception
        except websockets.exceptions.ConnectionClosedError:
            if me:
                # TODO implement client disconnect
                self._clients.pop(me.uuid)
            print("Client disconnected...")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", type=str, nargs="?", default=DEFAULT_HOST,
                        help="Host to bind to (default: {DEFAULT_HOST})")
    parser.add_argument("--port", type=int, nargs="?", default=DEFAULT_PORT,
                        help=f"Port to listen on (default: {DEFAULT_PORT})")

    args = parser.parse_args()

    print(f"Server starting at {args.host}:{args.port}...")

    server = websockets.serve(handle_client, args.host, args.port)

    asyncio.get_event_loop().run_until_complete(server)

    try:
        asyncio.get_event_loop().run_forever()
    except KeyboardInterrupt:
        print("Server shutting down...")
