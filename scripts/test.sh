#!/usr/bin/env bash
# Test a real MISS -> HIT against a local origin, with no external test CDN.
set -euo pipefail
image=$1
suffix="$$"
network="lancache-test-$suffix"
origin="lancache-origin-$suffix"
cache="lancache-cache-$suffix"
work=$(mktemp -d)
cleanup() {
  docker rm -f "$cache" "$origin" >/dev/null 2>&1 || true
  docker network rm "$network" >/dev/null 2>&1 || true
  rm -rf "$work"
}
trap cleanup EXIT
docker network create "$network" >/dev/null
docker run -d --name "$origin" --network "$network" --network-alias origin \
  --entrypoint python3 "$image" -c '
from http.server import BaseHTTPRequestHandler, HTTPServer
class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        data = b"lancache-arm64 deterministic smoke test\n"
        self.send_response(200)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)
HTTPServer(("0.0.0.0", 80), Handler).serve_forever()
' >/dev/null
docker run -d --name "$cache" --network "$network" -p 127.0.0.1::80 \
  -e UPSTREAM_DNS=127.0.0.11 -e NOFETCH=true \
  -e CACHE_INDEX_SIZE=8m -e CACHE_DISK_SIZE=1g -e MIN_FREE_DISK=10m \
  -e NGINX_WORKER_PROCESSES=1 "$image" >/dev/null
port=$(docker port "$cache" 80/tcp | head -1 | cut -d: -f2)
ready=false
for ((attempt=0; attempt<45; attempt++)); do
  if [[ $(curl -s -o /dev/null -w '%{http_code}' "http://127.0.0.1:$port/lancache-heartbeat" || true) = 204 ]]; then
    ready=true
    break
  fi
  sleep 1
done
if [[ $ready != true ]]; then
  docker logs "$cache"
  exit 1
fi
docker exec "$cache" nginx -t
curl --fail --silent --show-error -D "$work/first.headers" -H 'Host: origin' \
  "http://127.0.0.1:$port/smoke.bin" -o "$work/first.body"
curl --fail --silent --show-error -D "$work/second.headers" -H 'Host: origin' \
  "http://127.0.0.1:$port/smoke.bin" -o "$work/second.body"
cmp "$work/first.body" "$work/second.body"
grep -q 'deterministic smoke test' "$work/second.body"
grep -qi '^X-Upstream-Cache-Status: MISS' "$work/first.headers"
grep -qi '^X-Upstream-Cache-Status: HIT' "$work/second.headers"
echo 'ARM64 architecture, nginx configuration, HTTP readiness and MISS -> HIT passed.'
