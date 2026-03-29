# Buckyball Conductor Im2col E2E Promote V2

Use this promote when you want `buckyball-conductor` to run a fully automated end-to-end im2col workflow with strict debug/optimize separation, researcher-assisted path selection, and contract outputs.

## Copy/Paste Prompt

```text
你是 buckyball-conductor。请以全自动串联模式完成 im2col 的端到端流程。

一、总目标

新增一个全新 Ball：im2colv2。
必须与现有 im2col 实现彻底区分：源码命名、注册项、CTest 目标、ISA 工件全部独立，不得复用现有 im2col 命名或测试目标。
默认自动串联执行 Author -> Registrar -> CTest -> Runtime -> DebugOptimize，除非遇到硬阻塞。

二、im2col 算子语义与新架构要求

支持 veclane×veclane tile 的卷积 lowering。
输入为 feature map tile（128-bit word），支持 arbitrary kernel/stride/padding/dilation。
输出为 im2col 矩阵 tile（veclane×veclane），读写比 1:1。
iter 控制多 tile 执行。
FSM 至少包含并保持语义完整：
idle -> sRead -> sIm2col -> sWrite -> complete -> idle
允许在不破坏上述必要阶段语义的前提下增加流水级或 FIFO 提升吞吐。
sRead 负责流水发起读取并在 resp 到达时处理数据。
sWrite 负责统一写回结果。
可参考 Eyeriss dataflow 思想与 Gemmini im2col 风格，但禁止直接复制代码；必须完全适配本项目 veclane tile、Blink IO、FSM 规范。

三、Yosys 调用与报告读取新规范

当通过 bbdev yosys 指定 top 为 Ball 名称时，top 首字母必须大写。
示例：im2colBall -> Im2colBall。
优化阶段必须基于新版报告进行分析与结论：
hierarchy_report：层级热点与模块归属
area_report：芯片面积与 sequential 占比
timing_report：Startpoint / Endpoint / Path Delay / Slack
优化结论必须明确给出面积与时序改进依据，不允许空泛描述。
Runtime 严格判定以仿真目录 `stdout.log` 为准（显式 PASS/FAIL 行）。
日志主格式为 bdb.ndjson，兼容回退 bdb.log，作为补充 trace 证据。
Runtime 结束后使用 find_latest_bdb_log 与 summarize_bdb_log，并结合同目录 stdout.log 输出 strict_pass / heuristic_pass / fail 与证据。

四、严格的 Debug 与 Optimize 职能分离（强制）

只要 Runtime 任意 step 报错，或结果不是 strict_pass（包括 heuristic_pass 和 fail），进入 DebugOptimize 的 debug 模式。
debug 模式禁止运行任何 Yosys/OpenSTA 综合工具。
debug 模式只能基于 bdb.ndjson（或回退 bdb.log）、stdout.log、disasm.log 做问题定位与修复。
只有当当前流程中至少出现过一次 strict_pass，才允许进入 DebugOptimize 的 optimize 模式。
optimize 模式必须运行综合工具并依据报告执行面积/时序优化。
若 DebugOptimize 有代码改动，必须由 Runtime agent 重新执行完整链路 Step1a -> Step1b -> Step2 -> Step3，禁止跳过 Step2。
进入 optimize 循环后，必须按每轮顺序执行：
1) 完成一轮优化代码改动；
2) 先调用 Runtime 完整链路确认优化后无功能错误；
3) 仅当该轮再次得到 strict_pass，才允许调用 Yosys/OpenSTA 评估该轮面积/时序收益；
4) 若该轮不是 strict_pass，则回到 debug-only，不得运行该轮综合评估。
5) 若该轮最差路径时序裕度（worst-path slack）< 0，必须立即转入 debug 进行时序修复；修复后重新走 Runtime 全链路并再次评估，直到 slack > 0 才可视为时序安全。
6) 在 worst-path slack <= 0 时，禁止宣称 optimize 收敛完成。
7) optimize 结束前必须同时满足：最后一轮 Runtime 仍为 strict_pass，且 final_worst_path_slack > 0、timing_safe=true。

五、执行流程

先执行 requirement clarification，输出精简 Requirement Plan：
operator_name, matrix_shape, data_type, isa_policy, test_vector_policy, runtime_policy, semantic_oracle_strategy, hardware_activation_evidence, assumptions
在 requirement clarification 后自动检测技术路径是否未明确（如 dataflow/control/memory layout/bank mapping 为 TBD、你来定、或缺失）：
1) 立即调用 Researcher 子 Agent 做互联网研究，产出 3-5 条候选技术路径（含优缺点、关键优化、论文引用）。
2) 使用 vscode/askQuestions 展示完备选择页面（每条路径含关键特征、与现有接口框架兼容性、优缺点），支持单选/多选+自定义。
3) 用户选择完成后，再次调用 Researcher 深挖所选路径的实现细节、代码模式、伪代码和优化要点。
4) 生成 Final Plan Architecture 并打印后传给 Author，字段包括：
	operator_name, matrix_shape, data_type, isa_policy, test_vector_policy, runtime_policy, semantic_oracle_strategy, hardware_activation_evidence, assumptions,
	chosen_tech_paths, architecture_overview, pros_cons_summary, paper_references, detailed_implementation_guidance,
	oracle_input_generation, oracle_comparison_rule, special_encoding_plan。
若 questionnaire 已完全明确技术路径，则跳过研究步骤。
Researcher 为只读 Agent，禁止修改代码或文件。
Author 阶段：生成并校验 BALL_HANDOFF_V1，必须满足 contracts.meta.json required 字段。
Registrar 阶段：仅更新 mapping/generator/decode 三平面，输出 BALL_REGISTRATION_RESULT_V1。
Registrar 阶段后必须执行注册检查并确认：mapping_applied=true、generator_applied=true、decode_applied=true、errors 为空；未通过禁止进入 CTest。
CTest 阶段：仅创建与注册工件，不执行仿真；输出 runtime metadata：test_target, binary_name, config。
CTest 阶段后必须执行注册检查并确认：
- CTest target 已注册到对应组 CMakeLists；
- 目标已加入 buckyball-CTest-build 依赖；
- ISA include 已登记到 isa.h；
- runtime metadata 自洽（test_target/binary_name/config 对应同一测试）。
CTest 必须输出语义有效性检查并确认：
- self_fulfilling_oracle=false；
- expected 由独立 oracle/golden 生成，不得由 input 或 DUT 输出直接拷贝；
- 至少一个非平凡激活用例能证明硬件效果，若受 ISA/special 编码限制则必须输出 blocked 原因与所需编码扩展。
若 CTest 注册检查未通过，禁止进入 Runtime。
若 CTest 语义有效性检查未通过，禁止进入 Runtime。
禁止跳过 Registrar 直接进入 CTest 或 Runtime。
Runtime 阶段严格按顺序执行：
Step1a run_bbdev_test_compile(mode=apply, test_target=...)
Step1b run_bbdev_workload_build(mode=apply)
Step2 run_bbdev_verilog(mode=apply, config=sims.verilator.BuckyballToyVerilatorConfig)
Step3 run_bbdev_verilator(mode=apply, run_args=--jobs 16 --binary ... --config sims.verilator.BuckyballToyVerilatorConfig --batch)
Runtime 后执行日志定位与总结，输出分类与证据。
非 strict_pass 进入 debug-only 循环；出现 strict_pass 后至少进入一轮 post-pass optimize 循环。
仅遇到 hard blocker 才停止，并返回 blocker 原因与最小下一步输入；否则持续迭代直到无进一步优化机会或达到目标。

六、脏目录与未提交修改策略（继续运行）

将“未提交文件修改”与“脏目录”相关告警视为非阻塞告警，不中断流程，记录 warning 后继续执行。
禁止为清理脏目录而执行任何破坏性 git 操作。
禁止回滚或覆盖用户已有修改。
仅当出现真正硬阻塞（例如关键工具不可用、必要输入缺失、契约无法满足）才停止。

七、最终输出

BALL_HANDOFF_V1
BALL_REGISTRATION_RESULT_V1
Registrar 注册检查结论（pass/fail + evidence）
CTest 注册检查结论（pass/fail + evidence）
CTest 语义有效性检查结论（self_fulfilling_oracle + evidence）
最后一次 Runtime 结论（含 strict_pass / heuristic_pass / fail 与证据）
DEBUG_OPTIMIZE_RESULT_V1（必须包含 baseline_snapshot/post_snapshot/comparison_table/validate_gate/perf/optimization_rounds/optimization_summary）
其中 optimization_rounds 每轮必须包含：round, runtime_revalidated_strict_pass, worst_path_slack, timing_safe, area_delta, timing_delta, cycle_delta, notes。
其中 optimization_summary 必须包含：total_area_delta, total_timing_delta, total_cycle_delta, rounds_completed, final_worst_path_slack, timing_safe。
next_action 必须与门禁一致：若本轮或最终 worst_path_slack < 0，则 next_action 只能为 rerun_runtime_full_chain（进入时序修复循环）。
并追加每一轮优化收益汇总（每轮面积下降、开销下降、延时下降/Slack 改善，以及总计改善）
```

## Notes

- This is a conductor-level orchestration prompt, not a runtime-only prompt.
- Keep stage ownership boundaries strict: CTest prepares artifacts only, Runtime executes Step1a/1b/2/3, DebugOptimize does not run Yosys in debug mode.
- Researcher agent is read-only and used only for internet research / path analysis.
- Preserve dirty worktree safety: no destructive git cleanup actions.
