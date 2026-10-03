# ClawHub distribution control

ClawHub is a release channel, not a recursive mirror. Each canonical product repository owns one reviewed `.clawhub/publish.json`; this repository supplies the pinned reusable writer and an anonymous daily audit.

## Cold start and steady state

The first rollout **does not wait for another release**. `mode: bootstrap` builds from the manifest's exact 40-character `bootstrapSha`, while the manifest itself is read from reviewed `main`. It performs the same owner, rights, package, version, fingerprint, scan, and public-read gates as later releases. It never publishes drifting `main`.

After bootstrap, product callers use:

- `release`: exact commit of an approved stable GitHub release;
- `reconcile`: every 12 hours, the exact commit of the latest approved stable release;
- `validate`: token-free PR/package checks.

All three writer entries share the repository concurrency group and do not cancel a running writer. The central daily audit only reads public data and manages deduplicated issues in `zenstory-ai/.github`.

## Reusable workflow contract

Call `.github/workflows/clawhub-publish.yml` at a **full commit SHA**. Inputs are `source_ref` (full source SHA), `policy_ref` (full SHA containing the reviewed manifest), `control_ref` (the same full `zenstory-ai/.github` SHA used by `uses:`), `mode` (`validate|bootstrap|release|reconcile`), optional `manifest_path`, and optional `dry_run` (default true). Validation, release, and reconcile require `policy_ref == source_ref`. Only cold-start `bootstrap` may differ, and then the policy manifest must record `bootstrapSha == source_ref`. The only secret is `CLAWHUB_TOKEN`; it is neither required nor exposed for validation/dry-run jobs. The reusable job verifies `control_ref` against its called-workflow ref, and the central audit flags caller pin drift.

Writer concurrency belongs only to each product caller. The reusable workflow deliberately has no concurrency group, so nested reusable jobs cannot self-lock and token-free validation cannot occupy a writer slot.

`mode: validate` is deliberately offline after installing the pinned CLI. It performs schema, catalog, rights, path, license, dependency, and package-digest checks, then imports `dist/skills.js` relative to the resolved `clawhub@0.23.3` executable to compare the SDK's complete `{path,size,sha256}` inventory with the canonical staged package. It does not call the registry, authenticate, or execute skill code. When a pull-request base SHA is available, the validator reads the prior manifest with `git show`; changing package bytes, display name, categories, or topics without changing the skill version fails. A missing base manifest is allowed for the first rollout.

Bootstrap, release, and reconcile modes—including their dry runs—remain remote fail-closed plans. They retain owner, exact-version content, public scan/moderation, metadata, and remote-ahead checks; remote failures are never caught or converted into a skipped validation.

The caller repository must be a `canonical-public` entry in `clawhub-sources.json`. The workflow never runs product code and never passes `--migrate-owner`.

Writer authentication is isolated to a mode-0600 config under `runner.temp`, because `clawhub@0.23.3` does not read `CLAWHUB_TOKEN` directly. The config is created from the masked environment without putting the token in process arguments; `clawhub whoami` verifies it before writing. An EXIT trap removes the config before any artifact upload. The token is never printed or included in reports.

## Package and identity rules

- Identity is exactly `publisher/slug`; all reads and writes are owner-qualified.
- Versions are explicit semver. Same version/different client bytes is a hard conflict.
- Fingerprint is SHA-256 of `path:fileSha256` lines ordered with the pinned CLI's JavaScript `path.localeCompare()`, joined by `\n`, over original bytes. It is **not** Python byte ordering, and locale collation is runtime-sensitive. Therefore the locked CLI dry-run in the final runner is authoritative; publish rebuilds that dry-run plan in the same runner before writing. Cross-platform identity uses `packageDigest`, not a Python approximation of the CLI fingerprint.
- `packageDigest` is the cross-platform source lock: SHA-256 of canonical JSON for path-sorted `{path,sha256,size}` records. Every publish entry must carry it; validation fails after any package change until the version is bumped and the lock is refreshed. Central audit uses this digest, exact owner/version files (ignoring only `skill-card.md`), and an aggregate clean scan to count `verified` coverage.
- `include` is relative to the skill path. Escapes, symlinks, and secret-like files fail closed.
- Generated Python bytecode is never package input: any `__pycache__` path component and any `.pyc` or `.pyo` file is deterministically excluded before inventory, fingerprint, and `packageDigest` calculation. This is independent of repository ignore files and prevents local test execution from changing release bytes.
- If the skill has no own license file, the repository's first `LICENSE*` is copied unchanged into the package. Source licenses are not rewritten or relicensed.
- ClawHub's exact server-generated `skill-card.md` is recorded and excluded from the client fingerprint comparison. Any other extra remote file changes the fingerprint and conflicts.
- `runtimeDependsOn` entries beginning with `skill:` use `skill:owner/slug@semver`. The controller generates `INSTALL.md` with exact-version companion commands. Owner-qualified installs live at `skills/@owner/slug`; cross-owner physical-sibling dependencies are rejected unless a future reviewed adapter contract is added. Cycles are allowed; dependencies are not a build DAG. A skill is not `DISTRIBUTION_VERIFIED` until every declared companion version is public with an aggregate clean scan.
- ClawHub does not auto-install companions. Same-root isolated closure checks remain a product verification responsibility; the generated instructions do not claim automatic installation.

Publishing on ClawHub applies MIT-0. ZenStory's creator confirmed organization contributor authorization on 2026-10-03; canonical self-authored items record `permission-recorded` evidence in each product's `.clawhub/README.md`. Third-party `browser-cdp` remains excluded. Rights confirmation never bypasses owner, package, version, scan, or public verification.

Catalog categories/topics are sent for a new item or when the public API proves a difference. Public topics are read from `skill.topics`; categories are compared only if a public field exists. If the API does not expose a field, reports mark it `metadataUnobserved`; absence is not treated as either equality or permission to republish. Source flags and local provenance hashes are audit evidence only and do not claim that ClawHub resolved a server-side GitHub import.

## Local commands

```sh
python3 scripts/clawhub_release.py validate --manifest .clawhub/publish.json --repo-root . --clawhub-bin "$(command -v clawhub)" --base-ref "$BASE_SHA" --output inventory.json
python3 scripts/clawhub_release.py lock --manifest .clawhub/publish.json --repo-root .
python3 scripts/clawhub_release.py plan --manifest .clawhub/publish.json --repo-root . --output plan.json --clawhub-bin "$(command -v clawhub)"
python3 scripts/clawhub_release.py publish --manifest .clawhub/publish.json --repo-root . --plan plan.json --report report.json --clawhub-bin "$(command -v clawhub)"
python3 scripts/clawhub_release.py verify --manifest .clawhub/publish.json --repo-root . --report verify.json
python3 scripts/clawhub_release.py audit --catalog clawhub-sources.json --output audit.json
```

`publish` re-hashes the manifest and every package before each run. Matching public owner/version/content is a verified no-op; explicit `--version` is never invoked until the resolve/version checks show a missing target version. `pending-publication` and `submitted` remain pending, not verified.

Anonymous registry reads retry at most three total attempts for timeouts, network failures, HTTP 429, and 5xx responses. Numeric or HTTP-date `Retry-After` is honored with a 30-second cap; otherwise delays are 1 and 2 seconds. Authentication/authorization failures, malformed JSON, owner conflicts, and content/version blockers are not retried or converted into success.
