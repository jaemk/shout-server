import os
import asyncio
import asyncpg
import aiohttp_jinja2 as aiojinja
import jinja2
from aiohttp import web, WSMsgType

import json
import logging
import random
import time


PROJECT_DIR = os.path.dirname(os.path.realpath(__file__))
STATIC_ROOT = os.path.join(PROJECT_DIR, 'static')
TEMPLATE_ROOT = os.path.join(PROJECT_DIR, 'templates')


access_log = logging.getLogger('aiohttp.access')
access_log.setLevel(logging.INFO)
ch = logging.StreamHandler()
access_log.addHandler(ch)

socket_log = logging.getLogger(__name__ + '_socket_log')
socket_log.setLevel(logging.INFO)
ch = logging.StreamHandler()
socket_log.addHandler(ch)

def slog(s):
    socket_log.info(f'[SOCKET_LOG] {s}')


KEY_CHARS = 'abcdefghjkmpqrstuwxyz23456789'
def get_new_key(socket_ids):
    n_chars = 4
    key = ''.join(random.sample(KEY_CHARS, n_chars))
    while key in socket_ids:
        n_chars += 1
        key = ''.join(random.sample(KEY_CHARS, n_chars))
    return key


async def process_ws_data(request, data, msg, ws):
    if data.get('initialize'):
        source_command = data.get('source_command')
        new_stream_id = get_new_key(request.app['sockets'])
        request.app['ws_to_id'][ws] = new_stream_id
        request.app['id_to_ws'][new_stream_id] = ws
        request.app['sockets'][new_stream_id] = {'subscribers': set(), 'source_command': source_command}
        request.app['pings'][ws] = {'last_ping': time.time()}
        slog(f'Initialized source: {new_stream_id}')
        await ws.send_json({'stream_id': new_stream_id})
        return

    stream_id = data.get('subscribe')
    if stream_id:
        sockets = request.app['sockets']
        stream = sockets.get(stream_id)
        if not stream:
            slog(f'Attempt to subscribe to non-existent stream: {stream_id}')
            await ws.send_json({'error': {'short': 'NOSTREAM', 'msg': f"That stream doesn't exist: {stream_id}"}})
            await ws.close()
            return

        stream['subscribers'].add(ws)
        request.app['pings'][ws] = {'subbed_to': stream_id, 'last_ping': time.time()}
        slog(f'Subscribed to: {stream_id}')
        await ws.send_json({'subscribe': 'ok', 'source_command': stream['source_command']})
        return

    stream_id = request.app['ws_to_id'].get(ws)

    ping = data.get('ping')
    if ping:
        request.app['pings'][ws].update({'last_ping': time.time()})
        await ws.send_json({'pong': 'pong'})
        return

    if not stream_id:
        slog(f'Received pack from unregistered stream: `{data}`')
        await ws.send_json({'error': {'short': 'NOTREGISTERED', 'msg': 'You have not registered as a stream'}})
        await ws.close()
        return

    payload = data.get('payload')
    if payload is None:
        slog(f'Received pack missing `payload`: `{data}`')
        await ws.send_json({'error': {'short': 'NODATA', 'msg': 'Expected `payload` key with data'}})
        await ws.close()
        return

    slog(f"payload: `{repr(payload)}`")
    subscribers = request.app['sockets'][stream_id]['subscribers']
    for sub in subscribers:
        await sub.send_json({'payload': payload})


async def cleanup(app, stream_id=None, ws=None, close=False):
    if stream_id is not None:
        slog(f'Cleaning up stream-id: {stream_id}')
        producer = app['sockets'].get(stream_id)
        if producer:
            subscribers = producer.get('subscribers')
            for sub in subscribers:
                await sub.close()

    try:
        del app['sockets'][stream_id]
    except KeyError:
        pass

    if ws is None:
        ws = app['id_to_ws'][stream_id]

    subbed_to = app['pings'][ws].get('subbed_to')
    if subbed_to:
        app['sockets'][subbed_to]['subscribers'].remove(ws)

    try:
        del app['ws_to_id'][ws]
    except KeyError:
        pass

    if close:
        await ws.close()

    try:
        del app['id_to_ws'][stream_id]
    except KeyError:
        pass


async def process_ws(request, ws):
    slog('Websocket connected')
    async for msg in ws:
        if msg.type == WSMsgType.CLOSED:
            await ws.close()
        elif msg.type == WSMsgType.ERROR:
            socket_log.error(f'ws connection closed with error: {ws.exception()}')
        elif msg.type == WSMsgType.TEXT:
            data = json.loads(msg.data)
            await process_ws_data(request, data, msg, ws)
        else:
            slog(f'Unhandled `WSMsgType`: `{msg.type}`')
            raise NotImplementedError(f'Unhandled `WSMsgType`: `{msg.type}`')

    slog('Websocket closed')
    stream_id = request.app['ws_to_id'].get(ws)
    if stream_id is not None:
        await cleanup(stream_id=stream_id, app=app, ws=ws, close=False)


async def sockets(request):
    ws = web.WebSocketResponse()
    await ws.prepare(request)
    await process_ws(request, ws)
    return ws


@aiojinja.template('core/home.html')
async def home(request):
    return {'msg': 'Greetings'}


@aiojinja.template('core/watch.html')
async def watch(request):
    stream_id = request.match_info.get('stream_id')
    return {'stream_id': stream_id}


async def handle_power(request):
    pool = request.app['pool']
    power = int(request.match_info.get('power', 10))
    async with pool.acquire() as conn:
        async with conn.transaction():
            result = await conn.fetchval('select 2 ^ $1', power)
            resp = f'2 ^ {power} is {result}'
            return web.Response(text=resp)


async def init_app():
    app = web.Application()

    app['pool'] = await asyncpg.create_pool(database='shout', user='shout', password='shout', host='localhost')
    app.router.add_route('GET', '/', home)
    app.router.add_route('GET', '/api/ws', sockets)
    app.router.add_route('GET', '/pow/{power:\d+}', handle_power)
    app.router.add_route('GET', '/{stream_id:[a-z0-9]+}', watch)

    app.router.add_static('/static', STATIC_ROOT)

    aiojinja.setup(app, loader=jinja2.FileSystemLoader(TEMPLATE_ROOT))

    app.make_handler(access_log=access_log)
    app['sockets'] = {}
    app['ws_to_id'] = {}
    app['id_to_ws'] = {}
    app['pings'] = {}
    return app


loop = asyncio.get_event_loop()
app = init_app()

CLEAN_INTERVAL = 30
async def cleaner():
    while True:
        await asyncio.sleep(CLEAN_INTERVAL)
        now = time.time()
        count = 0
        to_drop_from_pings = []
        for ws, info in app['pings'].items():
            if (now - info['last_ping']) > CLEAN_INTERVAL:
                await cleanup(app, ws=ws, close=True)
                to_drop_from_pings.append(ws)
                count += 1
        for ws in to_drop_from_pings:
            del app['pings'][ws]
        print(f"Cleaned up {count} connections")

loop.create_task(cleaner())
app = loop.run_until_complete(app)
web.run_app(app, port=3000)
