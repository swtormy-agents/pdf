#!/usr/bin/env python3
"""Local static server for tests: serves the repo root at /pdf/ (like the GitHub Pages project site
noclaudkit.com/pdf/); everything outside /pdf/ is 404. Usage: python3 tools/test/serve.py [port]"""
import http.server, os, sys
ROOT=os.path.abspath(os.path.join(os.path.dirname(__file__),'..','..'))
class H(http.server.SimpleHTTPRequestHandler):
    extensions_map={**http.server.SimpleHTTPRequestHandler.extensions_map,'.js':'text/javascript','.mjs':'text/javascript','.svg':'image/svg+xml','.css':'text/css','.xml':'application/xml'}
    def translate_path(self, path):
        p=path.split('?',1)[0].split('#',1)[0]
        if p.startswith('/pdf/'): p=p[4:]
        else: return '/nonexistent'
        if '..' in p or p.startswith('/tools'): return '/nonexistent'
        return ROOT+p+('index.html' if p.endswith('/') else '')
    def log_message(self,*a): pass
http.server.ThreadingHTTPServer(('127.0.0.1',int(sys.argv[1]) if len(sys.argv)>1 else 8931),H).serve_forever()
