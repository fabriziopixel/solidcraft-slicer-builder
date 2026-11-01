"""Bounded crash backtraces on the isolated builder; never changes test gates."""
import argparse
import json
import os
from pathlib import Path
import re
import resource
import shutil
import signal
import subprocess

from .driver import PRODUCTION_MARKER


def crash_tests(log):
    """Select only suites with an observed fatal signal, not assertion failures."""
    sections = re.split(r"(?m)^\d+/\d+ Testing: ", log)[1:]
    return {section.splitlines()[0].strip() for section in sections
            if re.search(r"SIG(?:SEGV|ABRT|BUS|ILL|FPE) -", section)}


def checked_test(test, build):
    command = test.get("command", [])
    if not command or not Path(command[0]).is_absolute():
        raise ValueError("expected absolute test executable")
    executable = Path(command[0]).resolve(strict=True)
    if not executable.is_relative_to(build):
        raise ValueError("test executable outside build")
    properties = {p["name"]: p["value"] for p in test.get("properties", [])}
    directory = Path(properties.get("WORKING_DIRECTORY", build)).resolve(strict=True)
    if not directory.is_relative_to(build):
        raise ValueError("test directory outside build")
    return [str(executable), *command[1:]], directory


def disable_core_dumps():
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))


def diagnose(output, confirmed=False, timeout=120):
    if not confirmed or PRODUCTION_MARKER.exists():
        raise ValueError("confirmed isolated builder required; CAD host forbidden")
    if not 1 <= timeout <= 120:
        raise ValueError("diagnostic timeout must be 1..120 seconds")
    output = output.resolve(strict=True)
    build = (output / "build").resolve(strict=True)
    report = json.loads((output / "build-report.json").read_text())
    if not report.get("compiled") or report.get("tests_passed") or report.get("state") != "failed":
        raise ValueError("requires a compiled candidate with failed CTest")
    destination = output / "crash-diagnostics"
    destination.mkdir(mode=0o700)  # Never overwrite an earlier diagnosis.
    summary = {"diagnostic_only": True, "printer_ready": False, "production_approved": False,
               "runs": [], "limitations": "Release backtraces may lack line numbers; reruns may differ."}
    # No CI credentials, debugger init scripts, network symbol server or core dumps.
    env = {key: value for key, value in os.environ.items()
           if key in {"PATH", "HOME", "LANG", "LC_ALL", "TMPDIR"}}
    env.update({"DEBUGINFOD_URLS": "", "GIT_CONFIG_GLOBAL": "/dev/null"})
    try:
        names = crash_tests((build / "Testing/Temporary/LastTest.log").read_text())
        gdb = shutil.which("gdb")
        if not gdb:
            summary["unavailable"] = "gdb not installed; no crash rerun"
            return summary
        listing = subprocess.run(["ctest", "--test-dir", str(build), "--show-only=json-v1"],
                                 env=env, check=True, capture_output=True, text=True, timeout=30)
        tests = json.loads(listing.stdout)["tests"]
        selected = [test for test in tests if test["name"] in names]
        if {test["name"] for test in selected} != names or len(selected) > 8:
            raise ValueError("crashed suite selection mismatch or exceeds eight-suite bound")
        for index, test in enumerate(selected):
            command, directory = checked_test(test, build)
            filename = f"crash-{index + 1}.log"
            argv = [gdb, "-nx", "-nh", "--batch", "-iex", "set auto-load off",
                    "-iex", "set debuginfod enabled off", "-ex", "set pagination off",
                    "-ex", "run", "-ex", "thread apply all bt", "--args", *command]
            entry = {"suite": test["name"], "log": filename, "timeout": False}
            with (destination / filename).open("wb") as log:
                process = subprocess.Popen(argv, cwd=directory, env=env, stdout=log,
                                           stderr=subprocess.STDOUT, start_new_session=True,
                                           preexec_fn=disable_core_dumps)
                try:
                    process.wait(timeout=timeout)
                except subprocess.TimeoutExpired:
                    entry["timeout"] = True
                finally:
                    # Kill descendants too, even when the debugger has already exited.
                    try:
                        os.killpg(process.pid, signal.SIGKILL)
                    except ProcessLookupError:
                        pass
                    process.wait()
            entry["debugger_exit_code"] = process.returncode
            summary["runs"].append(entry)
        return summary
    finally:
        (destination / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--confirm-isolated-builder", action="store_true")
    args = parser.parse_args()
    diagnose(args.output, args.confirm_isolated_builder)


if __name__ == "__main__":
    main()
