# How to cut a release

Releases are manual and made from `main`. The workflow runs the full test matrix first, then
tags the commit it tested and creates a GitHub release with generated notes.

1. Open **Actions → CD → Run workflow** on the `main` branch.
2. Leave `version` empty to bump the patch of the latest `X.Y.Z` tag (`0.1.0` if there is
   none), or type the version, such as `0.2.0`, for a minor or major bump.
3. Run it. If any test job fails, nothing is tagged.

Tags and versions have no `v` prefix. The workflow refuses to run from another branch, to
reuse an existing tag, or to release a version older than the latest.
