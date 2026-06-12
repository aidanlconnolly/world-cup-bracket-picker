import json
import os
import re
import secrets
import time
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

# ─── Shared brackets (local dev: file-backed; prod uses api/brackets.py + Vercel KV) ───
BRACKETS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'brackets.local.json')

def load_brackets():
    try:
        with open(BRACKETS_FILE) as f:
            return json.load(f)
    except Exception:
        return []

@app.route('/api/brackets', methods=['GET', 'POST', 'OPTIONS'])
def brackets():
    if request.method == 'OPTIONS':
        return '', 200
    if request.method == 'GET':
        return jsonify({'brackets': load_brackets()})

    data = request.json or {}
    name = re.sub(r'[\x00-\x1f<>]', '', str(data.get('name', ''))).strip()[:30]
    bracket_hash = str(data.get('hash', ''))
    if not name or not bracket_hash or len(bracket_hash) > 50000:
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
    lst = [b for b in load_brackets() if b.get('name', '').lower() != name.lower()]
    lst.insert(0, entry)
    with open(BRACKETS_FILE, 'w') as f:
        json.dump(lst[:100], f)
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
