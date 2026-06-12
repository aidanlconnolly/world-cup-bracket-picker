import json
import os
import re
import secrets
import time
import urllib.request
from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
import anthropic

app = Flask(__name__, static_folder='.', static_url_path='')
CORS(app)

_client = None
def get_client():
    global _client
    if _client is None:
        key = os.environ.get('ANTHROPIC_API_KEY')
        if not key:
            return None
        _client = anthropic.Anthropic(api_key=key)
    return _client

@app.route('/')
def index():
    return send_from_directory('.', 'index.html')

# ─── Shared brackets ─────────────────────────────────────────────────────────
# On Vercel this Flask app serves the /api routes too (Flask preset), so the
# brackets route must use KV there (read-only filesystem). Locally, with no KV
# env vars, it falls back to a JSON file next to server.py.
BRACKETS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'brackets.local.json')
KV_KEY = 'wc2026:brackets'

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
    if kv_config()[0]:
        try:
            raw = kv_command('GET', KV_KEY)
            lst = json.loads(raw) if raw else []
            return lst if isinstance(lst, list) else []
        except Exception:
            return []
    try:
        with open(BRACKETS_FILE) as f:
            return json.load(f)
    except Exception:
        return []

def save_brackets(lst):
    if kv_config()[0]:
        kv_command('SET', KV_KEY, json.dumps(lst))
        return
    with open(BRACKETS_FILE, 'w') as f:
        json.dump(lst, f)

@app.route('/api/brackets', methods=['GET', 'POST', 'OPTIONS'])
def brackets():
    if request.method == 'OPTIONS':
        return '', 200
    if request.method == 'GET':
        return jsonify({'brackets': load_brackets()})

    data = request.json or {}
    name = re.sub(r'[\x00-\x1f<>]', '', str(data.get('name', ''))).strip()[:30]
    if not name:
        return jsonify({'error': 'invalid bracket'}), 400

    remaining = [b for b in load_brackets() if b.get('name', '').lower() != name.lower()]

    # {"name": ..., "remove": true} unpublishes that name (no auth — friend-group toy)
    if data.get('remove'):
        try:
            save_brackets(remaining)
        except Exception:
            return jsonify({'error': 'storage unavailable'}), 502
        return jsonify({'ok': True, 'removed': name})

    bracket_hash = str(data.get('hash', ''))
    if not bracket_hash or len(bracket_hash) > 50000:
        return jsonify({'error': 'invalid bracket'}), 400

    entry = {
        'id': f'{int(time.time()*1000)}-{secrets.token_hex(3)}',
        'name': name,
        'champion': str(data.get('champion', ''))[:40],
        'runnerUp': str(data.get('runnerUp', ''))[:40],
        'mode': 'ai' if data.get('mode') == 'ai' else 'pick',
        'hash': bracket_hash,
        'ts': int(time.time() * 1000),
    }
    remaining.insert(0, entry)
    try:
        save_brackets(remaining[:100])
    except Exception:
        return jsonify({'error': 'storage unavailable'}), 502
    return jsonify({'ok': True, 'id': entry['id']})

@app.route('/api/simulate', methods=['POST', 'OPTIONS'])
def simulate():
    if request.method == 'OPTIONS':
        return '', 200
    data = request.json
    team1 = data['team1']
    team2 = data['team2']
    winner = data['winner']
    probability = data['probability']
    stage = data['stage']
    venue = data.get('venue', '')

    prompt = (
        f"{stage}: {team1} vs {team2} at {venue}.\n"
        f"Result: {winner} wins ({probability}% probability).\n"
        f"In exactly 2 sentences, explain why {winner} won. "
        f"Be specific: mention key players, tactical strengths, or recent form. No filler."
    )

    client = get_client()
    if client is None:
        return jsonify({'reasoning': ''}), 503

    message = client.messages.create(
        model='claude-sonnet-4-6',
        max_tokens=150,
        messages=[{'role': 'user', 'content': prompt}]
    )
    return jsonify({'reasoning': message.content[0].text})

@app.route('/api/final', methods=['POST', 'OPTIONS'])
def final():
    if request.method == 'OPTIONS':
        return '', 200
    data = request.json
    champion = data['champion']
    runner_up = data.get('runnerUp', 'the runner-up')
    third = data.get('third', '')

    prompt = (
        f"The 2026 FIFA World Cup champion is {champion}, who beat {runner_up} in the Final."
        f"{f' {third} won the 3rd place game.' if third else ''}\n"
        f"Return a JSON object (no markdown, no code block) with exactly these three string fields:\n"
        f"- goldenBoot: one sentence naming the Golden Boot winner and why\n"
        f"- surpriseTeam: one sentence on the tournament's biggest surprise team\n"
        f"- summary: one sentence capturing how {champion} claimed the trophy"
    )

    client = get_client()
    if client is None:
        return jsonify({'error': 'ANTHROPIC_API_KEY not set'}), 503

    message = client.messages.create(
        model='claude-sonnet-4-6',
        max_tokens=250,
        messages=[{'role': 'user', 'content': prompt}]
    )

    try:
        result = json.loads(message.content[0].text)
    except Exception:
        result = {
            'goldenBoot': 'Golden Boot data unavailable.',
            'surpriseTeam': 'Surprise team data unavailable.',
            'summary': f'{champion} claimed the 2026 World Cup title in thrilling fashion.'
        }

    return jsonify(result)

if __name__ == '__main__':
    app.run(port=3000, debug=True)
