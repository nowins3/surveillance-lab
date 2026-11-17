#!/usr/bin/env python3
"""Surveillance Lab: an in-memory, facilitated multiplayer camera experience."""
import argparse
import asyncio
import contextlib
import copy
import errno
import hmac
import json
import os
import secrets
import time
from pathlib import Path
from urllib.parse import urlsplit
from aiohttp import web
from https_setup import add_setup_routes

ROOT = Path(__file__).parent
SCENARIOS = json.loads((ROOT / 'scenarios.json').read_text())
MAX_ROOMS = 50


def now():
    return time.time()


def check(condition, message, status=400):
    if not condition:
        raise ApiError(message, status)


class ApiError(Exception):
    def __init__(self, message, status=400):
        self.message, self.status = message, status


class Room:
    def __init__(self, title):
        self.code = ''.join(secrets.choice('ABCDEFGHJKLMNPQRSTUVWXYZ23456789') for _ in range(6))
        self.manager = secrets.token_urlsafe(32)
        self.title = title
        self.created = now()
        self.ended = False
        self.players = {}
        self.listeners = set()
        self.round = None
        self.history = []
        self.scenarios = copy.deepcopy(SCENARIOS)
        self.settings = {'automatic': False, 'interval': 45, 'duration': 20, 'visionTriggers': False}
        self.next_prompt = now() + 45
        self.cursor = 0
        self.source = 'off'
        self.source_epoch = 0
        self.frame = None
        self.frame_at = 0
        self.frame_seq = 0
        self.observation = None
        self.events = []
        self.last_detection = 0
        self.vision_busy = False
        self.last_trigger = 0
        self.detection_streak = 0
        self.log('Session created')

    def log(self, text):
        self.events.append({'at': now(), 'text': text})
        self.events = self.events[-100:]

    def identity(self, token):
        if hmac.compare_digest(token, self.manager):
            return 'manager'
        if token in self.players:
            return token
        raise ApiError('This session credential is invalid. Rejoin the room.', 401)

    def counts(self):
        counts = [0] * len(self.round['options'])
        for vote in self.round['votes'].values():
            counts[vote] += 1
        return counts

    def view(self, who):
        manager = who == 'manager'
        active = None
        if self.round:
            active = {k: v for k, v in self.round.items() if k not in ('votes', 'reveal')}
            active['responses'] = len(self.round['votes'])
            active['myVote'] = self.round['votes'].get(who)
            if manager or self.round['status'] == 'revealed':
                active['counts'] = self.counts()
            if self.round['status'] == 'revealed':
                active['reveal'] = self.round['reveal']
        live = self.source != 'off' and now() - self.frame_at < 3
        data = {'code': self.code, 'title': self.title, 'ended': self.ended,
                'serverTime': now(), 'role': 'manager' if manager else 'participant',
                'participants': len(self.players),
                'online': sum(p['connections'] > 0 for p in self.players.values()),
                'round': active, 'settings': self.settings, 'nextPrompt': self.next_prompt,
                'source': self.source, 'live': live, 'frameAt': self.frame_at,
                'frameSeq': self.frame_seq,
                'observation': self.observation if live else None,
                'history': self.history}
        if manager:
            data.update(scenarios=self.scenarios, events=self.events,
                        roster=[{'name': p['name'], 'online': p['connections'] > 0} for p in self.players.values()])
        else:
            data['name'] = self.players[who]['name']
        return data

    def publish(self):
        for queue in self.listeners:
            if queue.full():
                with contextlib.suppress(asyncio.QueueEmpty):
                    queue.get_nowait()
            queue.put_nowait(True)

    def start_round(self, scenario, origin='manual'):
        check(not self.ended, 'The session has ended.', 409)
        check(not self.round or self.round['status'] == 'revealed', 'Reveal the current round before starting another.', 409)
        self.round = {k: copy.deepcopy(scenario[k]) for k in ('title', 'category', 'observation', 'question', 'options', 'reveal')}
        self.round.update(id=secrets.token_hex(8), scenarioId=scenario['id'], status='open',
                          openedAt=now(), deadline=now()+self.settings['duration'], votes={}, origin=origin,
                          evidence=copy.deepcopy(self.observation) if self.source != 'off' and now()-self.frame_at < 3 else None)
        self.log(f"Round opened: {scenario['title']} ({origin})")
        self.publish()

    def close_round(self):
        check(self.round is not None, 'There is no active round.', 409)
        if self.round['status'] == 'open':
            self.round['status'] = 'closed'
            self.round['closedAt'] = now()
            self.log('Voting closed')
            self.publish()

    def reveal(self):
        self.close_round()
        if self.round['status'] == 'revealed':
            return
        self.round['status'] = 'revealed'
        self.history.append({'id': self.round['id'], 'title': self.round['title'],
                             'question': self.round['question'], 'options': self.round['options'],
                             'counts': self.counts(), 'responses': len(self.round['votes']),
                             'reveal': self.round['reveal'], 'origin': self.round['origin'],
                             'at': now()})
        self.next_prompt = now()+self.settings['interval']
        self.log('Results revealed')
        self.publish()

    def observe(self, boxes, simulated=False, frame_seq=None):
        people = len(boxes)
        zone = any(0.35 <= b['box'][0] + b['box'][2]/2 <= 0.65 for b in boxes)
        self.observation = {'at': now(), 'frameSeq': frame_seq if frame_seq is not None else self.frame_seq,
                            'simulated': simulated, 'model': 'Simulation' if simulated else 'OpenCV HOG',
                            'people': people, 'zone': zone, 'boxes': boxes}
        self.detection_streak = self.detection_streak + 1 if people else 0
        if (self.settings['visionTriggers'] and now()-self.frame_at < 3 and self.detection_streak >= 2 and
                now() - self.last_trigger >= self.settings['interval'] and
                (not self.round or self.round['status'] == 'revealed') and not self.ended):
            trigger = 'crowd' if people >= 3 else 'zone' if zone else 'person'
            self.last_trigger = now()
            self.start_round(next(s for s in self.scenarios if s['trigger'] == trigger),
                             'simulated detection' if simulated else 'model detection')
        self.publish()


@web.middleware
async def errors(request, handler):
    try:
        # Browser mutations must come from this origin; no permissive CORS.
        origin = request.headers.get('Origin')
        if request.method not in ('GET', 'HEAD', 'OPTIONS') and origin:
            check(urlsplit(origin).netloc == request.host, 'Cross-origin requests are not allowed.', 403)
        response = await handler(request)
    except ApiError as exc:
        response = web.json_response({'error': exc.message}, status=exc.status)
    except (json.JSONDecodeError, UnicodeDecodeError, ValueError, TypeError, KeyError):
        response = web.json_response({'error': 'Invalid request data.'}, status=400)
    if not response.prepared:
        response.headers.update({'X-Content-Type-Options': 'nosniff', 'Referrer-Policy': 'no-referrer',
                                 'Cache-Control': 'no-store', 'X-Frame-Options': 'DENY'})
        response.headers['Content-Security-Policy'] = "default-src 'self'; img-src 'self' blob: data:; media-src 'self' blob:; style-src 'self'; script-src 'self'; connect-src 'self'; frame-ancestors 'none'"
    return response


def resolve(request, manager=False):
    room = request.app['rooms'].get(request.match_info['code'].upper())
    check(room is not None, 'Room not found. Check the code or ask the manager.', 404)
    token = request.headers.get('Authorization', '').removeprefix('Bearer ')
    who = room.identity(token)
    check(not manager or who == 'manager', 'Only the manager can do that.', 403)
    return room, who


async def body(request):
    data = await request.json()
    check(isinstance(data, dict), 'Expected a JSON object.')
    return data


def text_value(data, key, maximum=200, default=''):
    value = data.get(key, default)
    check(isinstance(value, str) and 0 < len(value.strip()) <= maximum, f'{key} must contain 1–{maximum} characters.')
    return value.strip()


def integer(data, key, low, high):
    val = data.get(key)
    check(type(val) is int and low <= val <= high, f'{key} must be between {low} and {high}.')
    return val


async def health(request):
    return web.json_response({'ok': True, 'vision': request.app['detector'] is not None})


async def create(request):
    data = await body(request)
    password = os.getenv('APP_PASSWORD')
    check(not password or hmac.compare_digest(str(data.get('password', '')), password), 'Incorrect session-creation password.', 403)
    check(len(request.app['rooms']) < MAX_ROOMS, 'Session limit reached. Restart the server or wait for expiry.', 429)
    room = Room(text_value(data, 'title', 80, 'Surveillance Lab'))
    while room.code in request.app['rooms']:
        room = Room(room.title)
    request.app['rooms'][room.code] = room
    return web.json_response({'code': room.code, 'token': room.manager, 'role': 'manager'})


async def join(request):
    room = request.app['rooms'].get(request.match_info['code'].upper())
    check(room is not None, 'Room not found. Check your six-character code.', 404)
    check(not room.ended, 'This session has ended.', 409)
    check(len(room.players) < 100, 'This room is full.', 409)
    data = await body(request)
    token = secrets.token_urlsafe(32)
    room.players[token] = {'name': text_value(data, 'name', 30), 'connections': 0}
    room.log('A participant joined')
    room.publish()
    return web.json_response({'code': room.code, 'token': token, 'role': 'participant'})


async def state(request):
    room, who = resolve(request)
    return web.json_response(room.view(who))


async def events(request):
    room, who = resolve(request)
    response = web.StreamResponse(headers={'Content-Type': 'text/event-stream', 'Cache-Control': 'no-store',
                                           'X-Accel-Buffering': 'no', 'X-Content-Type-Options': 'nosniff'})
    await response.prepare(request)
    queue = asyncio.Queue(maxsize=1)
    room.listeners.add(queue)
    if who != 'manager':
        room.players[who]['connections'] += 1
    room.publish()
    try:
        while True:
            await response.write(('data: '+json.dumps(room.view(who))+'\n\n').encode())
            try:
                await asyncio.wait_for(queue.get(), timeout=10)
            except asyncio.TimeoutError:
                pass
    except (ConnectionError, asyncio.CancelledError, RuntimeError):
        pass
    finally:
        room.listeners.discard(queue)
        if who != 'manager':
            room.players[who]['connections'] = max(0, room.players[who]['connections']-1)
        room.publish()
    return response


async def vote(request):
    room, who = resolve(request)
    check(who != 'manager', 'Join as a participant in another browser to vote.', 403)
    data = await body(request)
    check(not room.ended and room.round and room.round['status'] == 'open' and now() < room.round['deadline'], 'Voting is closed.', 409)
    check(data.get('roundId') == room.round['id'], 'This prompt has been replaced.', 409)
    choice = integer(data, 'choice', 0, len(room.round['options'])-1)
    room.round['votes'][who] = choice
    room.publish()
    return web.json_response({'ok': True})


async def control(request):
    room, _ = resolve(request, True)
    data = await body(request)
    action = data.get('action')
    check(not room.ended, 'This session has ended.', 409)
    if action == 'start':
        scenario = next((s for s in room.scenarios if s['id'] == data.get('scenarioId')), None)
        check(scenario is not None, 'Scenario not found.', 404)
        room.start_round(scenario)
    elif action == 'close':
        room.close_round()
    elif action == 'reveal':
        room.reveal()
    elif action == 'settings':
        interval = integer(data, 'interval', 15, 600)
        duration = integer(data, 'duration', 5, 120)
        check(type(data.get('automatic')) is bool and type(data.get('visionTriggers')) is bool, 'Invalid toggle values.')
        room.settings = {k: data[k] for k in ('automatic', 'visionTriggers')}
        room.settings.update(interval=interval, duration=duration)
        room.next_prompt = now()+interval
        room.log('Prompt settings updated')
    elif action == 'source':
        check(data.get('source') in ('off', 'demo', 'camera'), 'Invalid camera source.')
        room.source = data['source']
        room.source_epoch += 1
        room.frame, room.observation, room.frame_at = None, None, 0
        room.detection_streak = 0
        room.log('Broadcast source: '+room.source)
    elif action == 'simulate':
        check(room.source == 'demo', 'Simulation only runs in demo mode.', 409)
        count = integer(data, 'people', 0, 6)
        boxes = [{'label':'person', 'score':None, 'box':[round(0.12+i*0.13, 3), 0.26, 0.10, 0.48]} for i in range(count)]
        room.observe(boxes, True)
    elif action == 'custom':
        check(len(room.scenarios) < 30, 'Maximum 30 scenarios per room.')
        options = data.get('options')
        check(isinstance(options, list) and 2 <= len(options) <= 5 and all(isinstance(o, str) and 0 < len(o.strip()) <= 100 for o in options), 'Provide 2–5 choices of up to 100 characters.')
        room.scenarios.append({'id': secrets.token_hex(6), 'title': text_value(data, 'title', 80),
                               'category': 'Custom', 'trigger': 'manual',
                               'observation': text_value(data, 'observation', 300),
                               'question': text_value(data, 'question', 300), 'options': [o.strip() for o in options],
                               'reveal': text_value(data, 'reveal', 800)})
        room.log('Custom scenario added')
    elif action == 'end':
        if room.round and room.round['status'] != 'revealed':
            room.reveal()
        room.ended, room.source, room.frame, room.observation = True, 'off', None, None
        room.log('Session ended')
    else:
        raise ApiError('Unknown manager action.')
    room.publish()
    return web.json_response({'ok': True})


async def process_detection(app, room, jpeg, seq, epoch):
    try:
        async with app['vision_lock']:
            boxes = await asyncio.to_thread(app['detector'].detect, jpeg)
        if room.source == 'camera' and room.source_epoch == epoch and not room.ended and now()-room.frame_at < 3:
            room.observe(boxes, frame_seq=seq)
    except Exception:
        room.log('Vision could not process a frame')
    finally:
        room.vision_busy = False


async def frame(request):
    room, _ = resolve(request, True)
    check(not room.ended and room.source in ('camera', 'demo'), 'Broadcast is stopped.', 409)
    check(request.content_type == 'image/jpeg', 'Expected a JPEG frame.', 415)
    jpeg = await request.read()
    check(100 <= len(jpeg) <= 250_000 and jpeg[:2] == b'\xff\xd8' and jpeg[-2:] == b'\xff\xd9', 'Invalid or oversized JPEG frame.')
    was_live = room.frame is not None
    room.frame, room.frame_at = jpeg, now()
    room.frame_seq += 1
    if not was_live or room.frame_seq % 4 == 0:
        room.publish()
    detector = request.app['detector']
    if detector and room.source == 'camera' and not room.vision_busy and now()-room.last_detection >= 1.5:
        room.vision_busy, room.last_detection = True, now()
        task = asyncio.create_task(process_detection(request.app, room, jpeg, room.frame_seq, room.source_epoch))
        request.app['vision_tasks'].add(task)
        task.add_done_callback(request.app['vision_tasks'].discard)
    return web.json_response({'ok': True, 'seq': room.frame_seq})


async def get_frame(request):
    room, _ = resolve(request)
    if room.frame is None or room.ended or now()-room.frame_at > 3:
        return web.Response(status=204)
    return web.Response(body=room.frame, content_type='image/jpeg', headers={'X-Frame-Sequence':str(room.frame_seq), 'X-Frame-Time':str(room.frame_at)})


async def export(request):
    room, _ = resolve(request, True)
    data = {'title': room.title, 'code': room.code, 'createdAt': room.created, 'exportedAt': now(),
            'participants': len(room.players), 'settings': room.settings, 'results': room.history,
            'events': room.events, 'scenarios': room.scenarios}
    return web.Response(text=json.dumps(data, indent=2), content_type='application/json',
                        headers={'Content-Disposition':f'attachment; filename="surveillance-{room.code}.json"'})


async def maintenance(app):
    while True:
        await asyncio.sleep(0.5)
        for code, room in list(app['rooms'].items()):
            if now()-room.created > 6*3600:
                # End and notify before removing credentials; clear raw image immediately.
                room.ended, room.source, room.frame = True, 'off', None
                room.publish()
                del app['rooms'][code]
                continue
            if room.ended:
                continue
            if room.frame and now()-room.frame_at > 3:
                room.frame, room.observation = None, None
                room.detection_streak = 0
                room.publish()
            if room.round and room.round['status'] == 'open' and now() >= room.round['deadline']:
                room.close_round()
            # Automatic mode reveals after a short pause, then schedules another round.
            if room.settings['automatic']:
                if room.round and room.round['status'] == 'closed' and now() >= room.round.get('closedAt', room.round['deadline'])+4:
                    room.reveal()
                if (not room.round or room.round['status'] == 'revealed') and now() >= room.next_prompt:
                    candidates = [s for s in room.scenarios if s['trigger'] == 'timer']
                    scenario = candidates[room.cursor % len(candidates)]
                    room.cursor += 1
                    room.start_round(scenario, 'timer')


async def lifecycle(app):
    task = asyncio.create_task(maintenance(app))
    yield
    task.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await task
    for t in app['vision_tasks']:
        t.cancel()
    await asyncio.gather(*app['vision_tasks'], return_exceptions=True)


async def index(request):
    return web.FileResponse(ROOT/'public'/'index.html')


def make_app(vision=False, *, certificate_directory=None, https_port=8443, https_address=None):
    app = web.Application(middlewares=[errors], client_max_size=300_000)
    app['rooms'], app['detector'], app['vision_tasks'] = {}, None, set()
    app['vision_lock'] = asyncio.Lock()
    if vision:
        try:
            from vision import PersonDetector
            app['detector'] = PersonDetector()
        except ImportError as exc:
            raise SystemExit('Vision dependencies missing. Run: python -m pip install -r requirements-vision.txt') from exc
    app.cleanup_ctx.append(lifecycle)
    add_setup_routes(app, certificate_directory or ROOT/'.local-https', https_port, https_address)
    app.add_routes([web.get('/api/health', health), web.post('/api/rooms', create),
                    web.post('/api/rooms/{code}/join', join), web.get('/api/rooms/{code}/state', state),
                    web.get('/api/rooms/{code}/events', events), web.post('/api/rooms/{code}/vote', vote),
                    web.post('/api/rooms/{code}/control', control), web.post('/api/rooms/{code}/frame', frame),
                    web.get('/api/rooms/{code}/frame', get_frame), web.get('/api/rooms/{code}/export', export),
                    web.get('/', index), web.static('/assets/', ROOT/'public')])
    return app


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--host', default='127.0.0.1')
    parser.add_argument('--port', default=8000, type=int)
    parser.add_argument('--vision', action='store_true', help='Enable the offline HOG person detector')
    parser.add_argument('--cert', help='TLS certificate for HTTPS')
    parser.add_argument('--key', help='TLS private key for HTTPS')
    args = parser.parse_args()
    ssl_context = None
    if bool(args.cert) != bool(args.key):
        parser.error('--cert and --key must be supplied together')
    if args.cert:
        import ssl
        ssl_context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        ssl_context.load_cert_chain(args.cert, args.key)
    try:
        web.run_app(make_app(args.vision), host=args.host, port=args.port, ssl_context=ssl_context)
    except OSError as exc:
        if exc.errno in (errno.EADDRINUSE, 10048) or getattr(exc, 'winerror', None) == 10048:
            parser.exit(1, f'Port {args.port} is already in use. The lab may already be running.\n'
                           'For iPhone camera support, run only python local_https.py; '
                           'it serves both HTTP and HTTPS.\n'
                           'Stop the existing server with Ctrl+C before starting another.\n')
        raise
