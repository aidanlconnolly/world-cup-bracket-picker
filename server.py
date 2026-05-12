import json
import os
from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
import anthropic

app = Flask(__name__, static_folder='.', static_url_path='')
CORS(app)

client = anthropic.Anthropic(api_key=os.environ.get('ANTHROPIC_API_KEY'))

@app.route('/')
def index():
    return send_from_directory('.', 'index.html')

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
