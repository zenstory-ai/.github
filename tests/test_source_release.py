"""Offline regressions for the public source-release boundary (no publication)."""
import hashlib
import importlib.util
import re
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock
from urllib.error import HTTPError

P = Path(__file__).parents[1] / "scripts/source_release.py"
S = importlib.util.spec_from_file_location("source_release", P)
r = importlib.util.module_from_spec(S)
S.loader.exec_module(r)


class SourceReleaseTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name) / "repo"
        self.root.mkdir()
        self.policy = {
            "schemaVersion": 1,
            "repository": "zenstory-ai/drama-skills",
            "versionFiles": [{"path": "VERSION", "format": "text"},
                             {"path": "plugin.json", "format": "json", "pointer": "/version"}],
            "changelog": "CHANGELOG.md",
            "requiredPaths": ["skills/a/SKILL.md", "LICENSE", "plugin.json"],
            "excludePaths": [],
            "ciWorkflows": [{"file": "ci.yml", "jobs": ["tests (py3.10)", "lint and types"]}],
        }
        files = {"VERSION": "1.2.3\n", "plugin.json": '{"version":"1.2.3"}\n',
                 "CHANGELOG.md": "## [Unreleased]\n\n## [1.2.3] - 2026-10-01\n",
                 "LICENSE": "MIT\n", "skills/a/SKILL.md": "# A\n"}
        for path, body in files.items():
            p = self.root / path
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(body)
        self.commit()

    def tearDown(self):
        self.tmp.cleanup()

    def git(self, *args):
        return subprocess.check_output(["git", "-C", str(self.root), *args], text=True).strip()

    def commit(self):
        subprocess.run(["git", "init", "-q", str(self.root)], check=True)
        self.git("config", "user.name", "Test")
        self.git("config", "user.email", "test@example.invalid")
        self.git("add", ".")
        self.git("commit", "-qm", "fixture")
        self.sha = self.git("rev-parse", "HEAD")

    def test_versions_and_stable_tag(self):
        self.assertEqual("1.2.3", r.check_contract(self.root, self.policy, self.sha, "v1.2.3"))
        for tag in ("v01.2.3", "v1.2.3-rc.1", "1.2.3", "v1.2.4", "v1.2.3\n"):
            with self.subTest(tag=tag), self.assertRaises(r.ReleaseError):
                r.check_contract(self.root, self.policy, self.sha, tag)

    def test_source_not_mutable_worktree(self):
        (self.root / "VERSION").write_text("9.9.9\n")
        self.assertEqual("1.2.3", r.check_contract(self.root, self.policy, self.sha))

    def test_mismatched_version_and_missing_notes(self):
        (self.root / "plugin.json").write_text('{"version":"1.2.4"}')
        self.commit()
        with self.assertRaisesRegex(r.ReleaseError, "version"):
            r.check_contract(self.root, self.policy, self.sha)
        (self.root / "plugin.json").write_text('{"version":"1.2.3"}')
        (self.root / "CHANGELOG.md").write_text("## [Unreleased]\n")
        self.commit()
        with self.assertRaisesRegex(r.ReleaseError, "changelog"):
            r.check_contract(self.root, self.policy, self.sha)

    def test_private_or_wrong_repository_policy(self):
        for repo in ("zenstory-ai/geo", "elsewhere/drama-skills", "zenstory-ai/industry-hot"):
            policy = dict(self.policy, repository=repo)
            with self.subTest(repo=repo), self.assertRaises(r.ReleaseError):
                r.check_contract(self.root, policy, self.sha)

    def test_reproducible_archive_and_manifest(self):
        a = Path(self.tmp.name) / "a"
        b = Path(self.tmp.name) / "b"
        r.package_source(self.root, self.policy, self.sha, a)
        r.package_source(self.root, self.policy, self.sha, b)
        for name in ("drama-skills-1.2.3.tar.gz", "RELEASE.json", "SHA256SUMS"):
            self.assertEqual((a / name).read_bytes(), (b / name).read_bytes())
        manifest = r.verify_candidate(a, self.policy["repository"], self.sha, "1.2.3")
        self.assertEqual(self.sha, manifest["sourceSha"])
        self.assertIn("skills/a/SKILL.md", [x["path"] for x in manifest["files"]])

    def test_generated_untracked_files_not_in_archive(self):
        (self.root / ".env").write_text("SECRET=not-for-publication")
        (self.root / "skills/a/__pycache__").mkdir()
        (self.root / "skills/a/__pycache__/x.pyc").write_bytes(b"cache")
        out = Path(self.tmp.name) / "candidate"
        manifest = r.package_source(self.root, self.policy, self.sha, out)
        self.assertFalse(any(".env" in x["path"] or "__pycache__" in x["path"] for x in manifest["files"]))

    def test_tracked_secret_and_symlink_are_rejected(self):
        (self.root / ".env").write_text("secret")
        self.commit()
        with self.assertRaisesRegex(r.ReleaseError, "unsafe"):
            r.package_source(self.root, self.policy, self.sha, Path(self.tmp.name) / "secret")
        (self.root / ".env").unlink()
        (self.root / "skills/a/link").symlink_to("../../../../outside")
        self.commit()
        with self.assertRaisesRegex(r.ReleaseError, "link"):
            r.package_source(self.root, self.policy, self.sha, Path(self.tmp.name) / "link")

    def test_internal_plugin_symlinks_are_preserved(self):
        (self.root / ".agents").mkdir()
        (self.root / ".agents/skills").symlink_to("../skills")
        (self.root / ".agents/notes").mkdir()
        (self.root / ".agents/notes/process.md").write_text("development note")
        self.policy["excludePaths"] = [".agents/notes"]
        self.policy["requiredPaths"].append(".agents/skills")
        self.commit()
        out = Path(self.tmp.name) / "internal-link"
        manifest = r.package_source(self.root, self.policy, self.sha, out)
        self.assertIn({"path": ".agents/skills", "type": "symlink", "target": "../skills"}, manifest["files"])
        self.assertFalse(any(x["path"].startswith(".agents/notes") for x in manifest["files"]))
        r.verify_candidate(out, self.policy["repository"], self.sha, "1.2.3")
        self.assertEqual(255, (out / manifest["archive"]["name"]).read_bytes()[9])

    def test_cyclic_internal_links_are_rejected(self):
        (self.root / "a").symlink_to("b")
        (self.root / "b").symlink_to("a")
        self.commit()
        with self.assertRaisesRegex(r.ReleaseError, "cycle"):
            r.package_source(self.root, self.policy, self.sha, Path(self.tmp.name) / "cycle")

    def test_digest_source_and_extra_files_rejected(self):
        out = Path(self.tmp.name) / "candidate"
        r.package_source(self.root, self.policy, self.sha, out)
        with self.assertRaises(r.ReleaseError):
            r.verify_candidate(out, self.policy["repository"], "f" * 40, "1.2.3")
        with self.assertRaises(r.ReleaseError):
            r.verify_candidate(out, self.policy["repository"], self.sha, "1.2.3", expected_manifest="f" * 64)
        with self.assertRaises(r.ReleaseError):
            r.verify_candidate(out, self.policy["repository"], self.sha, "1.2.3", expected_archive="f" * 64)
        (out / "drama-skills-1.2.3.tar.gz").write_bytes(b"tampered")
        with self.assertRaises(r.ReleaseError):
            r.verify_candidate(out, self.policy["repository"], self.sha, "1.2.3")
        r.package_source(self.root, self.policy, self.sha, out)
        (out / "unexpected.txt").write_text("unexpected")
        with self.assertRaises(r.ReleaseError):
            r.verify_candidate(out, self.policy["repository"], self.sha, "1.2.3")

    def run_fixture(self):
        return {"id": 30, "run_number": 10, "workflow_id": 8, "path": ".github/workflows/ci.yml",
                "event": "push", "head_branch": "main", "head_sha": self.sha,
                "head_repository": {"full_name": self.policy["repository"]},
                "status": "completed", "conclusion": "success", "run_attempt": 2, "check_suite_id": 40}

    def test_exact_ci_identity_and_attempt(self):
        run = self.run_fixture()
        jobs = [{"name": name, "conclusion": "success"} for name in self.policy["ciWorkflows"][0]["jobs"]]
        suite = {"id": 40, "app": {"id": 15368}, "head_sha": self.sha, "status": "completed", "conclusion": "success"}
        r.validate_ci_run(run, jobs, suite, self.policy["repository"], self.sha, 8, "ci.yml", self.policy["ciWorkflows"][0]["jobs"])
        for field, value in [("head_sha", "f" * 40), ("event", "pull_request"), ("head_branch", "topic"),
                             ("workflow_id", 9), ("conclusion", "cancelled"), ("status", "in_progress")]:
            wrong = dict(run, **{field: value})
            with self.subTest(field=field), self.assertRaises(r.ReleaseError):
                r.validate_ci_run(wrong, jobs, suite, self.policy["repository"], self.sha, 8, "ci.yml", self.policy["ciWorkflows"][0]["jobs"])
        for bad in (jobs[:-1], [dict(jobs[0], conclusion="skipped"), jobs[1]], jobs + [jobs[0]]):
            with self.assertRaises(r.ReleaseError):
                r.validate_ci_run(run, bad, suite, self.policy["repository"], self.sha, 8, "ci.yml", self.policy["ciWorkflows"][0]["jobs"])
        with self.assertRaises(r.ReleaseError):
            r.validate_ci_run(run, jobs, dict(suite, app={"id": 999}), self.policy["repository"], self.sha, 8, "ci.yml", self.policy["ciWorkflows"][0]["jobs"])

    def test_newest_failed_run_never_falls_back(self):
        old = self.run_fixture()
        new = dict(old, id=31, run_number=11, conclusion="failure")
        self.assertEqual(31, r.newest_run([old, new])["id"])

    def fake_ci_api(self):
        api = mock.Mock()
        run = self.run_fixture()
        repo = self.policy["repository"]
        replies = {
            f"/repos/{repo}": {"private": False, "full_name": repo, "default_branch": "main"},
            f"/repos/{repo}/branches/main": {"protected": True},
            f"/repos/{repo}/compare/{self.sha}...main": {"status": "ahead"},
            f"/repos/{repo}/actions/workflows/ci.yml": {"id": 8, "path": ".github/workflows/ci.yml", "state": "active"},
            f"/repos/{repo}/actions/runs/30": run,
            f"/repos/{repo}/check-suites/40": {"id": 40, "app": {"id": 15368}, "head_sha": self.sha, "status": "completed", "conclusion": "success"},
        }
        api.request.side_effect = lambda path, *a, **k: replies[path]
        api.pages.side_effect = lambda path, key: [run] if key == "workflow_runs" else [{"name": x, "conclusion": "success"} for x in self.policy["ciWorkflows"][0]["jobs"]]
        api.tag_sha.return_value = self.sha
        return api, replies

    def test_ci_proof_reads_exact_latest_attempt_and_public_branch(self):
        api, replies = self.fake_ci_api()
        proof = r.ci_proof(api, self.policy, self.sha, "v1.2.3")
        self.assertEqual(2, proof["ci"][0]["runAttempt"])
        self.assertTrue(any("/runs/30/attempts/2/jobs" in x.args[0] for x in api.pages.call_args_list))
        replies[f"/repos/{self.policy['repository']}"]["private"] = True
        with self.assertRaisesRegex(r.ReleaseError, "public"):
            r.ci_proof(api, self.policy, self.sha)

    def test_moved_tag_and_concurrent_attempt_block_publication_proof(self):
        api, replies = self.fake_ci_api()
        api.tag_sha.return_value = "f" * 40
        with self.assertRaisesRegex(r.ReleaseError, "tag/source"):
            r.ci_proof(api, self.policy, self.sha, "v1.2.3")
        api.tag_sha.return_value = self.sha
        original = api.request.side_effect
        count = 0
        def request(path, *args, **kwargs):
            nonlocal count
            value = original(path, *args, **kwargs)
            if path.endswith("/actions/runs/30"):
                count += 1
                if count > 1:
                    return dict(value, run_attempt=3, status="in_progress", conclusion=None)
            return value
        api.request.side_effect = request
        with self.assertRaisesRegex(r.ReleaseError, "attempt changed"):
            r.ci_proof(api, self.policy, self.sha)

    def test_explicit_clawhub_dispatch_is_only_queued(self):
        api = mock.Mock()
        api.tag_sha.return_value = self.sha
        api.request.return_value = {"tag_name": "v1.2.3", "draft": False, "prerelease": False}
        result = r.dispatch_clawhub(api, self.policy["repository"], "v1.2.3", self.sha)
        self.assertEqual("CLAWHUB_QUEUED", result["channel"])
        call = api.request.call_args
        self.assertEqual("POST", call.args[1])
        self.assertEqual({"ref": "main", "inputs": {"mode": "release", "release_tag": "v1.2.3", "source_sha": self.sha, "dry_run": "false"}}, call.args[2])
        api.tag_sha.return_value = "f" * 40
        with self.assertRaises(r.ReleaseError):
            r.dispatch_clawhub(api, self.policy["repository"], "v1.2.3", self.sha)

    def test_all_four_control_refs_must_match(self):
        pin = "a" * 40
        caller = f"""jobs:
  release:
    uses: zenstory-ai/.github/.github/workflows/source-release.yml@{pin}
    with:
      control_ref: {pin}
  clawhub-handoff:
    steps:
      - uses: actions/checkout@{'b' * 40}
        with:
          repository: zenstory-ai/.github
          ref: {pin}
          path: controls
      - run: >-
          python controls/scripts/source_release.py dispatch-clawhub
          --tag v1.2.3 --control-ref {pin}
"""
        r.check_control_pins(caller, pin)
        for position in range(4):
            # Replace only the selected occurrence without changing the other three.
            offset = [m.start() for m in re.finditer(pin, caller)][position]
            bad = caller[:offset] + "c" * 40 + caller[offset + len(pin):]
            with self.subTest(position=position), self.assertRaisesRegex(r.ReleaseError, "pins"):
                r.check_control_pins(bad, pin)
        with self.assertRaises(r.ReleaseError):
            r.check_control_pins(caller, "ROOT_REPLACE")

    def test_every_plugin_version_authority_is_checked(self):
        import json
        authorities = [(".zcode-plugin/plugin.json", "/version", {"version": "1.2.3"}),
                       ("marketplace.json", "/plugins/0/version", {"plugins": [{"version": "1.2.3"}]}),
                       ("reasonix-plugin.json", "/version", {"version": "1.2.3"})]
        for path, pointer, value in authorities:
            dest = self.root / path
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_text(json.dumps(value))
            self.policy["versionFiles"].append({"path": path, "format": "json", "pointer": pointer})
            self.policy["requiredPaths"].append(path)
        self.commit()
        r.check_contract(self.root, self.policy, self.sha)
        for path, pointer, value in authorities:
            dest = self.root / path
            original = dest.read_text()
            dest.write_text(original.replace("1.2.3", "1.2.4"))
            self.commit()
            with self.subTest(path=path), self.assertRaisesRegex(r.ReleaseError, "version"):
                r.check_contract(self.root, self.policy, self.sha)
            dest.write_text(original)
            self.commit()

    def test_workflow_pins_privilege_and_independent_artifact_identity(self):
        workflow = (P.parents[1] / ".github/workflows/source-release.yml").read_text()
        for ref in re.findall(r"uses:\s+(\S+)", workflow):
            self.assertRegex(ref, r"@[0-9a-f]{40}$")
        self.assertIn("artifact-ids: ${{ needs.build.outputs.artifact_id }}", workflow)
        self.assertIn("EXPECTED_ARCHIVE_SHA256: ${{ needs.build.outputs.archive_sha256 }}", workflow)
        self.assertIn("EXPECTED_MANIFEST_SHA256: ${{ needs.build.outputs.manifest_sha256 }}", workflow)
        self.assertEqual(1, workflow.count("contents: write"))
        self.assertNotIn("id-token: write", workflow)
        self.assertNotIn("secrets:", workflow)

    def test_fork_cannot_publish_or_manual_from_topic(self):
        self.assertFalse(r.validate_event("pull_request", "refs/pull/1/merge", False))
        self.assertTrue(r.validate_event("push", "refs/tags/v1.2.3", True))
        self.assertFalse(r.validate_event("workflow_dispatch", "refs/heads/main", False))
        for event, ref, publish in [("pull_request", "refs/pull/1/merge", True),
                                    ("workflow_dispatch", "refs/heads/topic", False),
                                    ("workflow_dispatch", "refs/heads/main", True),
                                    ("push", "refs/tags/v1.2.3-rc.1", True)]:
            with self.assertRaises(r.ReleaseError):
                r.validate_event(event, ref, publish)

    @mock.patch.object(r, "urlopen")
    def test_http_only_404_means_absence(self, urlopen):
        api = r.GitHub("test-token")
        for code in (401, 403, 429, 500):
            urlopen.side_effect = HTTPError("https://api.github.com/x", code, "error", {}, None)
            with self.subTest(code=code), self.assertRaises(r.ReleaseError):
                api.request("/x", missing_ok=True)
        urlopen.side_effect = HTTPError("https://api.github.com/x", 404, "missing", {}, None)
        self.assertIsNone(api.request("/x", missing_ok=True))

    def test_existing_asset_must_match_exact_bytes(self):
        content = b"asset"
        expected = hashlib.sha256(content).hexdigest()
        r.compare_asset({"size": len(content), "digest": "sha256:" + expected}, content)
        with self.assertRaises(r.ReleaseError):
            r.compare_asset({"size": len(content), "digest": "sha256:" + "f" * 64}, content)
        with self.assertRaises(r.ReleaseError):
            r.compare_asset({"size": 100, "digest": "sha256:" + expected}, content)

    @mock.patch.object(r, "ci_proof", return_value={"ci": []})
    @mock.patch.object(r, "anonymous_bytes")
    def test_rerun_identical_assets_never_writes_and_conflict_fails(self, public, proof):
        out = Path(self.tmp.name) / "candidate"
        manifest = r.package_source(self.root, self.policy, self.sha, out)
        names = [manifest["archive"]["name"], "RELEASE.json", "SHA256SUMS"]
        assets = [{"name": n, "size": (out / n).stat().st_size,
                   "digest": "sha256:" + hashlib.sha256((out / n).read_bytes()).hexdigest()} for n in names]
        api = mock.Mock()
        api.request.return_value = {"id": 1, "html_url": "https://github.com/example/release",
                                    "tag_name": "v1.2.3", "draft": False, "prerelease": False}
        api.pages.return_value = assets
        public.side_effect = [(out / n).read_bytes() for n in names]
        result = r.publish_release(api, self.policy, self.sha, "v1.2.3", out)
        self.assertEqual("GITHUB_PUBLISHED", result["channel"])
        self.assertTrue(all(len(x.args) < 2 or x.args[1] != "POST" for x in api.request.call_args_list))
        assets[0]["digest"] = "sha256:" + "f" * 64
        api.request.reset_mock()
        with self.assertRaisesRegex(r.ReleaseError, "never overwrite"):
            r.publish_release(api, self.policy, self.sha, "v1.2.3", out)
        self.assertTrue(all(len(x.args) < 2 or x.args[1] != "POST" for x in api.request.call_args_list))


if __name__ == "__main__":
    unittest.main()
