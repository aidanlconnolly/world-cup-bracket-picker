import json
import os
from http.server import BaseHTTPRequestHandler
import anthropic


class handler(BaseHTTPRequestHandler):
    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.end_headers()

    def do_POST(self):
        length = int(self.headers.get('Content-Length', 0))
        data = json.loads(self.rfile.read(length))

        client = anthropic.Anthropic(api_key=os.environ.get('ANTHROPIC_API_KEY'))

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

        result = {'reasoning': message.content[0].text}
        self._respond(result)

    def _respond(self, result):
        body = json.dumps(result).encode()
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass
