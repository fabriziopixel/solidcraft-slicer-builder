"""Synthetic driver/packaging tests. Never compiles or claims an engine build."""
import hashlib
import json
from pathlib import Path
import subprocess
import tarfile
import tempfile
import unittest
from unittest.mock import patch

from slicer.builder import driver, package


class BuilderTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source = self.root / "upstream"
        self.source.mkdir()
        self.output = self.root / "candidate"
        for target, value in [("PRODUCTION_MARKER", self.root / "no-production")]:
            p = patch.object(driver, target, value)
            p.start()
            self.addCleanup(p.stop)
        for target, value in [("system", "Linux"), ("machine", "x86_64")]:
            p = patch.object(driver.platform, target, return_value=value)
            p.start()
            self.addCleanup(p.stop)
        p = patch.object(driver.shutil, "which", return_value="/usr/bin/tool")
        p.start()
        self.addCleanup(p.stop)

    def check(self, confirmed=True, ram=driver.MIN_RAM, disk=driver.MIN_DISK):
        return driver.preflight(self.source, self.output, confirmed, (ram, disk))

    def test_explicit_builder_confirmation_required(self):
        with self.assertRaisesRegex(ValueError, "explicit"):
            self.check(confirmed=False)

    def test_cad_host_rejected_even_with_sufficient_resources(self):
        with patch.object(driver, "PRODUCTION_MARKER", self.source):
            with self.assertRaisesRegex(ValueError, "CAD deployment"):
                self.check()

    def test_insufficient_resources_rejected(self):
        for ram, disk in [(driver.MIN_RAM - 1, driver.MIN_DISK), (driver.MIN_RAM, driver.MIN_DISK - 1)]:
            with self.subTest(ram=ram, disk=disk), self.assertRaisesRegex(ValueError, "external builder needs"):
                self.check(ram=ram, disk=disk)
        self.assertFalse(self.output.exists())

    def test_existing_output_never_overwritten(self):
        self.output.mkdir()
        with self.assertRaisesRegex(ValueError, "new directory"):
            self.check()

    def test_supported_resources_pass(self):
        self.assertEqual(self.check()["available_ram_bytes"], driver.MIN_RAM)
        self.assertFalse(self.output.exists())

    def test_plan_is_inert_and_runs_real_tests(self):
        with patch.object(driver.subprocess, "run") as run:
            commands = driver.plan(self.source)
            run.assert_not_called()
        self.assertIn("-DSLIC3R_BUILD_TESTS=ON", commands[4])
        self.assertIn("--no-tests=error", commands[-1])
        self.assertFalse(self.output.exists())

    def test_two_job_plan_keeps_dependency_superbuild_serial(self):
        commands = driver.plan(self.source, jobs=2)
        self.assertEqual(commands[3][-2:], ["--parallel", "1"])
        self.assertEqual(commands[5][3:5], ["--parallel", "2"])

    def test_main_build_collects_all_errors_but_still_requires_tests(self):
        commands = driver.plan(self.source, jobs=2)
        self.assertEqual(commands[5][-3:], ["--", "-k", "0"])
        self.assertEqual(commands[3][-2:], ["--parallel", "1"])
        self.assertEqual(commands[-1][0], "ctest")
        self.assertIn("--no-tests=error", commands[-1])

    def test_unbounded_parallelism_rejected_before_build(self):
        with self.assertRaisesRegex(ValueError, "one or two"):
            driver.build(self.source, self.output, True, jobs=8)
        self.assertFalse(self.output.exists())

    def test_ci_credentials_not_inherited_by_build(self):
        with patch.object(driver, "preflight", return_value={}), \
                patch.dict(driver.os.environ, {"GITHUB_TOKEN": "synthetic", "ACTIONS_RUNTIME_TOKEN": "synthetic"}), \
                patch.object(driver.subprocess, "run", side_effect=subprocess.CalledProcessError(1, "git")) as run:
            with self.assertRaises(subprocess.CalledProcessError):
                driver.build(self.source, self.output, True)
        env = run.call_args.kwargs["env"]
        self.assertNotIn("GITHUB_TOKEN", env)
        self.assertNotIn("ACTIONS_RUNTIME_TOKEN", env)

    def test_build_failure_saved_without_success_flags(self):
        with patch.object(driver, "preflight", return_value={}), \
                patch.object(driver.subprocess, "run", side_effect=subprocess.CalledProcessError(1, "git")):
            with self.assertRaises(subprocess.CalledProcessError):
                driver.build(self.source, self.output, True)
        report = json.loads((self.output / "build-report.json").read_text())
        self.assertEqual(report["state"], "failed")
        self.assertFalse(report["compiled"])
        self.assertFalse(report["tests_passed"])
        self.assertFalse(report["printer_ready"])

    def test_build_fix_source_hashes_and_revision_required(self):
        docs = self.root / "docs/slicer"
        docs.mkdir(parents=True)
        source = self.source / "test.cpp"
        source.write_bytes(b"reviewed source")
        manifest = {"revision": driver.REVISION, "sources": [
            {"path": "test.cpp", "sha256": hashlib.sha256(source.read_bytes()).hexdigest()}],
            "patches": [{"path": "reviewed.patch", "sha256": "synthetic"}]}
        path = docs / "b2-build-fixes.json"
        path.write_text(json.dumps(manifest))
        with patch.object(driver, "ROOT", self.root):
            self.assertEqual(driver.build_fixes(self.source), manifest["patches"])
            source.write_bytes(b"changed")
            with self.assertRaisesRegex(ValueError, "source mismatch"):
                driver.build_fixes(self.source)
            manifest["revision"] = "wrong"
            path.write_text(json.dumps(manifest))
            with self.assertRaisesRegex(ValueError, "revision mismatch"):
                driver.build_fixes(self.source)

    def test_shipped_build_fix_patch_hashes(self):
        manifest = json.loads((driver.ROOT / "docs/slicer/b2-build-fixes.json").read_text())
        for entry in manifest["patches"]:
            self.assertIn(entry["path"], package.FILES)
            self.assertEqual(hashlib.sha256((driver.ROOT / entry["path"]).read_bytes()).hexdigest(),
                             entry["sha256"])

    def test_wrong_revision_stops_before_cmake(self):
        def command(argv, **kwargs):
            return subprocess.CompletedProcess(argv, 0, stdout=b"wrong-revision\n")
        with patch.object(driver, "preflight", return_value={}), \
                patch.object(driver.subprocess, "run", side_effect=command) as run:
            with self.assertRaisesRegex(ValueError, "unexpected source revision"):
                driver.build(self.source, self.output, True)
        self.assertFalse(any(call.args[0][0] == "cmake" for call in run.call_args_list))
        self.assertEqual(json.loads((self.output / "build-report.json").read_text())["state"], "failed")


class KitTests(unittest.TestCase):
    def test_geometry_patch_preserves_assertions_and_disables_new_voronoi_repair(self):
        text = (driver.ROOT / "slicer/engine/patches/0008-geometry-raster-test-api.patch").read_text()
        removed = [line[1:] for line in text.splitlines() if line.startswith("-") and not line.startswith("---")]
        added = [line[1:] for line in text.splitlines() if line.startswith("+") and not line.startswith("+++")]
        for line in removed + added:
            self.assertNotIn("REQUIRE(", line)
            self.assertNotIn("TEST_CASE(", line)
        self.assertEqual(sum("vd.construct_voronoi(lines.begin(), lines.end(), false)" in line for line in added), 14)
        self.assertEqual(sum("vd.construct_voronoi(pts.begin(), pts.end())" in line for line in added), 2)

    def test_linux_link_patch_keeps_all_suites_and_uses_real_libraries(self):
        text = (driver.ROOT / "slicer/engine/patches/0009-linux-test-link-dependencies.patch").read_text()
        self.assertIn('"$<LINK_GROUP:RESCAN,libslic3r_gui,libslic3r>"', text)
        self.assertIn('include(${wxWidgets_USE_FILE})', text)
        self.assertNotIn("\n-add_subdirectory", text)
        self.assertNotIn("\n-add_test", text)
        self.assertIn('if(CMAKE_SYSTEM_NAME STREQUAL "Linux")', text)

    def test_allowlist_only_and_deterministic(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "public").write_text("source")
            (root / ".env").write_text("must not be included")
            with patch.object(package, "FILES", ("public",)):
                first = package.package(root, root / "first.tgz")
                second = package.package(root, root / "second.tgz")
            self.assertEqual(first, second)
            with tarfile.open(root / "first.tgz") as archive:
                self.assertEqual(archive.getnames(), ["builder-kit-manifest.json", "public"])
                manifest = json.load(archive.extractfile("builder-kit-manifest.json"))
                self.assertEqual(manifest["files"]["public"]["sha256"], hashlib.sha256(b"source").hexdigest())
                self.assertFalse(manifest["compiled"])
                self.assertFalse(manifest["printer_ready"])

    def test_symlinks_rejected_before_archive_creation(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "real").write_text("source")
            (root / "link").symlink_to(root / "real")
            with patch.object(package, "FILES", ("link",)):
                with self.assertRaisesRegex(ValueError, "unsafe kit source"):
                    package.package(root, root / "kit.tgz")
            self.assertFalse((root / "kit.tgz").exists())

    def test_existing_archive_never_overwritten(self):
        with tempfile.TemporaryDirectory() as temp:
            output = Path(temp) / "kit.tgz"
            output.write_bytes(b"existing")
            with self.assertRaisesRegex(ValueError, "overwrite"):
                package.package(Path(temp), output)
            self.assertEqual(output.read_bytes(), b"existing")


if __name__ == "__main__":
    unittest.main()
