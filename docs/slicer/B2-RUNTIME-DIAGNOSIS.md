# B2 runtime diagnosis and candidate corrections

## Latest verified run: 41348912185

Run [41348912185](https://github.com/fabriziopixel/solidcraft-slicer-builder/actions/runs/41348912185) completed **failure**, with `compiled=true`, `tests_passed=false`: six of eight suites still failed. Its original CTest output survives in `candidate/build.log`; the diagnostic CTest inventory overwrote `Testing/Temporary/LastTest.log` with an empty session. The collector now snapshots both original `LastTest.log` and `LastTestsFailed.log` into `crash-diagnostics/` before any further CTest invocation. A synthetic regression explicitly reproduces inventory truncation and verifies byte-for-byte preservation and unchanged failed gate.

Observed progress, not a passed gate:

- Both new NFP regression cases passed (zero-area rejection and omitted/supplied callback). Nesting completed without SIGSEGV or `bad_function_call`, but eight original cases still failed, including bin-count and placement properties.
- Config accessor and fill factory no longer crashed. Further configuration/validation and fill geometry failures remain.
- Two crashes remain: placeholder scripting and skirt height. Release GDB traces identify test functions, not precise source lines. Pinned source review additionally establishes unchecked null typed options: placeholder setup requests `first_layer_height`/`first_layer_speed`; skirt reads `support_material_speed` after slicing.
- Candidate **0014 is diagnostic/test-only**: five explicit `REQUIRE(... != nullptr)` preconditions. It deliberately keeps the obsolete names and every original calculation/assertion; incompatible schema must fail clearly, not be renamed to a physically different setting. It is not a migration or a fix for these failing scenarios. No runtime code changes in this follow-up.
- Shared FFF fixtures still report that objects do not fit the bed. Hull/geometry, SLA intersections and filament capacity/score failures remain unresolved. No test or tolerance is removed or softened.

Evidence downloaded to `/root/solidcraft-review/ci-41348912185/`. Source for the additional placeholder test was independently fetched from the pinned public revision and its SHA256 matched the manifest. Patch applicability was verified against the previously reviewed patched source copy. Local checks: **30 kit tests and 8 synthetic diagnostic tests passed**. The three CMake fixture tests were **skipped locally** because fixture tools were unavailable; they remain required on the hosted runner. These are not engine compilation/runtime validation. Production and engine B3/lock remain unchanged; B2 is open.

## Latest completed diagnostic evidence: 41340831232

Run [41340831232](https://github.com/fabriziopixel/solidcraft-slicer-builder/actions/runs/41340831232) completed with failure after about 81 minutes. Application/tests compiled, dependency cache was reused, and the same six CTest suites failed. All three bounded GDB reruns completed without timeout. `debugger_exit_code=0` means GDB finished, **not** that its inferior passed: each backtrace records SIGSEGV.

- Nesting: `rightmostTopVertex → calcnfp → _trypack → packItems → nest`, while running the empty-item case. Pinned `nester.hpp` dereferences the result of `max_element` without an empty-range check.
- Config: crash in the accessor test immediately after the obsolete `gcode_comments` option is requested.
- Fill: crash in `Fill: Pattern Path Length`, consistent with the previously reviewed null-returning string factory.

The latter two Release traces identify test functions, not source instructions; pointer/root-cause identification additionally relies on the pinned source review. Neither patch 0011 nor the following candidates was in that completed run.

## Candidate corrections for the next controlled attempt

### 0012 — generic configuration tests, not a schema/runtime change

The test intent is typed access, serialization, validation and rejection of invalid values. Substitutions use real current fields of matching types, not superficially similar names:

| Old test field | Current test field | Reviewed type |
|---|---|---|
| `gcode_comments`, `support_material` | `enable_support` | bool, default false |
| `bed_temperature` | `hot_plate_temp` | non-nullable integer vector |
| `perimeter_speed` | `max_bridge_length` | scalar float, not a speed vector |
| `end_gcode` | `machine_end_gcode` | string |
| `perimeter_extrusion_width`, `first_layer_extrusion_width` | `spiral_mode_max_xy_smoothing` | float-or-percent, min 0 / max 1000 |
| `perimeters` | `wall_loops` | integer, min 0 |

This preserves generic **type** coverage; it is not evidence of equivalence between the physical settings. Invalid numeric tests additionally require the error map to name the field being tested. Five typed-pointer preconditions fail as assertions instead of dereferencing null. The unchanged-value test seeds 60.0 explicitly before malformed input, retaining the original 60.0 expectation rather than relying on a different option's default. The one default assertion changes from layer height 0.3 to **0.2**, the actual pinned schema default; no tolerance changes. No scenario, disabled block, invalid-input check or serialization test is removed.

### 0013 — runtime NFP safety candidate, not merely a test adaptation

The public `trypack` entry rejects `item.area() <= 0` with an unsuccessful `PackResult` before either the normal or wipe-tower path reaches a reference vertex. Empty/default, single-point and collinear contours have zero area; no fictitious vertex or successful placement is manufactured. Three `progressFunc` calls now check the optional function before invoking it, retaining supplied callbacks. Source review shows the callback defaults empty, so unconditional calls can throw `bad_function_call`; the previous exception itself has no throw-site backtrace.

Two new real engine test cases exercise direct rejection (including both wipe-tower flag states) and omitted/supplied callbacks after a valid packed item. All original nesting cases and their bin expectations remain. Rejection can expose a separate historical UNSET-vs-UNFIT/bin-count disagreement in the original nesting tests; those assertions are deliberately not changed. This is **not** a claim to fix all nesting behavior, invalid fixed/preloaded contours, or the rectangle-arrangement result.

### Verification and remaining gates

Verified 52 pinned source hashes and applied all ten compatibility/runtime patches in a separate source copy. Local checks: 29 kit tests, seven diagnostic-helper tests, three synthetic CMake regressions; these do **not** validate engine C++ compilation or runtime. The next attempt includes 0011–0013 and keeps all eight CTest suites and their gates. Further failures are expected to remain possible, particularly bed placement, hull results, SLA intersections and filament-group constraints. No new engine image, lock update, production deployment or printer connection is authorized by these candidates.

## Earlier evidence: 41310393746

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
