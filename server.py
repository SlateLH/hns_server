import argparse
import asyncio
import faker
import json
import logging
import sqlite3
import sys
import websockets

DEFAULT_HOST = "0.0.0.0"
DEFAULT_PORT = 42069
DEFAULT_LOGLEVEL = logging.WARNING
DEFAULT_LOGFORMAT = "[%(levelname)s] %(asctime)s %(message)s"

fake = faker.Faker()

class Client:
    def __init__(self, uuid: str, websocket):
        self._uuid = uuid
        self._sock = websocket
        self._name = None
        self._is_ready = False

    @property
    def uuid(self):
        return self._uuid

    @property
    def name(self):
        return self._name

    @property
    def is_ready(self):
        return self._is_ready

    @is_ready.setter
    def is_ready(self, is_ready):
        self._is_ready = is_ready

    async def join_server(self, name):
        self._name = name

        res = ["join_server", self.uuid, name]
        await self.send_response([res])

    async def get_user_name(self, name):
        res = ["get_user_name", name]
        await self.send_response([res])

    async def send_response(self, res):
        logging.info(f"sending response to {self.uuid}: {res}")
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

    async def broadcast(self, res):
        lobby_players = list(self._clients.values())

        for lp in lobby_players:
            await lp.send_response(res)

    async def broadcast_clients(self):
        await self.broadcast([["get_lobby_players", [[lp.uuid, lp.name, lp.is_ready] for lp in list(self._clients.values())]]])

    async def broadcast_update_is_ready(self, uuid, is_ready):
        await self.broadcast([["update_is_ready", uuid, is_ready]])

    async def handle_client(self, websocket, path):
        logging.info("client connection request")
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
                                logging.info(f"received request from {me.uuid}: {req}")
                                if req[0] == "get_user_name":
                                    await me.get_user_name(self._db.get_user_name(me.uuid))
                                elif req[0] == "update_is_ready":
                                    me.is_ready = req[1]
                                    await self.broadcast_update_is_ready(me.uuid, me.is_ready)
                        else:
                            logging.warning(f"invalid request from {me.uuid}: {message}")

                    elif "uuid" in message:
                        me = Client(message["uuid"], websocket)
                        self._db.connect(me.uuid)
                        self._clients[me.uuid] = me
                        logging.info(f"client connected: {me.uuid}")
                        await me.join_server(self._db.get_user_name(me.uuid))
                        await self.broadcast_clients()
                    else:
                        raise ClientConnectionException
        except ClientConnectionException:
            await websocket.send(json.dumps({"res": ["error", "connection_refused"]}))
            logging.warning("invalid connection request, client kicked")
        except websockets.exceptions.ConnectionClosedError:
            if me:
                # TODO implement client disconnect
                self._clients.pop(me.uuid)
                logging.info(f"client disconnected: {me.uuid}")
            else:
                logging.info("unknown client disconnected")

            await self.broadcast_clients()

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", type=str, nargs="?", default=DEFAULT_HOST,
                        help="Host to bind to (default: {DEFAULT_HOST})")
    parser.add_argument("--port", type=int, nargs="?", default=DEFAULT_PORT,
                        help=f"Port to listen on (default: {DEFAULT_PORT})")
    parser.add_argument("--loglevel", type=str, nargs="?", default=DEFAULT_LOGLEVEL,
                        help=f"The lowest severity of messages to log (default: {DEFAULT_LOGLEVEL})")

    args = parser.parse_args()

    console = logging.StreamHandler()
    console.setLevel(args.loglevel)
    console.setFormatter(logging.Formatter(DEFAULT_LOGFORMAT))

    logging.basicConfig(level=args.loglevel, filemode="a", filename=".log", format=DEFAULT_LOGFORMAT)
    logging.getLogger().addHandler(console)

    server = Server()

    ws_server = websockets.serve(server.handle_client, args.host, args.port)

    asyncio.get_event_loop().run_until_complete(ws_server)

    try:
        asyncio.get_event_loop().run_forever()
    except KeyboardInterrupt:
        logging.info("server shutting down")
