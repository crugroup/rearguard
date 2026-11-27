# How to cut a release

Every push to `main` whose CI run succeeds is released automatically. The CD workflow tags the
commit CI tested and creates a GitHub release with generated notes, bumping the patch of the
latest `X.Y.Z` tag (`0.1.0` if there is none). Nothing is tagged if any CI job fails, or if
the CI run was for a pull request.

When several pushes land close together, only the one that is still the tip of `main` when
its CI finishes is released, so a newer commit never gets an older version.

## For a minor or major version

1. Open **Actions → CD → Run workflow** on the `main` branch.
2. Type the version, such as `0.2.0`.
3. Run it. It runs the full test matrix first, then tags the tip of `main`.

Tags and versions have no `v` prefix. The workflow refuses to run by hand from another branch,
to reuse an existing tag, or to release a version older than the latest.
