#!/usr/bin/env bash
# Usage: scripts/build.sh PLAN.json IMAGE
set -euo pipefail
plan=$(realpath "$1")
image=$2
case $(docker info --format '{{.Architecture}}') in
  aarch64|arm64) ;;
  *) echo 'Use a native ARM64 Docker engine' >&2; exit 1 ;;
esac
work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT

for repo in ubuntu ubuntu-nginx monolithic; do
  revision=$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["sources"][sys.argv[2]])' "$plan" "$repo")
  [[ $revision =~ ^[0-9a-f]{40}$ ]] || { echo 'Invalid upstream revision' >&2; exit 1; }
  git init -q "$work/$repo"
  git -C "$work/$repo" remote add origin "https://github.com/lancachenet/$repo.git"
  git -C "$work/$repo" fetch -q --depth=1 origin "$revision"
  git -C "$work/$repo" checkout -q --detach FETCH_HEAD
done

python3 - "$plan" "$work" <<'PY'
import json
from pathlib import Path
import re
import sys
plan = json.loads(Path(sys.argv[1]).read_text())
root = Path(sys.argv[2])
if not re.fullmatch(r'ubuntu:[A-Za-z0-9_.-]+@sha256:[0-9a-f]{64}', plan['base']):
    raise ValueError('invalid pinned Ubuntu base')
for repo, pattern, replacement in [
    ('ubuntu', r'^FROM ubuntu:[A-Za-z0-9_.-]+\s*$', f"FROM {plan['base']}"),
    ('ubuntu-nginx', r'^FROM lancachenet/ubuntu:latest\s*$', 'FROM lancache-arm64-build/ubuntu:local'),
    ('monolithic', r'^FROM lancachenet/ubuntu-nginx:latest\s*$', 'FROM lancache-arm64-build/ubuntu-nginx:local'),
]:
    path = root/repo/'Dockerfile'
    text, count = re.subn(pattern, lambda _: replacement, path.read_text(), flags=re.MULTILINE)
    if count != 1:
        raise ValueError(f'{repo}: upstream FROM changed; review required')
    path.write_text(text)
PY

docker build --platform linux/arm64 --progress=plain -t lancache-arm64-build/ubuntu:local "$work/ubuntu"
docker build --platform linux/arm64 --progress=plain -t lancache-arm64-build/ubuntu-nginx:local "$work/ubuntu-nginx"
docker build --platform linux/arm64 --progress=plain \
  --label "org.opencontainers.image.source=https://github.com/${GITHUB_REPOSITORY:-PixPMusic/lancache-arm64}" \
  --label "org.opencontainers.image.revision=$(git rev-parse HEAD)" \
  --label "cc.pixp.lancache.upstream.monolithic=$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["sources"]["monolithic"])' "$plan")" \
  -t "$image" "$work/monolithic"
test "$(docker image inspect "$image" --format '{{.Architecture}}')" = arm64
