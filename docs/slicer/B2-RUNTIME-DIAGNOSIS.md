# B2 runtime diagnosis — run 41310393746

The metadata build at commit `8e58bf4461769dbc3b9c707aaa52dd29e5d77232` compiled successfully, including the application and test executables. CTest failed six of eight suites. This confirms the earlier runtime blocker; no gate is waived.

Evidence: https://github.com/fabriziopixel/solidcraft-slicer-builder/actions/runs/41310393746 — diagnostic artifact `b2-diagnostics-metadata-41310393746`, especially `candidate/build/Testing/Temporary/LastTest.log` and `candidate/build-report.json`.

| Suite | Observations, not yet established root causes |
|---|---|
| libnest2d | Loose rectangles remain unassigned (0 groups vs 1 expected); Prusa parts throws `bad_function_call`; empty-item nesting segfaults. |
| libslic3r | Sinking-object convex hull differs; removed configuration names `perimeter_extrusion_width`, `perimeters`, `gcode_comments` cause unknown-option exceptions; config accessor test segfaults. |
| fff_print | Shared print fixture reports objects cannot fit on bed; fill-pattern test segfaults. |
| support_material_on_wipe_tower | Same shared print-fixture failure; five support tests pass. |
| sla_print | Two pad intersection assertions fail; 19 cases pass. |
| filament_group | Golden scores and capacity constraints fail, including 4 filaments assigned where maximum is 3; property failures are not merely score tolerances. |

`slic3rutils_tests` (22 cases, 336 assertions) and `fila_manager_tests` (19 cases, 71 assertions) pass. Segfaults terminate suites early, so these logs are not a full enumeration of failing individual test cases.

## Next diagnostic attempt

No engine/test compatibility patch is justified by a backtrace yet. Do not rename arbitrary configuration keys, change geometric expectations, relax score tolerances or remove tests just to get a green run.

The workflow now preserves the original full CTest result and, after failure on a compiled candidate, reruns only suites whose original log contains a fatal signal under GDB. It uses CTest's JSON command/working-directory inventory, validates paths within the build, retains original arguments, and limits each suite to 120 seconds (at most eight suites). GDB initialization/auto-load and network symbol downloading are disabled; CI credentials are not inherited, core dumps are disabled, and timeout cleanup kills the debugger process group. The CAD-host guard remains mandatory. Only backtrace text and a JSON summary are uploaded, not binaries or core files. Release backtraces may lack line numbers, and a rerun may differ from the original execution.

GDB is installed if necessary on the disposable GitHub runner only, after compilation/cache identity calculation. No dependency recipes, compiler flags, engine sources, assertions or test selection in the acceptance run change. Missing GDB, timeout or even successful diagnostic reruns cannot turn the failed build green. The extra helper has seven synthetic unit tests; these are not engine runtime validation.

The remaining crash patch decisions require the collected stack traces and review of the corresponding pinned source/callers. Metadata/rendering validation, desktop comparison, legal review, production approval and printer readiness all remain open.

## Static follow-up while diagnostic run 41340831232 compiles

A specific null dereference is established directly in the pinned sources, independently of a backtrace:

- `tests/fff_print/test_fill.cpp:30,124,434` requests `Fill::new_from_type("rectilinear")`, then dereferences the returned pointer without checking it.
- `src/libslic3r/Fill/FillBase.cpp:69–73` looks up that exact string in `ConfigOptionEnum<InfillPattern>` and returns `nullptr` for an absent entry.
- `src/libslic3r/PrintConfig.cpp:219–245` no longer contains `rectilinear` in that infill map. It maps `zig-zag` to `ipRectilinear` (distinct from `zigzag`, which maps to `ipZigZag`).
- `FillBase.cpp:40` constructs the expected `FillRectilinear` for `ipRectilinear`.

Candidate test-only patch `0011-fill-test-pattern-name.patch` uses the current `zig-zag` string in all three places and adds three `REQUIRE(filler != nullptr)` guards. It retains coverage of the string factory; it does not substitute a different filling algorithm. Every original geometric assertion, number, tolerance, section and disabled block is unchanged. Source and patch hashes are pinned in `b2-build-fixes.json`.

Verified 45 source hashes, applied the eight compatibility patches in a separate source copy, and confirmed the fill-test file matches the original byte-for-byte after reversing just the three renamed factory arguments and three new guards. These are source checks, not compilation or runtime tests. 27 kit tests and seven diagnostic tests pass locally; the new kit test checks the exact patch scope and pinned source coverage.

Run `41340831232` remains on its original commit `4f5d456900b5c44a8e6cb32da3025eaa4b90bb93`: it **does not contain patch 0011**. No extra build was launched during this review. The patch is prepared for a subsequent reviewed attempt; neither the observed crash's stack nor subsequent fill geometry results have been validated yet.

The configuration tests need more than blind key renaming. For example, old scalar `perimeter_speed` assertions do not match the current `outer_wall_speed` option, which is `coFloats`, and old float-or-percent line-width tests do not match current `initial_layer_line_width`, which is `coFloat`. Those tests must preserve meaningful type/value/invalid-input coverage; changing keys alone would be misleading. No such patch is included here. Nesting callbacks, bed-placement fixtures, hull ordering, SLA intersections and filament-group failures remain separate open investigations.
