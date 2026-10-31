"""Compile tiny synthetic archives, never the engine or its dependencies."""
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
GROUP = "$<LINK_GROUP:RESCAN,libslic3r_gui,libslic3r,libnest2d>"


@unittest.skipUnless(shutil.which("cmake") and shutil.which("c++"), "CMake/C++ fixture tools unavailable")
class CMakeLinkageTests(unittest.TestCase):
    def fixture(self, root, broken=False, missing_found=False):
        def put(name, text):
            path = root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text)

        put("CMakeLists.txt", """cmake_minimum_required(VERSION 3.24)
project(LinkCycleRegression LANGUAGES CXX)
enable_testing()
add_subdirectory(src)
add_subdirectory(tests)
""")
        put("src/CMakeLists.txt", """set(wxWidgets_FOUND TRUE)
set(wxWidgets_INCLUDE_DIRS "${CMAKE_CURRENT_SOURCE_DIR}/wx")
set(wxWidgets_DEFINITIONS WX_FIXTURE=1)
set(wxWidgets_USE_FILE "${CMAKE_ROOT}/Modules/UsewxWidgets.cmake")
include(${wxWidgets_USE_FILE})
add_library(external_dep STATIC external.cpp)
add_library(libnest2d STATIC nest.cpp nest_tail.cpp)
add_library(libslic3r STATIC core.cpp)
add_library(libslic3r_gui STATIC gui.cpp)
# Match the pinned upstream graph, including the reciprocal core/nest links.
target_link_libraries(libnest2d PUBLIC external_dep libslic3r)
target_link_libraries(libslic3r PUBLIC libnest2d)
target_link_libraries(libslic3r_gui PUBLIC libslic3r)
""")
        put("src/wx/fixture.h", "#define WX_HEADER_PRESENT 1\n")
        put("src/external.cpp", "int external_value() { return 7; }\n")
        put("src/nest.cpp", "int core(); int nest() { return core(); }\n")
        put("src/core.cpp", "int gui(); int core() { return gui(); }\n")
        put("src/gui.cpp", "int nest_tail(); int gui() { return nest_tail(); }\n")
        put("src/nest_tail.cpp", "int external_value(); int nest_tail() { return external_value(); }\n")
        put("tests/main.cpp", """#include <fixture.h>
#if !WX_FIXTURE || !WX_HEADER_PRESENT
#error wx compile usage not propagated
#endif
int nest();
int main() { return nest() == 7 ? 0 : 1; }
""")
        patch = (ROOT / "slicer/engine/patches/0009-linux-test-link-dependencies.patch").read_text()
        # Execute the actual added CMake code, not a parallel copy of the fix.
        block = "\n".join(line[1:] for line in patch.splitlines()
                          if line.startswith("+") and not line.startswith("+++"))
        if missing_found:
            # Reproduce the previous patch: UsewxWidgets sees an unset FOUND
            # in this sibling directory and silently skips includes/flags.
            start = block.index("    get_directory_property(wxWidgets_FOUND")
            end = block.index("    get_directory_property(wxWidgets_INCLUDE_DIRS")
            block = block[:start] + block[end:]
        if broken:
            block = block.replace(GROUP, "$<LINK_GROUP:RESCAN,libslic3r_gui,libslic3r>")
        suites = ("libnest2d", "libslic3r", "slic3rutils", "fff_print", "sla_print",
                  "fila_manager", "filament_group", "cpp17")
        tests = "add_library(test_common INTERFACE)\n" + block + "\n"
        for suite in suites:
            tests += f"add_subdirectory({suite})\n"
            put(f"tests/{suite}/CMakeLists.txt", f"""add_executable({suite}_tests ../main.cpp)
target_link_libraries({suite}_tests test_common libnest2d)
add_test(NAME {suite} COMMAND {suite}_tests)
""")
        put("tests/CMakeLists.txt", tests)

    def run_tool(self, *args, success=True):
        result = subprocess.run(args, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        if success:
            self.assertEqual(result.returncode, 0, result.stdout)
        else:
            self.assertNotEqual(result.returncode, 0, result.stdout)
        return result.stdout

    def test_old_group_reproduces_upstream_cycle(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            self.fixture(root, broken=True)
            output = self.run_tool("cmake", "-S", str(root), "-B", str(root / "build"), success=False)
            self.assertIn("strongly connected component (cycle)", output)
            self.assertIn("libnest2d", output)

    def test_missing_found_reproduces_silent_wx_skip(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            self.fixture(root, missing_found=True)
            build = root / "build"
            output = self.run_tool("cmake", "-S", str(root), "-B", str(build))
            self.assertIn("wxWidgets requested but not found", output)
            output = self.run_tool("cmake", "--build", str(build), success=False)
            self.assertIn("fixture.h", output)

    def test_complete_group_configures_links_and_runs_all_suites(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            self.fixture(root)
            build = root / "build"
            self.run_tool("cmake", "-S", str(root), "-B", str(build))
            self.run_tool("cmake", "--build", str(build), "--parallel", "2")
            output = self.run_tool("ctest", "--test-dir", str(build), "--output-on-failure", "--no-tests=error")
            self.assertIn("100% tests passed, 0 tests failed out of 8", output)


if __name__ == "__main__":
    unittest.main()
