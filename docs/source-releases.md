# Public skill source-release contract

Applies only to `oh-story-claudecode`, `drama-skills`, `novel-to-game`, and
`video-recap-skills`. Private repositories are excluded. DSH and the ZenStory npm
CLI keep native npm workflows; hosting keeps its own provider contract.

## Product ownership

Each repository owns `.release/policy.json`, its version/changelog, its tag-push
predicate and its separately scoped ClawHub dispatch. Both the reusable workflow
and its `control_ref` checkout must use the same reviewed full commit SHA.
The shared publisher uses **the caller repository's `GITHUB_TOKEN`**, never an
organization-wide write token. Policy/allowlisting validates mechanics, not human
authorization. Main protection and review remain necessary.

The policy's `versionFiles` uses exact text paths or JSON pointers; do not infer
versions by searching all JSON. Repository versions are independent of per-skill
ClawHub versions. `requiredPaths` lists installable product files, `excludePaths`
lists explicit relative prefixes/globs, and `ciWorkflows` lists workflow filenames
and exact successful matrix/job names. `schemaVersion` is `1`.

## Release path

1. Update existing version authorities and prepare the dated changelog normally.
   This rollout does not bump versions or create tags.
2. Merge through existing protected checks. Primary and inventory workflows run
   on every main push. CI proof binds repository, workflow ID/path, push/main,
   exact SHA, run ID, newest attempt, check-suite Actions app and matrix jobs.
   A new failed/pending run never falls back to an older success.
3. Push stable `vX.Y.Z` from a commit on protected main. The tag must resolve to
   that exact commit. PR verification has no publish permission; explicit main
   dispatch is a **nonpublishing** dry-run.
4. Package tracked source once. Internal plugin aliases are preserved; escaping,
   dangling/cyclic links, entry paths through links, secrets and runtime caches
   are rejected. Untracked local files are never packaged. Normalized tar/gzip
   metadata and a per-file inventory make repeat builds comparable.
5. Promote the exact run/attempt artifact ID. Recheck archive/source/version/hash
   and current CI/tag identity before publication. Upload the archive,
   `RELEASE.json`, and `SHA256SUMS`; anonymously compare public bytes afterwards.
   Per-run CI proof stays in the workflow artifact, not deterministic release
   metadata. HTTP/network/auth failures are not treated as a missing release.

This is workflow-enforced append-only/idempotent behavior, **not** proof of
GitHub host-immutable tags/releases. No `--clobber`, deletion or overwrite is
used. Existing different bytes, duplicate names or a moved tag fail. Partial
upload failure can be safely retried only while existing bytes and source agree.
Host tag/update protection and immutable-release settings require separate
administrative verification.

## ClawHub handoff and outcomes

`GITHUB_TOKEN`-created Releases do not start ordinary `release.published`
workflows. Each caller therefore has a distinct `actions: write` dispatch job
after the source publisher succeeds; the source publisher itself only needs
`contents: write`. The existing ClawHub dispatch supports exact `mode=release`,
`release_tag` and `source_sha` and rechecks the fetched tag/stable Release.

An acknowledged dispatch is **`CLAWHUB_QUEUED`**, not published/scan-clean.
ClawHub's existing ownership, rights, per-skill version/hash and scan gates plus
the daily anonymous audit remain authoritative. No workflow bypasses suspicious
scans or silently waits for the next scheduled reconciliation.

## Offline validation

```sh
python -m unittest discover -s tests -v
python -m py_compile scripts/source_release.py
```

Tests cover exact version/tag/source, reproducible archives and internal aliases,
wrong/fork/failed CI identities, missing/skipped matrix jobs, newest failed runs,
404-versus-auth/network errors, digest conflicts and forbidden publication events.
Tests and PR validation perform no public writes or provider calls. A new real
tagged publish is a separate release operation; a successful dry-run is not proof
that npm/hosting/ClawHub publication executed.
