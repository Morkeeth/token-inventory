"""The local dashboard. Listens on 127.0.0.1 only. Makes no outbound request."""
import json
import os
import threading
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

from . import config, scan

WEB = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'web')
LOCAL_HOSTS = ('127.0.0.1', 'localhost')
_lock = threading.Lock()


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *a, **kw):
        super().__init__(*a, directory=WEB, **kw)

    def log_message(self, *a):
        pass

    def _local(self):
        # A page on another site cannot reach this server through a renamed host (DNS rebinding).
        host = (self.headers.get('Host') or '').rsplit(':', 1)[0].strip('[]')
        return host in LOCAL_HOSTS

    def _json(self, code, body):
        raw = json.dumps(body).encode()
        self.send_response(code)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Cache-Control', 'no-store')
        self.send_header('Content-Length', str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def end_headers(self):
        self.send_header('Content-Security-Policy', "default-src 'self'; style-src 'self' 'unsafe-inline'; connect-src 'self'")
        self.send_header('Referrer-Policy', 'no-referrer')
        super().end_headers()

    def do_GET(self):
        if not self._local():
            return self._json(403, {'error': 'local requests only'})
        if self.path.split('?')[0] == '/api/inventory':
            inv = scan.load()
            if inv is None:
                with _lock:
                    inv, _ = scan.run()
            inv = dict(inv, data_folder=config.tilde(config.data_dir()))
            return self._json(200, inv)
        if self.path in ('/', ''):
            self.path = '/index.html'
        return super().do_GET()

    def do_POST(self):
        if not self._local() or self.headers.get('Origin') not in (None, 'http://%s' % self.headers.get('Host')):
            return self._json(403, {'error': 'local requests only'})
        if self.path == '/api/scan':
            with _lock:
                inv, _ = scan.run()
            return self._json(200, {'ok': True, 'cells': len(inv['cells'])})
        return self._json(404, {'error': 'not found'})


def serve(port=7788, open_browser=False):
    httpd = ThreadingHTTPServer(('127.0.0.1', port), Handler)
    url = 'http://127.0.0.1:%d/' % httpd.server_address[1]
    print('Dashboard: %s' % url)
    print('Listening on this machine only. Nothing is uploaded. Ctrl-C stops it.')
    if open_browser:
        import webbrowser
        webbrowser.open(url)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print('\nStopped.')
    finally:
        httpd.server_close()
