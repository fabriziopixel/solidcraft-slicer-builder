"""Experimental external-builder driver. Never run on the CAD VPS."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import time

REVISION = "926a7192574bcb9b3a732e1ec59a46d79cb45466"
ROOT = Path(__file__).resolve().parents[2]
PRODUCTION_MARKER = Path("/opt/solidcraft")
MIN_RAM = 12 * 1024**3
MIN_DISK = 40 * 1024**3


def resources(parent):
    available = next(int(line.split()[1]) * 1024 for line in Path("/proc/meminfo").read_text().splitlines()
                     if line.startswith("MemAvailable:"))
    return available, shutil.disk_usage(parent).free


def preflight(source, output, confirmed, available=None):
    if not confirmed:
        raise ValueError("explicit --confirm-isolated-builder is required")
    if platform.system() != "Linux" or platform.machine() != "x86_64":
        raise ValueError("initial candidate requires Linux x86_64")
    # Deliberately no override for the known production host layout.
    if PRODUCTION_MARKER.exists():
        raise ValueError("CAD deployment detected: full build forbidden on this host")
    if output.exists() or output.is_symlink():
        raise ValueError("output must be a new directory; no overwrite/resume")
    if not source.is_dir() or not output.parent.is_dir():
        raise ValueError("source and output parent must exist")
    ram, disk = available if available is not None else resources(output.parent)
    if ram < MIN_RAM or disk < MIN_DISK:
        raise ValueError("external builder needs >=12 GiB available RAM and >=40 GiB free disk")
    for tool in ["git", "cmake", "ctest", "ninja", "c++", "pkg-config"]:
        if not shutil.which(tool):
            raise ValueError("missing builder prerequisite: " + tool)
    return {"available_ram_bytes": ram, "free_disk_bytes": disk}


def plan(source, jobs=1, ccache=False):
    """No execution or resource allocation: paths relative to a new output directory."""
    return [
        ["git", "clone", "--no-hardlinks", "--no-checkout", str(source), "source"],
        ["git", "-C", "source", "checkout", "--detach", REVISION],
        ["cmake", "-S", "source/deps", "-B", "deps-build", "-G", "Ninja",
         "-DCMAKE_POLICY_VERSION_MINIMUM=3.5", "-DDEP_WX_GTK3=ON", "-DCMAKE_BUILD_TYPE=Release"],
        ["cmake", "--build", "deps-build", "--parallel", "1"],
        ["cmake", "-S", "source", "-B", "build", "-G", "Ninja",
         "-DCMAKE_PREFIX_PATH={OUTPUT}/deps-build/destdir/usr/local", "-DSLIC3R_STATIC=1",
         "-DSLIC3R_GTK=3", "-DCMAKE_BUILD_TYPE=Release", "-DBBL_RELEASE_TO_PUBLIC=1",
         "-DBBL_INTERNAL_TESTING=0", "-DSLIC3R_BUILD_TESTS=ON",
         *(["-DCMAKE_C_COMPILER_LAUNCHER=ccache", "-DCMAKE_CXX_COMPILER_LAUNCHER=ccache"] if ccache else [])],
        # Collect all independently reachable compile failures in one attempt.
        # Ninja still exits nonzero on any failure; CTest is never skipped on success.
        ["cmake", "--build", "build", "--parallel", str(jobs), "--", "-k", "0"],
        ["ctest", "--test-dir", "build", "--output-on-failure", "--no-tests=error"],
    ]


def build_fixes(checkout):
    """Verify reviewed compatibility/runtime patch sources before applying any patch."""
    fixes = json.loads((ROOT / "docs/slicer/b2-build-fixes.json").read_text())
    if fixes["revision"] != REVISION:
        raise ValueError("build fix revision mismatch")
    for entry in fixes["sources"]:
        if hashlib.sha256((checkout / entry["path"]).read_bytes()).hexdigest() != entry["sha256"]:
            raise ValueError("build fix source mismatch: " + entry["path"])
    return fixes["patches"]


def save(path, value):
    temp = path.with_suffix(".tmp")
    temp.write_text(json.dumps(value, indent=2) + "\n")
    temp.replace(path)


def dependency_identity(checkout, render_experiment):
    """Strict identity: dependency tree, variant, toolchain, OS packages and recipe."""
    def capture(argv):
        return subprocess.check_output(argv, cwd=checkout, text=True).strip()
    return {
        "schema": 1,
        "deps_tree": capture(["git", "rev-parse", "HEAD:deps"]),
        "render_patch": hashlib.sha256((ROOT / "docs/slicer/b2-render-experiment.json").read_bytes()).hexdigest()
                        if render_experiment else None,
        "recipe": plan(checkout)[2:4],
        "compiler": capture(["c++", "--version"]),
        "cmake": capture(["cmake", "--version"]),
        "packages": hashlib.sha256(capture(["dpkg-query", "-W", "-f=${Package}=${Version}\\n"]).encode()).hexdigest(),
    }


def restore_dependencies(cache, destination, identity):
    if not (cache / "identity.json").is_file():
        return False
    if json.loads((cache / "identity.json").read_text()) != identity:
        raise ValueError("dependency cache identity mismatch; use a fresh cache")
    if not (cache / "prefix").is_dir():
        raise ValueError("incomplete dependency cache")
    shutil.copytree(cache / "prefix", destination, symlinks=True)
    return True


def store_dependencies(cache, prefix, identity):
    if cache.exists():
        raise ValueError("refusing to overwrite dependency cache")
    if not prefix.is_dir() or not any(prefix.iterdir()):
        raise ValueError("dependency install prefix missing or empty")
    temporary = cache.with_name(cache.name + ".tmp")
    temporary.mkdir(mode=0o700)
    shutil.copytree(prefix, temporary / "prefix", symlinks=True)
    save(temporary / "identity.json", identity)
    temporary.rename(cache)


def build(source, output, confirmed, render_experiment=False, jobs=1, dependency_cache=None, ccache=False):
    if jobs not in (1, 2):
        raise ValueError("only one or two compiler jobs permitted")
    limits = preflight(source, output, confirmed)
    if ccache and not shutil.which("ccache"):
        raise ValueError("ccache requested but not installed")
    if dependency_cache is not None:
        dependency_cache = dependency_cache.resolve()
        if dependency_cache == output.resolve() or output.resolve() in dependency_cache.parents:
            raise ValueError("dependency cache must be outside output")
    output.mkdir(mode=0o700)
    report = {"revision": REVISION, "resources": limits, "state": "preparing", "steps": [],
              "compiled": False, "tests_passed": False, "printer_ready": False,
              "production_approved": False, "started_unix": time.time(),
              "render_experiment": render_experiment, "compiler_jobs": jobs,
              "limitations": ["Earlier candidates compiled but failed CTest; new patches still require validation.",
                              "OS packages and upstream dependency downloads not yet frozen.",
                              "Includes candidate NFP runtime guards; metadata/rendering acceptance remains open."]}
    report_path = output / "build-report.json"
    save(report_path, report)
    # Do not pass CI tokens or unrelated credentials to third-party build scripts.
    env = {key: value for key, value in os.environ.items() if key in {
        "PATH", "HOME", "USER", "LOGNAME", "LANG", "LC_ALL", "TMPDIR", "TERM", "SHELL",
        "CC", "CXX", "PKG_CONFIG_PATH", "CMAKE_PREFIX_PATH",
        "CCACHE_DIR", "CCACHE_BASEDIR", "CCACHE_MAXSIZE", "CCACHE_COMPILERCHECK"}}
    env.update({"CMAKE_BUILD_PARALLEL_LEVEL": str(jobs), "GIT_CONFIG_NOSYSTEM": "1",
                "GIT_CONFIG_GLOBAL": "/dev/null", "GIT_TERMINAL_PROMPT": "0"})

    def run(argv, capture=False):
        argv = [str(a).replace("{OUTPUT}", str(output)) for a in argv]
        with (output / "build.log").open("ab") as log:
            log.write(("\n$ " + json.dumps(argv) + "\n").encode())
            log.flush()
            print("builder step: " + json.dumps(argv), flush=True)
            proc = subprocess.run(argv, cwd=output, env=env, stdout=subprocess.PIPE if capture else log,
                                  stderr=log, check=True)
        report["steps"].append(argv)
        save(report_path, report)
        return proc.stdout.decode() if capture else None

    try:
        commands = plan(source, jobs, ccache=ccache)
        for command in commands[:2]:
            run(command)
        checkout = output / "source"
        if run(["git", "-C", str(checkout), "rev-parse", "HEAD"], True).strip() != REVISION:
            raise ValueError("unexpected source revision")
        if any(line.startswith("160000") for line in run(["git", "-C", str(checkout), "ls-tree", "-r", "HEAD"], True).splitlines()):
            raise ValueError("unreviewed submodule dependency: stop and pin separately")
        index = json.loads((ROOT / "docs/slicer/b2-source-index.json").read_text())
        for entry in index:
            if hashlib.sha256((checkout / entry["path"]).read_bytes()).hexdigest() != entry["sha256"]:
                raise ValueError("upstream file mismatch: " + entry["path"])
        expected = json.loads((ROOT / "docs/slicer/b2-source-results.json").read_text())["patches"]
        if render_experiment:
            experiment = json.loads((ROOT / "docs/slicer/b2-render-experiment.json").read_text())
            for entry in experiment["additional_sources"]:
                if hashlib.sha256((checkout / entry["path"]).read_bytes()).hexdigest() != entry["sha256"]:
                    raise ValueError("render source mismatch: " + entry["path"])
            expected.append(experiment["patch"])
        expected.extend(build_fixes(checkout))
        report["patches"] = expected
        for entry in expected:
            patch = ROOT / entry["path"]
            if hashlib.sha256(patch.read_bytes()).hexdigest() != entry["sha256"]:
                raise ValueError("patch hash mismatch: " + entry["path"])
            run(["git", "-C", str(checkout), "apply", "--check", str(patch)])
            run(["git", "-C", str(checkout), "apply", str(patch)])
        (output / "candidate.diff").write_text(run(["git", "-C", str(checkout), "diff", "--binary"], True))
        (output / "toolchain.txt").write_text("\n".join(
            run([tool, "--version"], True) for tool in ["cmake", "ninja", "c++", "git"]))
        if shutil.which("dpkg-query"):
            (output / "os-packages.tsv").write_text(run(["dpkg-query", "-W", "-f=${Package}\t${Version}\n"], True))
        report["state"] = "building"
        save(report_path, report)
        prefix = output / "deps-build/destdir/usr/local"
        identity = dependency_identity(checkout, render_experiment) if dependency_cache else None
        restored = bool(dependency_cache and restore_dependencies(dependency_cache, prefix, identity))
        report["dependency_cache_hit"] = restored
        report["ccache_enabled"] = ccache
        save(report_path, report)
        if not restored:
            for command in commands[2:4]:
                run(command)
            # Persist completed dependencies BEFORE the application can fail.
            if dependency_cache:
                store_dependencies(dependency_cache, prefix, identity)
        for command in commands[4:-1]:
            run(command)
        binary = output / "build/src/bambu-studio"
        if not binary.is_file():
            raise ValueError("expected candidate executable missing")
        report["compiled"] = True
        report["binary_sha256"] = hashlib.sha256(binary.read_bytes()).hexdigest()
        report["state"] = "testing"
        save(report_path, report)
        run(commands[-1])
        report["tests_passed"] = True
        report["state"] = "candidate_built_not_release_ready"
    except BaseException as exc:
        report["state"] = "failed"
        report["error"] = type(exc).__name__ + ": " + str(exc)
        raise
    finally:
        report["finished_unix"] = time.time()
        save(report_path, report)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True, help="existing local upstream Git clone")
    parser.add_argument("--output", type=Path, required=True, help="new directory on external builder")
    parser.add_argument("--confirm-isolated-builder", action="store_true")
    parser.add_argument("--render-experiment", action="store_true", help="also apply unvalidated X11/GLX source variant")
    parser.add_argument("--jobs", type=int, choices=(1, 2), default=1)
    parser.add_argument("--dependency-cache", type=Path, help="external cache of completed dependency install prefix")
    parser.add_argument("--ccache", action="store_true", help="use ccache compiler launchers")
    parser.add_argument("--plan", action="store_true", help="print commands only; never execute")
    args = parser.parse_args()
    if args.plan:
        print(json.dumps({"commands": plan(args.source.resolve(), args.jobs, ccache=args.ccache), "build_executed": False,
                          "printer_ready": False, "render_experiment": args.render_experiment,
                          "requires": "isolated external builder; see builder README"}, indent=2))
        return 0
    build(args.source.resolve(), args.output.absolute(), args.confirm_isolated_builder,
          args.render_experiment, args.jobs, args.dependency_cache, args.ccache)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
