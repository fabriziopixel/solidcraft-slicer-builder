# SolidCraft — isolated Bambu source-build experiments

Public **source-only** build kit for the SolidCraft slicer laboratory. This repository is not the SolidCraft CAD application, Malghe Dolomiti, a production service or a print-ready slicer release. It contains only reviewed builder scripts, source patches, source hashes, tests and notices. No private models, databases, credentials or networking plugins are included.

## Manual GitHub Actions build

Open **Actions → B2 candidate build (diagnostic only) → Run workflow**.

- `x11`: two metadata fixes plus the optional X11/GLX rendering experiment.
- `metadata`: the two metadata fixes, retaining the upstream renderer.

Only standard `ubuntu-24.04` GitHub-hosted runners are used; no paid/larger or self-hosted runner and no VPS access. GitHub account policy/quotas can still block a job. Runs are manual, serialized and limited to 350 minutes. The runner must have at least 12 GiB available RAM and 40 GiB free disk after removal of fixed unused SDK directories on that disposable runner. No resource gate is bypassed. Prerequisites are installed on the runner, never on the CAD VPS.

The workflow checks out Bambu Studio revision `926a7192574bcb9b3a732e1ec59a46d79cb45466`, verifies reviewed source/patch hashes, builds dependencies and the candidate, and requires nonempty CTest results. Compiler parallelism is capped at two; the top-level dependency superbuild remains serial. OS repositories and all transitive downloads are **not yet frozen**, so this is experimental, not a reproducible or audited release recipe.

The workflow has read-only repository permissions, does not persist checkout credentials, and does not trigger on pull requests. Build subprocesses receive an allowlisted environment without CI tokens. **Only diagnostic reports/logs/diffs are uploaded**, retained seven days: no executable, AppImage, runtime image or arbitrary home-directory contents. Successful compilation alone does not validate rendering, 3MF metadata, desktop equivalence or physical printing. A separate source/license/artifact review is required before distributing a candidate binary.

No release, registry push, production deployment, database access, networking plugin installation or printer connection is implemented. `printer_ready` and `production_approved` remain false, even on a green build.

## Local checks (no compilation)

```sh
python3 -m unittest discover -s slicer/tests -p test_builder.py -v
python3 -m slicer.builder.driver --source /builder/upstream --output /builder/new-candidate --plan
```

See [external-builder instructions](slicer/builder/README.md) for prerequisites, source checkout, limitations and the optional renderer experiment. The full compile driver refuses the known CAD VPS layout; the workflow contains no credentials or channel to reach it.

## License and provenance

The patches derive from the pinned Bambu Studio source and are supplied under its AGPL-3.0 license. See [upstream license](slicer/engine/LICENSE.BambuStudio.txt) and [notices](slicer/engine/NOTICE.md). The original SolidCraft-authored build scripts, tests and documentation in this repository are also supplied under AGPL-3.0; this does not grant rights to any private SolidCraft or Malghe Dolomiti application code. Dependencies and assets can carry additional licenses. This repository is not a claim of legal clearance for a combined hosted application.
