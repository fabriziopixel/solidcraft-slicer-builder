# SolidCraft — isolated Bambu source-build experiments

Public **source-only** build kit for the SolidCraft slicer laboratory. This repository is not the SolidCraft CAD application, Malghe Dolomiti, a production service or a print-ready slicer release. It contains only reviewed builder scripts, source patches, source hashes, tests and notices. No private models, databases, credentials or networking plugins are included.

## Incremental CI caches and latest evidence

Run `41279128051` completed C++ compilation, including `bambu-studio` and the test executables. CTest then failed six suites (including assertion failures and segmentation faults); `compiled=true` is **not** a passing candidate. Runtime diagnosis remains open; no tests are disabled or softened by this update.

The workflow now defaults to `metadata` and uses two internal Actions caches:

- A completed dependency **install prefix**, reused only with an exact dependency-tree, renderer variant, dependency recipe, compiler/CMake, OS-package inventory and runner-path identity. It is saved before application compilation, including when later compilation or CTest fails. No partial dependency build is reused.
- A bounded 2 GiB `ccache` for application/test C and C++ objects, explicitly saved on failed jobs too. Each attempt has a new snapshot key and restores the most recent compatible snapshot. Compiler launchers do not cache linker work or CTest results.

The first run is still cold. Cache transfer, linking and tests still take time; no fixed warm-run duration is promised. GitHub cache quota/eviction and hosted image/package changes can cause a cold build. These caches contain compiled public dependency/object data, not release artifacts; public repository caches must not contain secrets or private source. Diagnostic artifact uploads remain reports/logs only. No full candidate executable is uploaded or deployed.

## Manual GitHub Actions build

Open **Actions → B2 candidate build (diagnostic only) → Run workflow**.

- `x11`: two metadata fixes plus the optional X11/GLX rendering experiment.
- `metadata`: the two metadata fixes, retaining the upstream renderer.

Both variants also apply a reviewed test-only callback compatibility patch after run `41064607414` failed compiling two stale libnest2d test lambdas. The patch adds the required second argument without removing assertions or excluding tests. Run `41106982877` then failed on a stale axis-angle rotation setter in a 3MF test. A second test-only patch adapts it to the vector setter, preserving the other rotation axes and all expected results/tolerances. Run `41127129442` then exposed a stale `load_obj` call in the shared test helper. Broader static review also found obsolete writer lift/extruder calls, configuration members and brim access in active FFF tests. Additional test-only patches adapt these to the reviewed APIs while preserving numeric expectations and test coverage; runtime equivalence is not yet proven. Source and patch hashes are pinned in `docs/slicer/b2-build-fixes.json`. The main Ninja build now collects all independently reachable errors (`-k 0`) and still fails on any error. Run `41176485962` exposed additional geometry/raster test API drift and incomplete Linux test linkage. Patches `0008`/`0009` update explicit polygon types, raster type namespaces and Voronoi construction, and link the real GUI/core archives as a rescan group with wx compile settings. All test targets and assertions remain; segment Voronoi repair is explicitly disabled to preserve the former direct Boost behavior. Runs `41185587433` and `41200655878` then exposed a CMake group cycle: `libnest2d` and core link each other, so patch `0009` now includes `libnest2d` in the same rescan group as GUI/core. A synthetic regression reproduces the old failure and configures, links and runs eight tiny executables with the fixed graph before the expensive dependency build. Run `41206486085` then exposed missing `wx/string.h` in two test objects: `wxWidgets_FOUND` was not imported from the sibling src directory, so CMake's real UsewxWidgets module silently skipped setup. Patch `0009` now imports and requires that flag; the regression uses the real CMake module and reproduces the old missing-header failure before verifying all eight fixed fixture executables. Those synthetic fixtures are not engine tests; see the latest compile/CTest evidence above.

Run `41234235376` passed those CMake/wx fixes and linked `bambu-studio` plus eight test executables, but the filament-manager test lacked the `boost::format` declaration through its GUI helper. Test-only patch `0010` adds `<boost/format.hpp>` before the helper, preserving the wx-enabled test branch and all assertions. Source and patch hashes are pinned. The subsequent run `41279128051` compiled successfully but failed CTest, as described above.

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
