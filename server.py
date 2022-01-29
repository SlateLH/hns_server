import argparse
import asyncio
import datetime
import faker
import json
import sqlite3
import websockets

DEFAULT_HOST = "0.0.0.0"
DEFAULT_PORT = 42069

fake = faker.Faker()

class Client:
    def __init__(self, uuid: str, websocket):
        self._uuid = uuid
        self._sock = websocket

    @property
    def uuid(self):
        return self._uuid

    async def get_user_name(self, name):
        res = ["get_user_name", name]
        await self.send_response([res])

    async def send_response(self, res):
        Logger.info(f"Sending response to {self.uuid}: {res}")
        await self._sock.send(json.dumps({"res": res }))

class DbManager:
    def __init__(self):
        self._con = sqlite3.connect('db.sqlite3')
        self._cur = self._con.cursor()
        self._cur.execute('''CREATE TABLE IF NOT EXISTS users (uuid TEXT NOT NULL PRIMARY KEY, name TEXT, UNIQUE(uuid))''')
        self._con.commit()

    def connect(self, uuid):
        name = f"{fake.safe_color_name().title()}{fake.first_name().title()}"
        self._cur.execute(f'''INSERT OR IGNORE INTO users(uuid, name) VALUES(\"{uuid}\", \"{name}\")''')
        self._con.commit()

    def get_user_name(self, uuid):
        self._cur.execute(f'''SELECT name FROM users WHERE uuid=\"{uuid}\"''')
        return self._cur.fetchone()[0]

    def __del__(self):
        self._con.close()

class ClientConnectionException(Exception):
    pass

class Server:
    def __init__(self):
        self._clients = {}
        self._rooms = {}
        self._db = DbManager()
        pass

    async def handle_client(self, websocket, path):
        Logger.log("Client connection request...")
        me = None
        try:
            async for message in websocket:
                try:
                    message = json.loads(message)
                except json.decoder.JSONDecodeError:
                    message = None
                if message is not None:
                    if me:
                        if "req" in message:
                            for req in message["req"]:
                                Logger.info(f"Received request from {me.uuid}: {req}")
                                if req[0] == "get_user_name":
                                    await me.get_user_name(self._db.get_user_name(me.uuid))
                        else:
                            Logger.error(f"Invalid request from {me.uuid}: {message}")

                    elif "uuid" in message:
                        me = Client(message["uuid"], websocket)
                        self._db.connect(me.uuid)
                        self._clients[me.uuid] = me
                        Logger.info(f"Client connected: {me.uuid}")
                    else:
                        raise ClientConnectionException
        except ClientConnectionException:
            await websocket.send(json.dumps({"res": ["error", "connection_refused"]}))
            Logger.error("Invalid connection request, client kicked...")
        except websockets.exceptions.ConnectionClosedError:
            if me:
                # TODO implement client disconnect
                self._clients.pop(me.uuid)
                Logger.info(f"Client disconnected: {me.uuid}")
            else:
                Logger.log("Unknown client disconnected...")

class Logger:
    colors = {
        "error": "\033[31m",
        "info": "\033[96m",
        "reset": "\033[0m",
    }

    @staticmethod
    def log(message):
        print(f"{Logger.colors['reset']}[LOG] {datetime.datetime.now()} {message}")

    @staticmethod
    def info(message):
        print(f"{Logger.colors['info']}[INFO] {datetime.datetime.now()} {message}")

    @staticmethod
    def error(message):
        print(f"{Logger.colors['error']}[ERROR] {datetime.datetime.now()} {message}{Logger.colors['error']}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", type=str, nargs="?", default=DEFAULT_HOST,
                        help="Host to bind to (default: {DEFAULT_HOST})")
    parser.add_argument("--port", type=int, nargs="?", default=DEFAULT_PORT,
                        help=f"Port to listen on (default: {DEFAULT_PORT})")

    args = parser.parse_args()

    Logger.log(f"Server starting at {args.host}:{args.port}...")

    server = Server()

    ws_server = websockets.serve(server.handle_client, args.host, args.port)

    asyncio.get_event_loop().run_until_complete(ws_server)

    try:
        asyncio.get_event_loop().run_forever()
    except KeyboardInterrupt:
        Logger.log("Server shutting down...")
