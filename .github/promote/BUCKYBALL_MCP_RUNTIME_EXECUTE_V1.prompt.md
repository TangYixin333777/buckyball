# Buckyball MCP Runtime Execute Promote V1

Use this promote when you want `buckyball-test-runtime` to execute bbdev runtime flow via MCP tools in apply mode.

## Copy/Paste Prompt

```text
使用 buckyball-test-runtime 执行 MCP runtime 验证（apply 模式）。
要求如下：
1) 优先通过 buckyball-mcp 工具调用，不要运行 python 测试脚本。
2) Step 1a（官方前置）: 执行 run_bbdev_test_compile(mode=apply)，参数：
   - test_target: <TEST_TARGET>
   - 前置说明：清理构建目录由用户在流程开始前手动完成，agent 不执行删除命令
3) Step 1b: 执行 run_bbdev_workload_build(mode=apply)。
   - 该步骤只做软件/workload 构建，不检查 VTestHarness。
4) Step 2: 执行 run_bbdev_verilog(mode=apply)，参数：
   - config: sims.verilator.BuckyballToyVerilatorConfig
   - 仅在这一步完成后检查 VTestHarness 是否存在。
5) Step 3: 执行 run_bbdev_verilator(mode=apply)，参数：
   - run_args: --jobs 16 --binary <BINARY_NAME> --config sims.verilator.BuckyballToyVerilatorConfig --batch
6) 然后执行 find_latest_bdb_log。
7) 最后执行 summarize_bdb_log。
8) 输出必须包含：
   - 每个工具调用的 OK/ERROR
   - return_code / command / warmup 结果
   - latest log_dir 下 stdout.log 的 PASS/FAIL 证据行（strict 判定依据）
   - latest bdb.ndjson 路径（若不存在则回退 bdb.log）
   - strict_pass / heuristic_pass / fail 结论与证据
如果某一步失败，停止后续步骤并给出最小修复建议。
```

## Variable

- `<BINARY_NAME>`: target workload binary name, for example `ctest_trace_test_singlecore-baremetal`.
- `<TEST_TARGET>`: software compile target, for example `ctest_relu_test`.

## Expected Tool Order

1. `run_bbdev_test_compile` (`mode=apply`)
2. `run_bbdev_workload_build` (`mode=apply`)
3. `run_bbdev_verilog` (`mode=apply`)
4. `run_bbdev_verilator` (`mode=apply`)
5. `find_latest_bdb_log`
6. `summarize_bdb_log`

## Notes

- MCP server already performs one-time warmup: `nix develop -c true` before runtime commands.
- Runtime tools default to `use_nix=true` unless explicitly overridden.
