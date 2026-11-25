#!/usr/bin/env python3
"""Resolve the published upstream latest digests and pinned ARM64 build inputs."""

import hashlib
import json
import os
from pathlib import Path
import re
import urllib.request


REPOS = ("ubuntu", "ubuntu-nginx", "monolithic")


def request(url, github=False):
    headers = {"User-Agent": "lancache-arm64"}
    if github and os.environ.get("GH_TOKEN"):
        headers["Authorization"] = f"Bearer {os.environ['GH_TOKEN']}"
    with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=30) as response:
        return response.read()


def github(path):
    return json.loads(request(f"https://api.github.com/repos/lancachenet/{path}", github=True))


def passed_ci(runs):
    # No result is not a green result. Ignore CI on unrelated feature branches.
    workflow = [run for run in runs if run["name"] == "build_test_deploy"]
    return bool(workflow) and all(run["status"] == "completed" and run["conclusion"] == "success" for run in workflow)


def fingerprint(plan):
    return hashlib.sha256(json.dumps(plan, sort_keys=True, separators=(",", ":")).encode()).hexdigest()[:24]


def resolve():
    sources, published = {}, {}
    for repo in REPOS:
        branch = github(repo)["default_branch"]
        commits = github(f"{repo}/commits?sha={branch}&per_page=30")
        for commit in commits:
            sha = commit["sha"]
            if passed_ci(github(f"{repo}/commits/{sha}/check-runs")["check_runs"]):
                sources[repo] = sha
                break
        else:
            raise ValueError(f"no CI-passing commit in the latest 30 {repo} commits")
        tag = json.loads(request(f"https://hub.docker.com/v2/repositories/lancachenet/{repo}/tags/latest"))
        published[repo] = tag["digest"]
        if not re.fullmatch(r"sha256:[0-9a-f]{64}", published[repo] or ""):
            raise ValueError(f"missing published image digest for {repo}")
    dockerfile = request(f"https://raw.githubusercontent.com/lancachenet/ubuntu/{sources['ubuntu']}/Dockerfile").decode()
    match = re.search(r"^FROM (ubuntu:[A-Za-z0-9_.-]+)\s*$", dockerfile, re.MULTILINE)
    if not match:
        raise ValueError("upstream base image format changed; review before rebuilding")
    tag_name = match[1].split(":", 1)[1]
    base = json.loads(request(f"https://hub.docker.com/v2/repositories/library/ubuntu/tags/{tag_name}"))
    images = [image for image in base["images"] if image["architecture"] == "arm64" and image["os"] == "linux"]
    if len(images) != 1 or not re.fullmatch(r"sha256:[0-9a-f]{64}", images[0]["digest"]):
        raise ValueError("expected exactly one linux/arm64 Ubuntu base image")
    recipe = hashlib.sha256()
    for path in [Path(__file__), Path(__file__).with_name("build.sh"), Path(__file__).with_name("test.sh")]:
        recipe.update(path.read_bytes())
    inputs = {"published_upstream": published, "base": f"{match[1]}@{images[0]['digest']}",
              "recipe": recipe.hexdigest()}
    # Git source selection is recorded, but a new Git commit alone does not
    # trigger a rebuild before upstream actually publishes a new latest image.
    return {"key": fingerprint(inputs), "upstream_digest": published["monolithic"],
            "plan": {**inputs, "sources": sources}}


if __name__ == "__main__":
    print(json.dumps(resolve(), separators=(",", ":")))
