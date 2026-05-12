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
