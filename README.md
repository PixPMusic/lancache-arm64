# LANCache ARM64

A native ARM64 rebuild of [LANCache Monolithic](https://github.com/lancachenet/monolithic).
Uses upstream Dockerfiles and overlays, replacing only their `FROM` references
to build the complete Ubuntu → Ubuntu nginx → Monolithic chain on ARM64.

Upstream currently publishes `latest`, without versioned releases or an
official nightly channel. This repository checks its published Docker Hub
image **digest** daily at 09:17 UTC and rebuilds when the inputs change.
It also tracks the published parent image digests, the ARM64 Ubuntu base
digest, and this repository's build recipe. Unchanged inputs skip the build.

## Image tags

```sh
docker pull ghcr.io/pixpmusic/lancache-arm64:latest
```

- `latest`: most recently built and smoke-tested image.
- `inputs-<hash>`: immutable identity of the tracked build inputs.
- `upstream-<monolithic-digest>-<inputs-hash>`: same image, identifying the
  upstream publication that triggered the rebuild.

The upstream images are currently AMD64-only. Their digests are **change
detectors**, not the binaries used inside the ARM64 image. Source revisions
are selected from each upstream default branch's most recent successful
`build_test_deploy` CI run and recorded in the workflow summary. Upstream's
published images do not record an exact Git revision, so this is not a
claim that the resulting image is byte-for-byte equivalent to their build.

The Ubuntu base is pinned by ARM64 digest; package repositories and the
upstream cache-domain list remain live at build time. Builds are traceable,
but not hermetic. For deployments, pin the resulting GHCR digest if you
want upgrades to happen only when you choose.

## Validation and publishing

Every build runs on `ubuntu-24.04-arm`. Before publishing, the smoke test
starts an isolated origin and LANCache on a temporary Docker network,
checks nginx configuration and HTTP readiness, then verifies a real
**MISS → HIT** with identical response bodies. Containers and the network
are removed on exit. Pull requests build and test without publishing.

Actions uses its own `GITHUB_TOKEN` with `packages: write`; no external
registry password or router credentials are needed. The first GHCR package
must be made public in its package settings for anonymous pulls. Scheduled
builds publish images only; they never connect to or restart a router.

Run **Build LANCache ARM64** manually in the Actions tab to check for an
update immediately. Changing the build recipe also triggers a check.

## Local build

Use Python 3, Git, Bash and a native ARM64 Docker engine:

```sh
mkdir -p build
python3 scripts/plan.py > build/inputs.json
python3 -c 'import json; json.dump(json.load(open("build/inputs.json"))["plan"], open("build/plan.json", "w"))'
scripts/build.sh build/plan.json lancache-arm64:local
scripts/test.sh lancache-arm64:local
```

`GH_TOKEN` is optional locally and raises GitHub API rate limits. Do not
commit tokens or Docker credentials. Build artifacts stay on your machine
until you explicitly push an image.

Checks: `python3 -m unittest discover -s tests -v`,
`bash -n scripts/build.sh scripts/test.sh`, and `actionlint`.

For deployment options and environment variables, see
[LANCache's documentation](https://lancache.net/docs/). This is an unofficial
rebuild; upstream owns its application code and existing license notices
remain in the image.
