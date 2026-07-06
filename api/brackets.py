import json
import os
import re
import secrets
import time
import urllib.request
from http.server import BaseHTTPRequestHandler

# Shared public brackets, stored as a single JSON array in Vercel KV (Upstash Redis).
# Requires the KV integration's env vars on the Vercel project:
#   KV_REST_API_URL + KV_REST_API_TOKEN (or UPSTASH_REDIS_REST_URL/_TOKEN).
KEY = 'wc2026:brackets'
MAX_BRACKETS = 100
# Frozen competition (July 6, 2026): POST rejects all mutations while True.
# Keep in sync with BOARD_LOCKED in index.html + server.py.
BOARD_LOCKED = True


def kv_config():
    url = os.environ.get('KV_REST_API_URL') or os.environ.get('UPSTASH_REDIS_REST_URL')
    token = os.environ.get('KV_REST_API_TOKEN') or os.environ.get('UPSTASH_REDIS_REST_TOKEN')
    return (url, token) if url and token else (None, None)


def kv_command(*args):
    url, token = kv_config()
    req = urllib.request.Request(
        url,
        data=json.dumps(list(args)).encode(),
        headers={'Authorization': f'Bearer {token}', 'Content-Type': 'application/json'},
        method='POST',
    )
    with urllib.request.urlopen(req, timeout=10) as r:
        return json.loads(r.read()).get('result')


def load_brackets():
    raw = kv_command('GET', KEY)
    if not raw:
        return []
    try:
        lst = json.loads(raw)
        return lst if isinstance(lst, list) else []
    except Exception:
        return []


class handler(BaseHTTPRequestHandler):
    def do_OPTIONS(self):
        self.send_response(200)
        self._cors()
        self.end_headers()

    def do_GET(self):
        if not kv_config()[0]:
            return self._respond({'error': 'storage not configured'}, 503)
        try:
            self._respond({'brackets': load_brackets()})
        except Exception:
            self._respond({'error': 'storage unavailable'}, 502)

    def do_POST(self):
        if BOARD_LOCKED:
            return self._respond({'error': 'The board is locked — brackets are final'}, 403)
        if not kv_config()[0]:
            return self._respond({'error': 'storage not configured'}, 503)
        try:
            length = int(self.headers.get('Content-Length', 0))
            data = json.loads(self.rfile.read(length)) if length else {}
        except Exception:
            return self._respond({'error': 'bad request'}, 400)

        name = re.sub(r'[\x00-\x1f<>]', '', str(data.get('name', ''))).strip()[:30]
        if not name:
            return self._respond({'error': 'invalid bracket'}, 400)

        # one entry per (name, kind): a person can hold a bracket AND predictor picks
        kind = 'predictor' if data.get('kind') == 'predictor' else 'bracket'
        def same(b):
            return b.get('name', '').lower() == name.lower() and b.get('kind', 'bracket') == kind

        # {"name": ..., "remove": true} unpublishes (no auth — friend-group toy);
        # with "kind" it removes just that kind, legacy removes wipe the whole name
        if data.get('remove'):
            try:
                if 'kind' in data:
                    remaining = [b for b in load_brackets() if not same(b)]
                else:
                    remaining = [b for b in load_brackets() if b.get('name', '').lower() != name.lower()]
                kv_command('SET', KEY, json.dumps(remaining))
                return self._respond({'ok': True, 'removed': name})
            except Exception:
                return self._respond({'error': 'storage unavailable'}, 502)

        bracket_hash = str(data.get('hash', ''))
        if not bracket_hash or len(bracket_hash) > 50000:
            return self._respond({'error': 'invalid bracket'}, 400)

        now_ms = int(time.time() * 1000)
        entry = {
            'id': f'{now_ms}-{secrets.token_hex(3)}',
            'name': name,
            'kind': kind,
            'champion': str(data.get('champion', ''))[:40],
            'runnerUp': str(data.get('runnerUp', ''))[:40],
            'mode': 'pick',
            'hash': bracket_hash,
            'ts': now_ms,
        }
        try:
            existing = load_brackets()
            prev = next((b for b in existing if same(b)), None)
            # first-publish time, kept across republishes — the client only credits
            # games that kicked off after an entry was created
            entry['createdAt'] = (prev.get('createdAt') or prev.get('ts') or now_ms) if prev else now_ms
            lst = [b for b in existing if not same(b)]
            lst.insert(0, entry)
            kv_command('SET', KEY, json.dumps(lst[:MAX_BRACKETS]))
            self._respond({'ok': True, 'id': entry['id']})
        except Exception:
            self._respond({'error': 'storage unavailable'}, 502)

    def _cors(self):
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')

    def _respond(self, result, status=200):
        body = json.dumps(result).encode()
        self.send_response(status)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Cache-Control', 'no-store')
        self._cors()
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass
