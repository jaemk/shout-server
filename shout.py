# usage: spin up the server
#
# in browser:
# var sock = new WebSocket('ws://localhost:3000/ws');
# sock.send(JSON.stringify({init_for: 'main'}))
#
# var sub1 = new WebSocket('ws://localhost:3000/ws');
# sub1.send(JSON.stringify({subscribe_to: 'main'}))
# sub1.onmessage = (e) => console.log('sub1-receive: ' + e.data);
#
# var sub2 = new WebSocket('ws://localhost:3000/ws');
# sub2.send(JSON.stringify({subscribe_to: 'main'}))
# sub2.onmessage = (e) => console.log('sub2-receive: ' + e.data);
#
# sock.send(JSON.stringify({data: 'this is data!'}))
# ~> sub1-receive: {"data": "this is data"}
# ~> sub2-receive: {"data": "this is data"}


import asyncio
import asyncpg
from aiohttp import web, WSMsgType

import json
import logging


access_log = logging.getLogger('aiohttp.access')
access_log.setLevel(logging.INFO)
ch = logging.StreamHandler()
access_log.addHandler(ch)

socket_log = logging.getLogger(__name__ + '_socket_log')
socket_log.setLevel(logging.INFO)
ch = logging.StreamHandler()
socket_log.addHandler(ch)


async def handle(request):
    pool = request.app['pool']
    power = int(request.match_info.get('power', 10))
    async with pool.acquire() as conn:
        async with conn.transaction():
            result = await conn.fetchval('select 2 ^ $1', power)
            resp = f'2 ^ {power} is {result}'
            return web.Response(text=resp)


async def socket_handle(request):
    ws = web.WebSocketResponse()
    await ws.prepare(request)
    async for msg in ws:
        if msg.type == WSMsgType.CLOSED:
            await ws.close()
        elif msg.type == WSMsgType.ERROR:
            socket_log.error(f'ws connection closed with error: {ws.exception()}')
        elif msg.type == WSMsgType.TEXT:
            data = json.loads(msg.data)
            sock_id = data.get('init_for')
            if sock_id:
                request.app['ws_to_id'][ws] = sock_id
                request.app['id_to_ws'][sock_id] = ws
                request.app['sockets'][sock_id] = {'subscribers': []}
                socket_log.info(f'initialized source: {sock_id}')
                continue

            sock_id = data.get('subscribe_to')
            if sock_id:
                request.app['sockets'][sock_id]['subscribers'].append(ws)
                socket_log.info(f'subscribed to: {sock_id}')
                continue

            sock_id = request.app['ws_to_id'][ws]
            subscribers = request.app['sockets'][sock_id]['subscribers']
            for sub in subscribers:
                await sub.send_json({'data': data['data']})
        else:
            raise NotImplementedError(f'Unhandled `WSMsgType`: `{msg.type}`')

    socket_log.info('websocket closed')
    return ws


async def init_app():
    app = web.Application()

    app['pool'] = await asyncpg.create_pool(database='shout', user='shout', password='shout', host='localhost')
    app.router.add_route('GET', '/{power:\d+}', handle)
    app.router.add_route('GET', '/', handle)
    app.router.add_route('GET', '/ws', socket_handle)
    app.make_handler(access_log=access_log)
    app['sockets'] = {}
    app['ws_to_id'] = {}
    app['id_to_ws'] = {}
    return app


loop = asyncio.get_event_loop()
app = init_app()
app = loop.run_until_complete(app)
web.run_app(app, port=3000)
