# B2 external-builder kit (experimental, not yet built)

This kit prepares **candidate source builds**, not print-ready output. It contains no CAD application, private model, DB dump, credentials, AppImage, networking plugin or production runtime image. Nothing publishes to production or changes the existing engine lock.

## Build status and CI

The separately authorized source-only GitHub repository is available at https://github.com/fabriziopixel/solidcraft-slicer-builder. Its workflow template is `build-candidate.workflow.yml`; it runs manually on standard disposable GitHub-hosted Ubuntu runners, without VPS access or paid/larger runners. Only diagnostic reports are uploaded, not executables. Actual build status must be checked in Actions; preparing the recipe is not evidence of compilation or successful rendering. The standalone driver does not provision hosts.

Use a dedicated, disposable **Linux x86_64 VM**, recommended 16+ GiB RAM and 60+ GiB free disk, with no credentials or production mounts. Preflight requires at least 12 GiB **available** RAM and 40 GiB free disk. Do not use the CAD VPS, including through a container hiding the production directory. The driver has an explicit confirmation gate and rejects the known `/opt/solidcraft` deployment marker, existing output directories and insufficient resources. This is an administrative guard, not a sandbox/security boundary. Do not run concurrently with valuable workloads. Network is needed for public upstream dependency downloads during compilation; candidate slicing must later run in a separate network-disabled sandbox.

The VM must already have the development packages required by the pinned upstream `linux.d/debian`, plus Python 3, Git, CMake, CTest, Ninja, a C++ compiler and pkg-config. Review the upstream prerequisite list and install it **on that disposable VM only**. The driver never runs apt, sudo, cloud APIs or package installation. Distribution/package compatibility is untested; do not claim the recipe is an end-to-end verified build. Capture the VM/base image digest and repository snapshots before attempting a reproducible build. Recording installed package versions alone is not dependency freezing.

## Reviewed retry after the first CI failure

Run `41064607414` failed during compilation of `tests/libnest2d/libnest2d_tests_main.cpp`, before CTest. Two test callbacks still use a one-argument signature, while the pinned `NfpPConfig::object_function` requires both item and packed items. Candidate patch `0004-libnest2d-test-callback.patch` adds the unused second parameter only; objectives, assertions, production nesting code and the full test selection are unchanged. `docs/slicer/b2-build-fixes.json` pins both reviewed sources and the patch hash. The driver verifies them before applying the patch to either variant. Local patch applicability and Python tests are not a successful C++ build. A new manual run is required; no automatic retry loop is configured.

Run `41106982877` advanced past those callbacks but failed compiling `tests/libslic3r/test_3mf.cpp:97`: the axis-angle `ModelInstance::set_rotation` overload is no longer available. Test-only patch `0005-3mf-test-rotation.patch` reads the current rotation vector, changes its X component to the same angle and calls the vector setter. Other axes, expected geometry, tolerances and assertions are preserved. The test and `Model.hpp` hashes are also pinned in the build-fix manifest. No runtime code or test selection is changed; compilation/CTest still requires another manual attempt.

## Broader static API review after the third failed build

Run `41127129442` failed on the shared `load_obj` test helper, whose current API also requires `ObjInfo` and a message output. Patch `0006` supplies these outputs without changing the mesh or the loader defaults. A broader scan of 75 test/build files and 57 directly included headers found additional active FFF test API drift addressed by `0007`:

- `set_extruder(0, 0)` explicitly selects filament/nozzle 0 for the single-extruder fixture;
- `eager_lift(LiftType::NormalLift)` requests the immediate vertical lift tested by the old `lift()` assertions; `lazy_lift` would defer motion and is not substituted;
- `z_hop` and `initial_layer_print_height` replace removed configuration members;
- brim counts now sum the per-object map, preserving the original entity vs recursive item count and numeric expectations for these object-only fixtures.

Source/API hashes are checked by the build-fix manifest. All four test patches apply in a new reviewed-source copy; assertion/test counts, numeric comparison constants and existing disabled blocks are preserved. This static review is **not** a C++ type check or proof of equivalent runtime behavior. Old configuration keys in test input files may still cause runtime failures; none are silently renamed or discarded to force a green test.

The main Ninja build now uses `-k 0` to compile all independently reachable targets even after an error. It still exits nonzero for any failure, keeps compiler parallelism bounded, and does not run CTest on an incomplete build. The dependency superbuild remains serial/fail-fast. This collects more diagnostics per attempt, not an exception to the success gate. No automatic retry loop or test exclusions were added.

## Fetch public upstream sources on the builder

```sh
mkdir upstream && git -C upstream init
 git -C upstream remote add origin https://github.com/bambulab/BambuStudio.git
 git -C upstream fetch --depth 1 origin 926a7192574bcb9b3a732e1ec59a46d79cb45466
 git -C upstream checkout --detach FETCH_HEAD
```

No submodules are present in the pinned tree acquired during this investigation. The driver still checks for gitlinks and refuses unreviewed ones. The source commit pins the dependency recipes, **not every external download or OS package**. Upstream's GLFW recipe pins version 3.3.7 and a SHA256; the whole transitive supply chain remains to be audited. No claim of bit-identical reproducibility is made.

## Transfer/verify the kit

Transfer only the generated `solidcraft-b2-builder-kit.tar.gz` and its communicated SHA256 over an authorized channel. Verify the checksum before extracting into an empty directory. It contains `builder-kit-manifest.json` with hashes of each allowlisted file. This is integrity metadata, not an independent signature. The archive is source-only, not an encrypted backup or off-site recovery of SolidCraft.

From the extracted kit root:

```sh
python3 -m unittest discover -s slicer/tests -p test_builder.py -v
# Inert inspection, permitted on any host; does not clone/configure/build:
python3 -m slicer.builder.driver --source /builder/upstream \
  --output /builder/candidate-metadata --plan
# RUN ONLY ON THE AUTHORIZED EXTERNAL VM. New output path required.
python3 -m slicer.builder.driver --source /builder/upstream \
  --output /builder/candidate-metadata --confirm-isolated-builder
```

The driver clones the local checkout into a new output directory, checks out the exact revision, verifies the 13 reviewed source hashes and both metadata-patch hashes, applies patches in the copy, then configures/builds dependencies and Studio with tests enabled. Default parallelism is one; `--jobs 2` is the bounded CI option, while the top-level dependency superbuild stays serial. Third-party build subprocesses receive an allowlisted environment without CI tokens. `ctest --no-tests=error` refuses an empty test run. The original checkout is not patched. There is no build resume/cleanup switch: preserve a failed attempt for inspection and choose a new output directory for another attempt. A build can take hours; stop the disposable VM if cancellation leaves compiler children running. This initial driver does not supply a production scheduler, hard build-time quotas or cgroup supervision.

## Optional rendering experiment, NOT the default

Additional investigation of the same revision found:

- `deps/GLFW/GLFW.cmake` explicitly sets `GLFW_USE_WAYLAND=ON` on Linux;
- bundled `deps/GLEW/glew/CMakeLists.txt` says Wayland is unsupported and does not enable EGL on Linux;
- the active CLI renderer requests an OSMesa context and uses GLFW's library version as an OpenGL version.

An experimental third patch switches the GLFW dependency to X11, requests a native GLX context, and requests OpenGL 3.3 explicitly. It does **not** skip GLEW validation or generate fake images. Patch applicability after the metadata series was tested; **compilation and rendering were not**. This is a proposed coherent stack, not a proven fix of the AppImage's precise runtime failure. The commented-out old rendering code is intentionally untouched.

On the external builder use a separate output directory:

```sh
python3 -m slicer.builder.driver --source /builder/upstream \
  --output /builder/candidate-x11 --confirm-isolated-builder --render-experiment
```

Only after compilation, package each candidate with its resources and shared-library inventory into a **new** runtime image. For the X11 candidate, an X server and Mesa software rendering are required, e.g. Xvfb/GLX with `LIBGL_ALWAYS_SOFTWARE=1`. Xvfb alone could not fix the old Wayland/OSMesa binary; this variant requires rebuilding the dependency and executable. Test the exact binary/resource bundle in a network-disabled sandbox. Do not replace the B3 image, copy the candidate into production, suppress errors or automatically update `engine.lock.json`. Build outputs are not yet installed/packaged by this driver.

## Reports and acceptance

Each attempt writes `build-report.json`, `build.log`, reviewed `candidate.diff`, `toolchain.txt`, package inventory when available, CMake caches/build tree and test logs. Failures remain `failed`; all reports keep `printer_ready=false` and `production_approved=false`, even if C++ tests pass. The two variants need separate reports and runtime-image digests. Never send a VM's entire home directory/environment back: return only reviewed logs, diffs, hashes and candidate artifacts. Preserve exact downloaded dependencies, source/build material and third-party notices for license and reproducibility review before any applicable distribution.

Compilation/CTest success does not close B2. Still required: repeated cube/cylinder/overhang OFF/Normal/Tree slicing; first-layer source/metadata consistency; volume/mass/length unit checks; real model thumbnails and 3MF references; timeout/cancel/OOM tests; review of timelapse warnings; independent Studio GUI comparison and the remaining firmware/device/legal gates. No output may be sent to a printer as part of this kit.

## Regenerating the source-only archive

From the authorized SolidCraft slicer repository:

```sh
python3 -m slicer.builder.package /new/path/solidcraft-b2-builder-kit.tar.gz
```

The packager is deterministic, includes only an explicit file allowlist, rejects symlinks and refuses overwrite. `.git`, `.env`, production code, database files and runtime outputs are not included. The patch code derives from the pinned Bambu Studio source under the supplied AGPL-3.0 license; preserve notices. Legal clearance of a combined hosted product remains a separate gate.
