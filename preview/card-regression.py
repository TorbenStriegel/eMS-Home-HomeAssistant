"""Run the browser selftest locally; optionally serve a saved baseline card."""
import argparse
import functools
import http.server
import pathlib
import re
import subprocess
import tempfile
import threading

parser = argparse.ArgumentParser()
parser.add_argument('--card', type=pathlib.Path)
parser.add_argument('--output', type=pathlib.Path, required=True)
args = parser.parse_args()
root = pathlib.Path(__file__).resolve().parents[1]

class Handler(http.server.SimpleHTTPRequestHandler):
    def do_GET(self):
        if args.card and self.path.split('?')[0] == '/custom_components/ems_home/frontend/ems-home-card.js':
            data = args.card.read_bytes()
            self.send_response(200)
            self.send_header('Content-Type', 'text/javascript')
            self.end_headers()
            self.wfile.write(data)
        else:
            super().do_GET()

    def log_message(self, format, *args):
        pass

server = http.server.ThreadingHTTPServer(('127.0.0.1', 0), functools.partial(Handler, directory=str(root)))
thread = threading.Thread(target=server.serve_forever, daemon=True)
thread.start()
profile = tempfile.TemporaryDirectory(prefix='ems-card-chrome-')
try:
    result = subprocess.run([
        '/usr/bin/chromium', '--headless', '--no-sandbox', '--disable-gpu',
        '--disable-background-networking', '--disable-component-update',
        '--disable-sync', '--no-first-run', '--no-default-browser-check',
        f'--user-data-dir={profile.name}',
        '--host-resolver-rules=MAP * ~NOTFOUND, EXCLUDE 127.0.0.1',
        '--dump-dom', '--virtual-time-budget=1000',
        f'http://127.0.0.1:{server.server_port}/preview/selftest.html',
    ], text=True, capture_output=True, timeout=60)
    match = re.search(r'<pre id="out">(.*?)</pre>', result.stdout, re.S)
    import html
    output = html.unescape(match.group(1)) if match else result.stdout + '\n' + result.stderr
    args.output.write_text(output + '\n')
    lines = output.splitlines()
    passed = sum(line.startswith('PASS ') for line in lines)
    failed = sum(line.startswith('FAIL ') for line in lines)
    print(f'Chrome returncode={result.returncode}; PASS={passed}; FAIL={failed}')
    print('\n'.join(line for line in lines if line.startswith('FAIL ')))
    if not passed or failed or result.returncode:
        raise SystemExit(1)
finally:
    server.shutdown()
    server.server_close()
    thread.join()
    profile.cleanup()
    print('Local test server stopped.')
