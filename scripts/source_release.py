#!/usr/bin/env python3
"""Public skill source releases: exact CI, reproducible bytes, no overwrites.

Standard library only. The workflow owns publication permission; this controller
validates mechanics, not human/host authorization. No registry/provider secrets.
"""
from __future__ import annotations

import argparse
import fnmatch
import gzip
import hashlib
import io
import json
import os
import re
import subprocess
import sys
import tarfile
import time
from pathlib import Path, PurePosixPath
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen

PUBLIC_SKILLS = {
    "zenstory-ai/oh-story-claudecode", "zenstory-ai/drama-skills",
    "zenstory-ai/novel-to-game", "zenstory-ai/video-recap-skills",
}
SHA = re.compile(r"[0-9a-f]{40}\Z")
VERSION = re.compile(r"(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)\Z")
UNSAFE_PARTS = {".git", ".omx", "node_modules", "__pycache__", ".venv", ".ssh"}
UNSAFE_NAMES = {".env", ".npmrc", ".pypirc", "id_rsa", "id_ed25519", "credentials.json", "secrets.json"}


class ReleaseError(RuntimeError):
    pass


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def encoded(value):
    return json.dumps(value, sort_keys=True, indent=2, ensure_ascii=False).encode() + b"\n"


def relative(value):
    if not isinstance(value, str) or not value or "\\" in value or any(ord(x) < 32 for x in value):
        raise ReleaseError("invalid relative path")
    if value.startswith("/") or any(x in {"", ".", ".."} for x in value.split("/")):
        raise ReleaseError("path escapes source root")
    return PurePosixPath(value)


def git(root, *args):
    p = subprocess.run(["git", "-C", str(root), *args], capture_output=True)
    if p.returncode:
        raise ReleaseError("git source operation failed")
    return p.stdout


def source_file(root, sha, path):
    if not SHA.fullmatch(sha):
        raise ReleaseError("source must be an immutable commit SHA")
    relative(path)
    return git(root, "show", f"{sha}:{path}")


def validate_policy(policy):
    fields = {"schemaVersion", "repository", "versionFiles", "changelog", "requiredPaths", "excludePaths", "ciWorkflows"}
    if not isinstance(policy, dict) or set(policy) != fields:
        raise ReleaseError("release policy has missing or unknown fields")
    if type(policy["schemaVersion"]) is not int or policy["schemaVersion"] != 1 or policy["repository"] not in PUBLIC_SKILLS:
        raise ReleaseError("only allowlisted public skill repositories are in scope")
    relative(policy["changelog"])
    if not isinstance(policy["versionFiles"], list) or not policy["versionFiles"]:
        raise ReleaseError("versionFiles must be nonempty")
    for item in policy["versionFiles"]:
        if not isinstance(item, dict) or item.get("format") not in {"text", "json"}:
            raise ReleaseError("invalid version file format")
        expected = {"path", "format", "pointer"} if item["format"] == "json" else {"path", "format"}
        if set(item) != expected:
            raise ReleaseError("invalid version file fields")
        relative(item["path"])
        if item["format"] == "json" and (not isinstance(item["pointer"], str) or not item["pointer"].startswith("/")):
            raise ReleaseError("JSON version requires explicit pointer")
    for field in ("requiredPaths", "excludePaths"):
        if not isinstance(policy[field], list) or any(not isinstance(x, str) for x in policy[field]):
            raise ReleaseError(f"{field} must be paths")
        for path in policy[field]:
            relative(path)
    if not policy["requiredPaths"] or not isinstance(policy["ciWorkflows"], list) or not policy["ciWorkflows"]:
        raise ReleaseError("required source and CI contracts cannot be empty")
    for workflow in policy["ciWorkflows"]:
        if not isinstance(workflow, dict) or set(workflow) != {"file", "jobs"}:
            raise ReleaseError("invalid CI workflow policy")
        if not re.fullmatch(r"[a-zA-Z0-9_-]+\.ya?ml", workflow["file"]):
            raise ReleaseError("CI workflow must be a repository workflow filename")
        jobs = workflow["jobs"]
        if not isinstance(jobs, list) or not jobs or any(not isinstance(x, str) or not x.strip() for x in jobs) or len(set(jobs)) != len(jobs):
            raise ReleaseError("CI jobs must be distinct, exact names")


def check_contract(root, policy, sha, tag=""):
    validate_policy(policy)
    versions = []
    for item in policy["versionFiles"]:
        data = source_file(root, sha, item["path"]).decode("utf-8")
        try:
            if item["format"] == "json":
                value = json.loads(data)
                for part in item["pointer"].split("/")[1:]:
                    key = part.replace("~1", "/").replace("~0", "~")
                    value = value[int(key)] if isinstance(value, list) else value[key]
            else:
                value = data.strip()
        except (ValueError, KeyError, TypeError, IndexError) as e:
            raise ReleaseError("cannot resolve version metadata") from e
        if not isinstance(value, str) or not VERSION.fullmatch(value):
            raise ReleaseError("release version must be stable SemVer")
        versions.append(value)
    if len(set(versions)) != 1:
        raise ReleaseError("repository version metadata disagrees")
    version = versions[0]
    if tag and tag != f"v{version}":
        raise ReleaseError("stable tag does not equal repository version")
    notes = source_file(root, sha, policy["changelog"]).decode("utf-8")
    if not re.search(rf"^## \[?{re.escape(version)}\]? - \d{{4}}-\d{{2}}-\d{{2}}\s*$", notes, re.M):
        raise ReleaseError("changelog lacks a dated version heading")
    for path in policy["requiredPaths"]:
        source_file(root, sha, path)
    return version


def validate_event(event, ref, publish):
    stable = ref.startswith("refs/tags/v") and VERSION.fullmatch(ref.removeprefix("refs/tags/v"))
    if publish:
        if event != "push" or not stable:
            raise ReleaseError("publication requires a stable tag push, never a PR or dispatch")
        return True
    if event == "pull_request" or (event == "workflow_dispatch" and ref == "refs/heads/main"):
        return False
    raise ReleaseError("dry-run must be a PR or an explicit main dispatch")


def newest_run(runs):
    if not runs:
        raise ReleaseError("missing CI run for exact source")
    return max(runs, key=lambda x: (x.get("run_number", 0), x.get("created_at", ""), x.get("id", 0)))


def validate_ci_run(run, jobs, suite, repo, sha, workflow_id, filename, expected_jobs):
    expected = {"workflow_id": workflow_id, "path": ".github/workflows/" + filename, "event": "push",
                "head_branch": "main", "head_sha": sha, "status": "completed", "conclusion": "success"}
    if any(run.get(k) != v for k, v in expected.items()) or run.get("head_repository", {}).get("full_name") != repo:
        raise ReleaseError("CI identity/conclusion does not prove this protected-main source")
    if not isinstance(run.get("run_attempt"), int) or run["run_attempt"] < 1:
        raise ReleaseError("CI attempt missing")
    if suite.get("id") != run.get("check_suite_id") or suite.get("app", {}).get("id") != 15368 or suite.get("head_sha") != sha or suite.get("conclusion") != "success" or suite.get("status") != "completed":
        raise ReleaseError("CI check suite is not successful GitHub Actions for this source")
    for name in expected_jobs:
        matches = [x for x in jobs if x.get("name") == name]
        if len(matches) != 1 or matches[0].get("conclusion") != "success":
            raise ReleaseError(f"required CI job not successful in exact attempt: {name}")


class GitHub:
    def __init__(self, token=None):
        self.token = token

    def request(self, path, method="GET", body=None, missing_ok=False, binary=False):
        base = "https://uploads.github.com" if binary else "https://api.github.com"
        headers = {"Accept": "application/vnd.github+json", "User-Agent": "zenstory-source-release/1", "X-GitHub-Api-Version": "2022-11-28"}
        if self.token:
            headers["Authorization"] = "Bearer " + self.token
        if binary:
            headers["Content-Type"] = "application/octet-stream"
            data = body
        else:
            headers["Content-Type"] = "application/json"
            data = encoded(body) if body is not None else None
        try:
            with urlopen(Request(base + path, data=data, headers=headers, method=method), timeout=30) as response:
                raw = response.read()
                return json.loads(raw) if raw else None
        except HTTPError as e:
            try:
                if e.code == 404 and missing_ok:
                    return None
                raise ReleaseError(f"GitHub {method} failed: HTTP {e.code}") from e
            finally:
                e.close()
        except (URLError, TimeoutError, json.JSONDecodeError) as e:
            raise ReleaseError("GitHub request/response failed; not evidence of absence") from e

    def pages(self, path, key=None):
        result = []
        for page in range(1, 101):
            data = self.request(path + ("&" if "?" in path else "?") + urlencode({"per_page": 100, "page": page}))
            batch = data[key] if key else data
            if not isinstance(batch, list):
                raise ReleaseError("invalid GitHub paginated response")
            result.extend(batch)
            if len(batch) < 100:
                return result
        raise ReleaseError("GitHub pagination limit exceeded")

    def tag_sha(self, repo, tag):
        obj = self.request(f"/repos/{repo}/git/ref/tags/{quote(tag, safe='')}")["object"]
        for _ in range(5):
            if obj.get("type") == "commit" and SHA.fullmatch(obj.get("sha", "")):
                return obj["sha"]
            if obj.get("type") != "tag" or not SHA.fullmatch(obj.get("sha", "")):
                break
            obj = self.request(f"/repos/{repo}/git/tags/{obj['sha']}")["object"]
        raise ReleaseError("tag must resolve to one immutable commit")


def ci_proof(api, policy, sha, tag=""):
    validate_policy(policy)
    if not SHA.fullmatch(sha):
        raise ReleaseError("source must be a commit SHA")
    repo = policy["repository"]
    meta = api.request(f"/repos/{repo}")
    branch = api.request(f"/repos/{repo}/branches/main")
    if meta.get("private") is not False or meta.get("full_name") != repo or meta.get("default_branch") != "main" or branch.get("protected") is not True:
        raise ReleaseError("source repository must be public with protected main")
    comparison = api.request(f"/repos/{repo}/compare/{sha}...main")
    if comparison.get("status") not in {"identical", "ahead"}:
        raise ReleaseError("release source is not an ancestor of main")
    if tag and (not tag.startswith("v") or not VERSION.fullmatch(tag[1:]) or api.tag_sha(repo, tag) != sha):
        raise ReleaseError("tag/source disagreement (including moved tag)")
    receipts = []
    for required in policy["ciWorkflows"]:
        filename = required["file"]
        wf = api.request(f"/repos/{repo}/actions/workflows/{filename}")
        if wf.get("path") != ".github/workflows/" + filename or wf.get("state") != "active" or not isinstance(wf.get("id"), int):
            raise ReleaseError("expected active CI workflow identity missing")
        runs = api.pages(f"/repos/{repo}/actions/workflows/{wf['id']}/runs?" + urlencode({"head_sha": sha, "branch": "main", "event": "push"}), "workflow_runs")
        selected = newest_run(runs)
        run = api.request(f"/repos/{repo}/actions/runs/{selected['id']}")
        if run.get("id") != selected["id"]:
            raise ReleaseError("CI run identity changed")
        attempt = run.get("run_attempt")
        if not isinstance(attempt, int) or attempt < 1:
            raise ReleaseError("latest CI attempt missing")
        jobs = api.pages(f"/repos/{repo}/actions/runs/{run['id']}/attempts/{attempt}/jobs", "jobs")
        suite = api.request(f"/repos/{repo}/check-suites/{run['check_suite_id']}")
        validate_ci_run(run, jobs, suite, repo, sha, wf["id"], filename, required["jobs"])
        # A concurrent rerun must not silently invalidate the inspected attempt.
        confirmed = api.request(f"/repos/{repo}/actions/runs/{run['id']}")
        if confirmed.get("run_attempt") != attempt or confirmed.get("conclusion") != "success" or confirmed.get("status") != "completed":
            raise ReleaseError("CI attempt changed during proof validation")
        receipts.append({"workflowId": wf["id"], "workflowPath": wf["path"], "runId": run["id"], "runAttempt": attempt,
                         "appId": suite["app"]["id"], "jobs": required["jobs"], "conclusion": "success"})
    return {"schemaVersion": 1, "repository": repo, "sourceSha": sha, "ci": receipts}


def unsafe(path):
    return any(x in UNSAFE_PARTS for x in path.parts) or path.name in UNSAFE_NAMES or path.suffix in {".pyc", ".pyo", ".pem", ".p12", ".pfx", ".key"}


def validate_links(members, prefix=""):
    """Preserve internal plugin aliases, but never extract through a link path."""
    names = {x.name.rstrip("/") for x in members} | ({prefix} if prefix else set())
    links = {x.name: x.linkname for x in members if x.issym()}
    minimum = 1 if prefix else 0

    def resolve(name, target, seen):
        if target.startswith("/") or "\\" in target or not target or any(ord(x) < 32 for x in target):
            raise ReleaseError("unsafe archive link target")
        parts = list(PurePosixPath(name).parent.parts)
        for part in target.split("/"):
            if part in {"", "."}:
                continue
            if part == "..":
                if len(parts) <= minimum:
                    raise ReleaseError("archive link escapes package root")
                parts.pop()
                continue
            parts.append(part)
            current = "/".join(parts)
            if current in links:
                if current in seen:
                    raise ReleaseError("archive link cycle")
                parts = resolve(current, links[current], seen | {current})
        if prefix and (not parts or parts[0] != prefix):
            raise ReleaseError("archive link escapes prefix")
        return parts

    for member in members:
        parts = PurePosixPath(member.name).parts
        if any("/".join(parts[:i]) in links for i in range(1, len(parts))):
            raise ReleaseError("archive entry traverses a symlink directory")
        if member.issym() and "/".join(resolve(member.name, member.linkname, {member.name})) not in names:
            raise ReleaseError("archive link target is absent")


def package_source(root, policy, sha, output):
    version = check_contract(root, policy, sha)
    repo = policy["repository"]
    prefix = repo.split("/")[1] + "-" + version
    excluded = policy["excludePaths"]
    epoch = int(git(root, "show", "-s", "--format=%ct", sha).strip())
    raw = git(root, "archive", "--format=tar", sha)
    inventory = []
    tar_bytes = io.BytesIO()
    with tarfile.open(fileobj=io.BytesIO(raw), mode="r:") as source, tarfile.open(fileobj=tar_bytes, mode="w", format=tarfile.PAX_FORMAT) as target:
        members = [x for x in source.getmembers() if not any(x.name.rstrip("/") == p or x.name.startswith(p + "/") or fnmatch.fnmatchcase(x.name, p) for p in excluded)]
        validate_links(members)
        for member in sorted(members, key=lambda x: x.name):
            path = relative(member.name.rstrip("/"))
            if any(path.as_posix() == x or path.as_posix().startswith(x + "/") or fnmatch.fnmatchcase(path.as_posix(), x) for x in excluded):
                continue
            if unsafe(path):
                raise ReleaseError(f"unsafe tracked archive entry: {path}")
            if not (member.isfile() or member.isdir() or member.issym()):
                raise ReleaseError(f"archive hardlinks/devices are not supported: {path}")
            content = source.extractfile(member).read() if member.isfile() else None
            normalized = tarfile.TarInfo(prefix + "/" + path.as_posix())
            normalized.type = tarfile.SYMTYPE if member.issym() else tarfile.REGTYPE if member.isfile() else tarfile.DIRTYPE
            normalized.linkname = member.linkname if member.issym() else ""
            normalized.mode = 0o755 if member.isdir() or member.mode & 0o111 else 0o644
            normalized.size = len(content) if content is not None else 0
            normalized.mtime = epoch
            target.addfile(normalized, io.BytesIO(content) if content is not None else None)
            if content is not None:
                inventory.append({"path": path.as_posix(), "size": len(content), "sha256": sha256(content)})
            elif member.issym():
                inventory.append({"path": path.as_posix(), "type": "symlink", "target": member.linkname})
    included = {x["path"] for x in inventory}
    if not set(policy["requiredPaths"]) <= included:
        raise ReleaseError("archive excludes required product files")
    compressed = io.BytesIO()
    with gzip.GzipFile(filename="", fileobj=compressed, mode="wb", mtime=0) as stream:
        stream.write(tar_bytes.getvalue())
    archive = compressed.getvalue()
    name = prefix + ".tar.gz"
    manifest = {"schemaVersion": 1, "repository": repo, "version": version, "sourceSha": sha,
                "archive": {"name": name, "size": len(archive), "sha256": sha256(archive)}, "files": inventory}
    output.mkdir(parents=True, exist_ok=True)
    (output / name).write_bytes(archive)
    (output / "RELEASE.json").write_bytes(encoded(manifest))
    (output / "SHA256SUMS").write_text(f"{sha256(archive)}  {name}\n{sha256(encoded(manifest))}  RELEASE.json\n")
    verify_candidate(output, repo, sha, version)
    return manifest


def verify_candidate(directory, repo, sha, version, expected_archive="", expected_manifest=""):
    if repo not in PUBLIC_SKILLS or not SHA.fullmatch(sha) or not VERSION.fullmatch(version):
        raise ReleaseError("candidate expected identity invalid")
    name = repo.split("/")[1] + "-" + version + ".tar.gz"
    allowed = {name, "RELEASE.json", "SHA256SUMS", "ci-proof.json"}
    if any(x.name not in allowed or not x.is_file() or x.is_symlink() for x in directory.iterdir()):
        raise ReleaseError("unexpected candidate files")
    manifest = json.loads((directory / "RELEASE.json").read_text())
    if expected_manifest and sha256((directory / "RELEASE.json").read_bytes()) != expected_manifest:
        raise ReleaseError("candidate manifest differs from independent producing-job digest")
    if manifest.get("schemaVersion") != 1 or any(manifest.get(k) != v for k, v in {"repository": repo, "sourceSha": sha, "version": version}.items()):
        raise ReleaseError("candidate source/version identity mismatch")
    if manifest.get("archive", {}).get("name") != name:
        raise ReleaseError("candidate archive filename mismatch")
    archive = (directory / name).read_bytes()
    if expected_archive and sha256(archive) != expected_archive:
        raise ReleaseError("candidate archive differs from independent producing-job digest")
    if manifest["archive"].get("size") != len(archive) or manifest["archive"].get("sha256") != sha256(archive):
        raise ReleaseError("candidate archive digest mismatch")
    sums = f"{sha256(archive)}  {name}\n{sha256((directory / 'RELEASE.json').read_bytes())}  RELEASE.json\n"
    if (directory / "SHA256SUMS").read_text() != sums:
        raise ReleaseError("candidate checksum manifest mismatch")
    actual = []
    prefix = name.removesuffix(".tar.gz") + "/"
    with tarfile.open(fileobj=io.BytesIO(archive), mode="r:gz") as tar:
        validate_links(tar.getmembers(), prefix.rstrip("/"))
        seen = set()
        for member in tar.getmembers():
            if not member.name.startswith(prefix):
                raise ReleaseError("archive prefix/path traversal")
            path = relative(member.name[len(prefix):].rstrip("/"))
            if unsafe(path) or path.as_posix() in seen or not (member.isfile() or member.isdir() or member.issym()):
                raise ReleaseError("unsafe/duplicate archive entry or link")
            seen.add(path.as_posix())
            if member.isfile():
                data = tar.extractfile(member).read()
                actual.append({"path": path.as_posix(), "size": len(data), "sha256": sha256(data)})
            elif member.issym():
                actual.append({"path": path.as_posix(), "type": "symlink", "target": member.linkname})
    if actual != manifest.get("files"):
        raise ReleaseError("archive file inventory mismatch")
    return manifest


def anonymous_bytes(url):
    try:
        with urlopen(Request(url, headers={"User-Agent": "zenstory-source-release/1"}), timeout=30) as response:
            return response.read()
    except (HTTPError, URLError, TimeoutError) as e:
        if isinstance(e, HTTPError):
            e.close()
        raise ReleaseError("anonymous public asset download failed") from e


def compare_asset(asset, data):
    if asset.get("size") != len(data) or (asset.get("digest") and asset["digest"] != "sha256:" + sha256(data)):
        raise ReleaseError("existing release asset differs; never overwrite")


def asset_url(repo, tag, name):
    return f"https://github.com/{repo}/releases/download/{quote(tag, safe='')}/{quote(name, safe='')}"


def publish_release(api, policy, sha, tag, directory, expected_archive="", expected_manifest=""):
    version = tag.removeprefix("v")
    candidate = verify_candidate(directory, policy["repository"], sha, version, expected_archive, expected_manifest)
    proof = ci_proof(api, policy, sha, tag)  # Recheck source/CI before write privilege is used.
    repo = policy["repository"]
    release = api.request(f"/repos/{repo}/releases/tags/{quote(tag, safe='')}", missing_ok=True)
    if release is None:
        release = api.request(f"/repos/{repo}/releases", "POST", {
            "tag_name": tag, "target_commitish": sha, "name": tag, "draft": False, "prerelease": False,
            "body": f"Source: `{sha}`\n\nReproducible source bundle; verify SHA256SUMS and RELEASE.json before installation.",
        })
    if release.get("tag_name") != tag or release.get("draft") is not False or release.get("prerelease") is not False:
        raise ReleaseError("existing release is not this stable published tag")
    assets = api.pages(f"/repos/{repo}/releases/{release['id']}/assets")
    for name in (candidate["archive"]["name"], "RELEASE.json", "SHA256SUMS"):
        data = (directory / name).read_bytes()
        existing = [x for x in assets if x.get("name") == name]
        if len(existing) > 1:
            raise ReleaseError("ambiguous duplicate release assets")
        if existing:
            compare_asset(existing[0], data)
            if anonymous_bytes(asset_url(repo, tag, name)) != data:
                raise ReleaseError("existing public asset bytes differ; never overwrite")
        else:
            api.request(f"/repos/{repo}/releases/{release['id']}/assets?" + urlencode({"name": name}), "POST", data, binary=True)
    return {"repository": repo, "sourceSha": sha, "version": version, "tag": tag,
            "releaseId": release["id"], "releaseUrl": release["html_url"], "ciProof": proof, "channel": "GITHUB_PUBLISHED"}


def verify_public(repo, tag, directory, manifest):
    for name in (manifest["archive"]["name"], "RELEASE.json", "SHA256SUMS"):
        expected = (directory / name).read_bytes()
        for attempt in range(6):
            try:
                if anonymous_bytes(asset_url(repo, tag, name)) != expected:
                    raise ReleaseError("anonymous public release bytes differ")
                break
            except ReleaseError:
                if attempt == 5:
                    raise
                time.sleep(5)
    return {"channel": "GITHUB_ANONYMOUS_BYTES_VERIFIED", "repository": repo,
            "tag": tag, "sourceSha": manifest["sourceSha"]}


def dispatch_clawhub(api, repo, tag, sha):
    if repo not in PUBLIC_SKILLS or not SHA.fullmatch(sha) or not tag.startswith("v") or not VERSION.fullmatch(tag[1:]):
        raise ReleaseError("invalid ClawHub release handoff identity")
    if api.tag_sha(repo, tag) != sha:
        raise ReleaseError("ClawHub handoff tag/source disagreement")
    release = api.request(f"/repos/{repo}/releases/tags/{quote(tag, safe='')}")
    if release.get("tag_name") != tag or release.get("draft") is not False or release.get("prerelease") is not False:
        raise ReleaseError("ClawHub handoff requires the exact stable published release")
    api.request(f"/repos/{repo}/actions/workflows/publish-clawhub.yml/dispatches", "POST", {
        "ref": "main", "inputs": {"mode": "release", "release_tag": tag, "source_sha": sha, "dry_run": "false"},
    })
    return {"channel": "CLAWHUB_QUEUED", "repository": repo, "tag": tag, "sourceSha": sha,
            "note": "Dispatch acknowledgement is not publication or scan verification; see ClawHub audit."}


def load_policy(root, sha, path):
    try:
        return json.loads(source_file(root, sha, path))
    except json.JSONDecodeError as e:
        raise ReleaseError("invalid source-bound release policy JSON") from e


def check_control_pins(caller, expected):
    """Bind both the reusable reader and write-capable handoff to one control SHA."""
    if not SHA.fullmatch(expected):
        raise ReleaseError("controls must be pinned to a full commit SHA")
    identities = [
        re.findall(r"^\s+uses: zenstory-ai/\.github/\.github/workflows/source-release\.yml@([0-9a-f]{40})\s*(?:#.*)?$", caller, re.M),
        re.findall(r"^\s+control_ref: ([0-9a-f]{40})\s*(?:#.*)?$", caller, re.M),
        re.findall(r"^\s+repository: zenstory-ai/\.github\s*\n\s+ref: ([0-9a-f]{40})\s*(?:#.*)?$", caller, re.M),
        re.findall(r"--control-ref\s+([0-9a-f]{40})(?=\s|$)", caller),
    ]
    if any(identity != [expected] for identity in identities):
        raise ReleaseError("reusable workflow/input/handoff checkout/CLI control pins disagree")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["check", "event", "ci-proof", "package", "publish", "verify-public", "dispatch-clawhub"])
    parser.add_argument("--root", type=Path, default=Path("."))
    parser.add_argument("--policy", default=".release/policy.json")
    parser.add_argument("--sha", default=os.getenv("SOURCE_SHA", ""))
    parser.add_argument("--tag", default="")
    parser.add_argument("--repository", default=os.getenv("GITHUB_REPOSITORY", ""))
    parser.add_argument("--control-ref", default="")
    parser.add_argument("--directory", type=Path, default=Path("candidate"))
    parser.add_argument("--output", type=Path)
    parser.add_argument("--event", default=os.getenv("GITHUB_EVENT_NAME", ""))
    parser.add_argument("--ref", default=os.getenv("GITHUB_REF", ""))
    parser.add_argument("--publish", choices=["true", "false"], default="false")
    parser.add_argument("--quiet", action="store_true")
    parser.add_argument("--expected-archive-sha", default=os.getenv("EXPECTED_ARCHIVE_SHA256", ""))
    parser.add_argument("--expected-manifest-sha", default=os.getenv("EXPECTED_MANIFEST_SHA256", ""))
    args = parser.parse_args(argv)
    if args.command == "event":
        result = {"publish": validate_event(args.event, args.ref, args.publish == "true")}
    else:
        policy = load_policy(args.root, args.sha, args.policy)
        if policy.get("repository") != args.repository:
            raise ReleaseError("caller and policy repository disagree")
        version = check_contract(args.root, policy, args.sha, args.tag)
        if args.control_ref:
            caller = source_file(args.root, args.sha, ".github/workflows/release.yml").decode()
            check_control_pins(caller, args.control_ref)
        api = GitHub(os.getenv("GH_TOKEN"))
        result = {"repository": args.repository, "sourceSha": args.sha, "version": version, "tag": args.tag or f"v{version}"}
        if args.command == "ci-proof":
            result = ci_proof(api, policy, args.sha, args.tag)
        elif args.command == "package":
            result = package_source(args.root, policy, args.sha, args.directory)
        elif args.command == "publish":
            validate_event(args.event, args.ref, True)
            if args.ref != "refs/tags/" + args.tag:
                raise ReleaseError("publisher tag differs from triggering ref")
            if not all(re.fullmatch(r"[0-9a-f]{64}", x) for x in (args.expected_archive_sha, args.expected_manifest_sha)):
                raise ReleaseError("publisher requires independent producing-job digests")
            result = publish_release(api, policy, args.sha, args.tag, args.directory, args.expected_archive_sha, args.expected_manifest_sha)
        elif args.command == "verify-public":
            manifest = verify_candidate(args.directory, args.repository, args.sha, version)
            result = verify_public(args.repository, args.tag, args.directory, manifest)
        elif args.command == "dispatch-clawhub":
            validate_event(args.event, args.ref, True)
            if args.ref != "refs/tags/" + args.tag:
                raise ReleaseError("ClawHub handoff tag differs from triggering ref")
            result = dispatch_clawhub(api, args.repository, args.tag, args.sha)
        if args.command == "check":
            output = os.getenv("GITHUB_OUTPUT")
            if output:
                with open(output, "a") as f:
                    f.write(f"source_sha={args.sha}\nversion={version}\ntag={args.tag or f'v{version}'}\n")
        elif args.command == "package" and os.getenv("GITHUB_OUTPUT"):
            with open(os.environ["GITHUB_OUTPUT"], "a") as f:
                f.write(f"archive_sha256={result['archive']['sha256']}\nmanifest_sha256={sha256(encoded(result))}\n")
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_bytes(encoded(result))
    if not args.quiet:
        print(encoded(result).decode(), end="")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (ReleaseError, ValueError, OSError, KeyError, tarfile.TarError) as error:
        print(f"::error::{error}", file=sys.stderr)
        sys.exit(1)
