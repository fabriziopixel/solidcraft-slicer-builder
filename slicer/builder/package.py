"""Create a deterministic, allowlisted source-only kit; never include the CAD repo/credentials."""
import argparse
import gzip
import hashlib
import io
import json
from pathlib import Path
import tarfile

from .driver import ROOT, REVISION

FILES = (
    "slicer/builder/README.md",
    "slicer/builder/PUBLIC-README.md",
    "slicer/builder/build-candidate.workflow.yml",
    "slicer/builder/driver.py",
    "slicer/builder/diagnose.py",
    "slicer/builder/package.py",
    "slicer/tests/test_builder.py",
    "slicer/tests/test_diagnose.py",
    "slicer/tests/test_cmake_linkage.py",
    "slicer/engine/patches/0001-first-layer-statistics.patch",
    "slicer/engine/patches/0002-filament-volume-units.patch",
    "slicer/engine/patches/0004-libnest2d-test-callback.patch",
    "slicer/engine/patches/0005-3mf-test-rotation.patch",
    "slicer/engine/patches/0006-obj-test-loader.patch",
    "slicer/engine/patches/0007-fff-test-current-api.patch",
    "slicer/engine/patches/0008-geometry-raster-test-api.patch",
    "slicer/engine/patches/0009-linux-test-link-dependencies.patch",
    "slicer/engine/patches/0010-fila-manager-test-boost-format.patch",
    "slicer/engine/patches/0011-fill-test-pattern-name.patch",
    "slicer/engine/patches/0012-config-test-current-schema.patch",
    "slicer/engine/patches/0013-nfp-degenerate-and-optional-progress.patch",
    "slicer/engine/patches/0014-test-option-preconditions.patch",
    "docs/slicer/b2-build-fixes.json",
    "docs/slicer/B2-RUNTIME-DIAGNOSIS.md",
    "slicer/engine/experiments/0003-x11-glx-rendering.patch",
    "slicer/engine/LICENSE.BambuStudio.txt",
    "slicer/engine/NOTICE.md",
    "docs/slicer/b2-source-index.json",
    "docs/slicer/b2-source-results.json",
    "docs/slicer/b2-build-source-index.json",
    "docs/slicer/b2-render-experiment.json",
)


def package(root, output):
    if output.exists() or output.is_symlink():
        raise ValueError("refusing to overwrite an existing kit")
    files = {}
    for name in FILES:
        path = root / name
        if path.is_symlink() or not path.is_file() or path.resolve().is_relative_to(root.resolve()) is False:
            raise ValueError("missing/unsafe kit source: " + name)
        data = path.read_bytes()
        if len(data) > 2 * 1024**2:
            raise ValueError("unexpected kit file size")
        files[name] = data
    manifest = {"format": 1, "upstream_revision": REVISION, "compiled": False, "printer_ready": False,
                "files": {name: {"sha256": hashlib.sha256(data).hexdigest(), "bytes": len(data)}
                          for name, data in files.items()}}
    files["builder-kit-manifest.json"] = (json.dumps(manifest, sort_keys=True, indent=2) + "\n").encode()
    with output.open("xb") as raw, gzip.GzipFile(filename="", fileobj=raw, mode="wb", mtime=0) as gz:
        with tarfile.open(fileobj=gz, mode="w") as archive:
            for name, data in sorted(files.items()):
                info = tarfile.TarInfo(name)
                info.size = len(data)
                info.mode = 0o644
                info.mtime = info.uid = info.gid = 0
                archive.addfile(info, io.BytesIO(data))
    return hashlib.sha256(output.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    print(package(ROOT, args.output) + "  " + str(args.output))


if __name__ == "__main__":
    main()
