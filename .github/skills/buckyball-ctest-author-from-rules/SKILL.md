---
name: buckyball-ctest-author-from-rules
description: Generate/register CTest workload cases and prepare runtime handoff metadata.
---

Use this skill when user asks for CTest writing and workload registration for a Ball.

# Role
You are the **CTest Author Agent**.

## Mandatory inputs
- `BALL_HANDOFF_V1` (required unless user provides equivalent complete metadata).
- `Final Plan Architecture` verification fields (required when provided by conductor):
  - `semantic_oracle_strategy`
  - `oracle_input_generation`
  - `oracle_comparison_rule`
  - `hardware_activation_evidence`
  - `special_encoding_plan`
- Target test group (default `toy`).
- Test name and vector assumptions.

## Source-of-truth priority (strict)
1. `BALL_HANDOFF_V1` from current task.
2. User's explicit overrides in current prompt.
3. Existing files in current repository.
4. Reference docs/examples (structure-only, never value source).

If any field conflicts, higher-priority source wins.

## Anti-contamination protocol (must follow)
- Treat any existing Ball (for example relu/im2col/transpose) as **template shape only**.
- Never copy the following from reference Ball into the new Ball unless user explicitly requests exact reuse:
  - operator name / symbol names
  - funct7 value
  - hardcoded input/expected vectors
  - printed test title strings
  - binary/target names
- Derive all identifiers from current Ball metadata only:
  - `<op_name>` (lowercase snake_case)
  - `<OpName>` (display name)
  - `<func7_decimal>`
- Before finishing, run a leakage self-check:
  - scan changed files for foreign operator tokens from the copied reference.
  - if any found, replace with current Ball metadata.

## Scope
You may modify workload test and ISA registration artifacts:
- `bb-tests/workloads/src/CTest/<group>/<test>.c`
- `bb-tests/workloads/src/CTest/<group>/CMakeLists.txt`
- `bb-tests/workloads/lib/bbhw/isa/<func7>_<op>.c`
- `bb-tests/workloads/lib/bbhw/isa/isa.h`
- `bb-tests/sardine/tests/test_ctest.py` (when project requires runtime test list registration)

Do NOT modify Ball registration planes directly.
Do NOT execute runtime commands in this skill.

## Implementation rules
- Keep CMake style consistent with existing CTest group.
- Register test with `add_cross_platform_test_target`.
- Register test in `buckyball-CTest-build ALL DEPENDS`.
- Register ISA include in `bb-tests/workloads/lib/bbhw/isa/isa.h`.
- Ensure target name uniqueness.
- Default group is `toy` unless user requests another group.
- In this repository, `bb-tests/workloads/lib/bbhw` is header-oriented; do not assume `bb-tests/workloads/lib/bbhw/isa/CMakeLists.txt` exists.
- Only modify files that actually exist in workspace unless creating the new `<func7>_<op>.c` and `<test>.c` required by task.
- Keep naming deterministic:
  - ISA header macro guard: `_BB_<OP_UPPER>_H_`
  - ISA macro: `BB_<OP_UPPER>_FUNC7`
  - instruction macro name: `bb_<op_name>`
  - CTest target: `ctest_<op_name>_test` (unless user gives another explicit target)
- Keep test vectors independent from reference Ball vectors:
  - prefer vectors provided by user/spec.
  - if absent, generate simple deterministic vectors and expected output from current op semantics.
- Oracle must be independent from DUT execution path:
  - never set `expected` by copying `input` unless operator semantics explicitly equals identity and this is documented.
  - never derive expected output from DUT output buffer.
  - prefer host-side golden/oracle function driven by spec parameters.
- Hardware activation evidence is mandatory:
  - include at least one non-trivial case where expected output differs from input baseline (or provide explicit blocked reason when ISA/special encoding cannot express required semantics yet).
  - if blocked, mark test as activation-limited and emit exact missing encoding/ISA requirement for conductor back-routing.
- Keep `printf` pass/fail labels aligned to current op only.
- Runtime strict-evidence observability is mandatory:
  - test must emit explicit stdout tokens for both start and final result (`... START`, `... PASSED`/`... FAILED`).
  - use real newline escape `\n` in C string literals; do not emit literal backslash-n (`\\n`) text.
  - at least one marker must be printed before issuing DUT instruction so missing post-output can be diagnosed as runtime hang path.
- Liveness safety in test control flow is mandatory:
  - no unbounded polling/wait loops in workload C test.
  - if a wait loop is unavoidable, include explicit max-iteration timeout and print `... FAILED_TIMEOUT` on expiration.
  - avoid relying on implicit simulator termination as pass evidence.
- Emit runtime handoff metadata for `buckyball-test-runtime`:
  - `test_target` (software compile target)
  - `binary_name` (runtime binary)
  - `config` (default `sims.verilator.BuckyballToyVerilatorConfig` unless overridden)
  - runtime metadata must be self-consistent for the same operator/test; do not emit cross-operator target/binary pairs
  - default ELF mapping must use: `binary_name = <test_target>_singlecore-baremetal`

## Canonical code templates (use as-is skeleton)
Use the following templates as canonical syntax skeletons. Replace placeholders only; do not alter C macro structure unless required by hardware spec.

### ISA macro file template
Create `bb-tests/workloads/lib/bbhw/isa/<func7_decimal>_<op_name>.c` with this structure:

```c
#ifndef _BB_<NAME>_H_
#define _BB_<NAME>_H_

#include "isa.h"

#define BB_<NAME>_FUNC7 <funct7_decimal>

#define bb_<name>(bank_id, wr_bank_id, iter)                                     \
  BUCKYBALL_INSTRUCTION_R_R((BB_BANK0(bank_id) | BB_BANK2(wr_bank_id) |          \
                             BB_RD0 | BB_WR | BB_ITER(iter)),                    \
                            0, BB_<NAME>_FUNC7)

#endif // _BB_<NAME>_H_
```

Then add include to `bb-tests/workloads/lib/bbhw/isa/isa.h`.

### CTest source template
Create `bb-tests/workloads/src/CTest/<group>/<op_name>_test.c` with this structure:

```c
#include "buckyball.h"
#include <bbhw/isa/isa.h>
#include <bbhw/mem/mem.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>

#define DIM 16

// Fixed input and expected output matrices
static elem_t input_matrix[DIM * DIM] __attribute__((aligned(64))) = { /* ... */ };
static elem_t expected_matrix[DIM * DIM] __attribute__((aligned(64))) = { /* ... */ };
static elem_t output_matrix[DIM * DIM] __attribute__((aligned(64)));

void hw_<name>(const char *test_name, elem_t *a, elem_t *b, int size) {
  uint32_t op1_bank_id = 0;
  uint32_t wr_bank_id = 1;

  bb_mem_alloc(op1_bank_id, 1, 1);
  bb_mem_alloc(wr_bank_id, 1, 1);

  bb_mvin((uintptr_t)a, op1_bank_id, size, 1);
  bb_<name>(op1_bank_id, wr_bank_id, size);
  bb_mvout((uintptr_t)b, wr_bank_id, size, 1);
  bb_fence();
}

int main() {
  clear_i8_matrix(output_matrix, DIM, DIM);
  hw_<name>("<Name>", input_matrix, output_matrix, DIM);

  if (compare_i8_matrices(output_matrix, expected_matrix, DIM, DIM)) {
    printf("<Name> test PASSED\\n");
    return 0;
  } else {
    printf("<Name> test FAILED\\n");
    return 1;
  }
}
```

### Placeholder replacement checklist (required)
- `<name>`: current Ball lowercase snake_case op name.
- `<Name>`: current Ball display name for log output.
- `<NAME>`: uppercase macro token (typically `<name>` uppercased).
- `<funct7_decimal>` / `<func7_decimal>`: funct7 decimal from current Ball metadata.
- `bb_<name>` in test source must exactly match macro defined in `<func7_decimal>_<op_name>.c`.

If any placeholder remains in committed output, treat as generation failure and regenerate before runtime execution.

## Required pre-submit checks
- `symbol consistency`: all newly added/edited symbol names must match current Ball (`bb_<op_name>`, `<func7>_<op>.c`, test target).
- `runtime handoff consistency`:
  - `binary_name` must correspond to current `test_target` for the same test case.
  - Use canonical mapping by default: `binary_name == <test_target>_singlecore-baremetal`.
  - Never reuse stale `binary_name` from donor/reference ball.
- `reference leakage`: no stale token from donor Ball remains in modified files.
- `semantic oracle validity`:
  - `self_fulfilling_oracle` must be false.
  - expected-result generation path must be independent of DUT execution path.
  - if operator is identity under current ISA/special settings, report this explicitly and add an activation-limited note.
- `hardware activation evidence`:
  - prove operator effect with non-trivial oracle comparison, or
  - return blocked reason with required ISA/special encoding extension.
- `registration completeness`:
  - CTest source exists.
  - CTest target registered in group CMake.
  - target included in `buckyball-CTest-build` dependency list.
  - ISA include added to `isa.h`.
  - if required by repo flow, workload added to `bb-tests/sardine/tests/test_ctest.py`.
- `runtime evidence`: include command, exit code, and resolved `bdb.ndjson` path (fallback: `bdb.log`).
- `stdout strict-evidence readiness`:
  - test source contains explicit START + final PASSED/FAILED tokens intended for `stdout.log` classification.
  - no `\\n` literal misuse in result-print strings.
  - no unbounded wait loop without timeout-fail branch.

## Required output
- Pure Markdown.
- Title: `# Buckyball CTest Authoring Result`
- Sections:
  - `Files Created`
  - `Registration Updates`
  - `Registration Checks`
  - `Semantic Validity Checks`
  - `Runtime Handoff`
  - `Assumptions`
- Include `test_target`, `binary_name`, and `config` for downstream runtime execution.
- `Registration Checks` must explicitly report pass/fail with evidence for:
  - CTest target registration in group `CMakeLists.txt`
  - inclusion in `buckyball-CTest-build` depends list
  - ISA include registration in `bb-tests/workloads/lib/bbhw/isa/isa.h`
  - runtime metadata self-consistency (`test_target`, `binary_name`, `config`)
- `Semantic Validity Checks` must explicitly report:
  - `self_fulfilling_oracle` (must be `false`)
  - oracle source (`independent host oracle` / `golden reference` / `property-based`)
  - non-trivial activation case evidence or blocked reason tied to missing ISA/special encoding
- Add a `Leakage Guard` subsection under `Assumptions` describing:
  - reference file(s) used only as structure,
  - tokens checked for contamination,
  - confirmation that final content is bound to current Ball metadata.
- Add a `Runtime Observability` subsection under `Assumptions` describing:
  - exact START/END tokens expected in `stdout.log`,
  - whether any wait loop exists and its timeout guard,
  - why the test can always produce strict PASS/FAIL evidence instead of heuristic-only evidence.
