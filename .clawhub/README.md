# Shared skill distribution

`publish.json` lists the four organization skills released on ClawHub by
`worldwonderer`. Every entry starts at `1.0.0` and locks its exact file inventory.
`you-click-publish` has been removed from the repository and is not a release entry.

## Rights

The organization creator recorded contributor permission for MIT-0 distribution
on 2026-10-03, as documented in `docs/clawhub-distribution.md`. On 2026-10-14 the
maintainer requested distribution of the organization skills and supplied
`prose-gap-polish.zip` to replace `you-click-publish`. The imported `SKILL.md`
matches the supplied file byte for byte. Existing source license declarations
remain unchanged; ClawHub's MIT-0 distribution terms apply to the released copies.

## Publish

Configure the repository Actions secret `CLAWHUB_TOKEN` for the `worldwonderer`
publisher. First preview the immutable bootstrap packages:

```sh
gh workflow run publish-skills.yml --repo zenstory-ai/.github --ref main -f mode=bootstrap -f dry_run=true
```

After checking the plan, publish the same snapshot:

```sh
gh workflow run publish-skills.yml --repo zenstory-ai/.github --ref main -f mode=bootstrap -f dry_run=false
```

The bootstrap source commit contains the skills and identity catalog but no
manifest. Its following commit adds the policy manifest and workflow, both
referring to that immutable source. Preserve the bootstrap commit when merging;
squashing or rebasing these rollout commits would change the recorded SHA.

Automatic publishing is opt-in: configure a persistent `CLAWHUB_TOKEN` and set
the repository Actions variable `CLAWHUB_AUTO_PUBLISH=true` to consume stable
GitHub Releases and reconcile every 12 hours. Leave that variable unset when
using a temporary key, and remove the temporary repository secret after the
first publication. Manual dry runs remain available without credentials.

Later skill changes require a per-skill version bump, refreshed `packageDigest`,
and a stable GitHub Release on `main`. Editing drifting `main` alone does not
replace an already approved release. The anonymous daily audit covers these
four skills alongside the product skill packs.
