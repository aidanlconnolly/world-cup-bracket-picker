import json
import re
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from http.server import BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs

# Cheapest get-in ticket prices, no API key needed — parity with the
# /api/prices Flask route in server.py (which is what answers in prod today).
# Discovery: StubHub's World Cup grouping page (embeds the next matches across
# host cities as JSON in the HTML) + the public explore feed. Price: each
# event page's JSON-LD AggregateOffer lowPrice. Coverage is partial (soonest
# games first) and grows as matches approach.

WC_GROUPING_URL = 'https://www.stubhub.com/world-cup-tickets/grouping/45410'
SH_EXPLORE_URL = 'https://www.stubhub.com/explore?method=getExploreEvents&page=0'
SH_EVENT_RE = re.compile(
    r'\{"eventId":(\d+),"name":"([^"]+)","url":"([^"]+)"[^}]*?"venueName":"([^"]+)"')
BROWSER_UA = ('Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 '
              '(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36')


def http_get_text(url, timeout=9):
    req = urllib.request.Request(url, headers={
        'User-Agent': BROWSER_UA,
        'Accept': 'text/html,application/xhtml+xml,application/json;q=0.9,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.9',
        'Accept-Encoding': 'gzip',
    })
    with urllib.request.urlopen(req, timeout=timeout) as r:
        body = r.read()
        if r.headers.get('Content-Encoding') == 'gzip':
            import gzip
            body = gzip.decompress(body)
        return body.decode('utf-8', 'replace')


def jdec(s):
    try:
        return json.loads(f'"{s}"')
    except Exception:
        return s


def fetch_stubhub_prices(max_events):
    found = {}

    def note(eid, name, url, venue):
        if 'World Cup' in name and '/event/' in url:
            found[eid] = {'name': name, 'url': url, 'venue': venue}

    try:
        page = http_get_text(WC_GROUPING_URL)
        for m in SH_EVENT_RE.finditer(page):
            note(m.group(1), jdec(m.group(2)), jdec(m.group(3)), jdec(m.group(4)))
    except Exception:
        pass
    try:
        d = json.loads(http_get_text(SH_EXPLORE_URL))
        for e in d.get('events', []):
            if e.get('eventId') and e.get('url'):
                note(str(e['eventId']), e.get('name', ''), e['url'], e.get('venueName', ''))
    except Exception:
        pass

    today = time.strftime('%Y-%m-%d')
    rows = []
    for e in found.values():
        m = re.search(r'-(\d{1,2})-(\d{1,2})-(\d{4})/event/', e['url'])
        if not m:
            continue
        mo, dy, yr = m.groups()
        date = f'{yr}-{int(mo):02d}-{int(dy):02d}'
        if date < today:
            continue
        rows.append({'name': e['name'], 'venue': e['venue'], 'date': date, 'url': e['url']})
    rows.sort(key=lambda x: x['date'])
    rows = rows[:max_events]

    def fill_price(row):
        try:
            page = http_get_text(row['url'])
            lows = [float(x) for x in re.findall(r'"lowPrice"\s*:\s*"?([0-9][0-9.]*)', page)]
            row['lowPrice'] = round(min(lows), 2) if lows else None
        except Exception:
            row['lowPrice'] = None

    # gentle: few threads, small caps — StubHub challenges bursty clients
    with ThreadPoolExecutor(4) as ex:
        list(ex.map(fill_price, rows))
    return [{k: v for k, v in r.items() if k != 'url'} for r in rows if r.get('lowPrice')]


_cache = {'at': 0.0, 'max': 0, 'data': None}
TTL_OK, TTL_EMPTY = 1800, 240


class handler(BaseHTTPRequestHandler):
    def do_OPTIONS(self):
        self.send_response(200)
        self._cors()
        self.end_headers()

    def do_GET(self):
        qs = parse_qs(urlparse(self.path).query)
        try:
            max_events = max(1, min(int(qs.get('max', ['12'])[0]), 24))
        except ValueError:
            max_events = 12
        age = time.time() - _cache['at']
        if _cache['data'] is not None and _cache['max'] >= max_events \
                and age < (TTL_OK if _cache['data'] else TTL_EMPTY):
            self._respond({'prices': _cache['data'], 'cached': True})
            return
        try:
            data = fetch_stubhub_prices(max_events)
        except Exception:
            data = []
        _cache.update({'at': time.time(), 'max': max_events, 'data': data})
        self._respond({'prices': data, 'cached': False})

    def _cors(self):
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')

    def _respond(self, result, status=200):
        body = json.dumps(result).encode()
        self.send_response(status)
        self._cors()
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass
