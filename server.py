import argparse
import asyncio
import datetime
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
        self._is_leader = False

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

    @property
    def is_leader(self):
        return self._is_leader

    @is_leader.setter
    def is_leader(self, is_leader):
        self._is_leader = is_leader

    async def join_server(self, name):
        self._name = name

        res = ["join_server", self.uuid, name, self.is_leader]
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
        name = f"{fake.safe_color_name().title()} {fake.word().title()}"
        self._cur.execute(f'''INSERT OR IGNORE INTO users(uuid, name) VALUES(\"{uuid}\", \"{name}\")''')
        self._con.commit()

    def get_user_name(self, uuid):
        self._cur.execute(f'''SELECT name FROM users WHERE uuid=\"{uuid}\"''')
        return self._cur.fetchone()[0]

    def __del__(self):
        self._con.close()

class ClientConnectionException(Exception):
    def __init__(self, code, message):
        self._code = code
        self._message = message

    @property
    def code(self):
        return self._code

    @property
    def message(self):
        return self._message

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
        await self.broadcast([["get_lobby_players", [[lp.uuid, lp.name, lp.is_ready, lp.is_leader] for lp in list(self._clients.values())]]])

    async def broadcast_update_is_ready(self, uuid, is_ready):
        await self.broadcast([["update_is_ready", uuid, is_ready]])

    async def broadcast_chat(self, name, message, time):
        await self.broadcast([["chat", name, message, time]])

    async def broadcast_init_start_game(self):
        await self.broadcast([["init_start_game"]])

    async def broadcast_cancel_start_game(self):
        await self.broadcast([["cancel_start_game"]])

    async def broadcast_start_game(self):
        await self.broadcast([["start_game"]])

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
                                elif req[0] == "chat":
                                    await self.broadcast_chat(me.name, req[1], datetime.datetime.now().strftime("%I:%M %p"))
                                elif req[0] == "init_start_game":
                                    await self.broadcast_init_start_game()
                                elif req[0] == "cancel_start_game":
                                    await self.broadcast_cancel_start_game()
                                elif req[0] == "start_game":
                                    await self.broadcast_start_game()
                        else:
                            logging.warning(f"invalid request from {me.uuid}: {message}")

                    elif "uuid" in message:
                        uuid = message["uuid"]

                        if uuid in self._clients:
                            raise ClientConnectionException("connection_refused", "client already connected")

                        me = Client(uuid, websocket)
                        self._db.connect(me.uuid)

                        if len(self._clients) == 0:
                            me.is_leader = True

                        self._clients[me.uuid] = me
                        logging.info(f"client connected: {me.uuid}")
                        await me.join_server(self._db.get_user_name(me.uuid))
                        await self.broadcast_clients()
                    else:
                        raise ClientConnectionException("connection_refused", "no uuid provided")
        except ClientConnectionException as e:
            await websocket.send(json.dumps({"res": ["error", e.code, e.message]}))
            logging.warning(f"invalid connection request, client kicked ({e.code}: {e.message})")
        except websockets.exceptions.ConnectionClosedError:
            if me:
                self._clients.pop(me.uuid)

                if me.is_leader and len(self._clients) > 0:
                    list(self._clients.values())[0].is_leader = True

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
    except:
        logging.critical("unhandled fatal exception, server shutting down")
