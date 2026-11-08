#!/usr/bin/env bash
# Verify Windows -> WSL localhost port forwarding (critical for the app architecture).
set -uo pipefail
mkdir -p /tmp/porttest
cd /tmp/porttest
cat > srv.py <<'PY'
import http.server, socketserver, json, sys
class H(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        body = json.dumps({"ok": True, "from": "wsl"}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)
    def log_message(self, *a): pass
socketserver.TCPServer.allow_reuse_address = True
with socketserver.TCPServer(("0.0.0.0", 18770), H) as s:
    s.serve_forever()
PY
python3 srv.py &
SRV=$!
sleep 1.5
echo "  started pid=$SRV on 0.0.0.0:18770"
echo "  local check: $(curl -s --max-time 3 http://127.0.0.1:18770/ || echo FAIL)"
# leave it running for the Windows-side test
echo $SRV > /tmp/porttest/pid
sleep 60
kill $SRV 2>/dev/null || true
