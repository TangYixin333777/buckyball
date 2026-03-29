# Buckyball Operator Authoring Spec (Merged)

> 本文件已合并历史上的接口规范与模板规范语义。

## 1. 目标与范围

- 目标：用精确、可执行的规则约束 Ball 编写方式，降低“能跑但不鲁棒”的实现风险。
- 适用范围：`arch/src/main/scala/framework/balldomain/prototype/<ball>/...` 的 wrapper/core/config 设计。
- 非范围：注册平面（mapping/generator/decode）与 CTest 平面。

### 1.1 复杂 Ball 审计结论（已扩展）

- 本规范已按 `gemmini / vector / systolicarray / im2col / trace / quant / dequant` 复核。
- 关键修订：
  - `cmdReq.ready` 不再限定“只能 idle 状态拉高”，对多子模块路由型允许按目标消费者可用性拉高。
  - `subRobReq` 不再默认一律 tie-off；复杂 Ball（如 gemmini）可合法主动发起 sub-ROB 命令。
  - lane 默认值纪律仅强约束 `req.valid/resp.ready`，元数据字段允许“常驻赋值”或“按请求赋值”。

## 2. 强制架构约束

### 2.1 wrapper/core 分层

- 必须使用 `XxxBall.scala` + `Xxx.scala` 分层。
- wrapper 必须：
  - 读取 `ballIdMappings` 的 `inBW/outBW`。
  - 暴露 `new BlinkIO(b, inBW, outBW)`。
  - 透传 `cmdReq/cmdResp/bankRead/bankWrite/status`。
  - 明确 `subRobReq` 策略：要么 tie-off（简单 Ball），要么由内部编码器驱动（复杂 Ball）。

Hierarchy 实例化可见性约束（强制）：
- 若 wrapper 通过 `Instance[T]` + `Instantiate(new T(...))` 连接子模块：
  - 子模块类必须 `@instantiable`。
  - 子模块 IO 必须为 `@public val io = IO(...)`。
  - wrapper 应与现有范式保持一致（`@instantiable` + hierarchy imports）。
- 禁止在未满足上述约束时直接连接 `instance.io.*`，否则会触发
  - `value io is not a member of chisel3.experimental.hierarchy.Instance[...]`。

参考示例：
- `ReluBall.scala` + `Relu.scala`
- `TransposeBall.scala` + `Transpose.scala`
- `TraceBall.scala` + `Trace.scala`

示例代码（wrapper/core 透传，来自 `ReluBall.scala`）：

```scala
val ballCommonConfig = b.ballDomain.ballIdMappings.find(_.ballName == "ReluBall")
  .getOrElse(throw new IllegalArgumentException("ReluBall not found in config"))
val inBW             = ballCommonConfig.inBW
val outBW            = ballCommonConfig.outBW

@public
val io = IO(new BlinkIO(b, inBW, outBW))

val reluUnit: Instance[PipelinedRelu] = Instantiate(new PipelinedRelu(b))

reluUnit.io.cmdReq <> io.cmdReq
reluUnit.io.cmdResp <> io.cmdResp
for (i <- 0 until inBW)  { reluUnit.io.bankRead(i)  <> io.bankRead(i) }
for (i <- 0 until outBW) { reluUnit.io.bankWrite(i) <> io.bankWrite(i) }
io.status <> reluUnit.io.status
```

示例代码（复杂 wrapper，`subRobReq` 主动驱动，来自 `GemminiBall.scala`）：

```scala
val cmdArb = Module(new Arbiter(new LoopCmd(b), 2))
cmdArb.io.in(0) <> matmulUnroller.io.cmd
cmdArb.io.in(1) <> convUnroller.io.cmd
encoder.io.cmd <> cmdArb.io.out
encoder.io.subRobRow <> io.subRobReq
encoder.io.ballId      := ballCommonConfig.ballId.U
encoder.io.masterRobId := rob_id_reg
```

### 2.2 IO 与协议命名

- core IO 名称和类型必须使用：
  - `cmdReq: Flipped(Decoupled(new BallRsIssue(b)))`
  - `cmdResp: Decoupled(new BallRsComplete(b))`
  - `bankRead: Vec(inBW, Flipped(new BankRead(b)))`
  - `bankWrite: Vec(outBW, Flipped(new BankWrite(b)))`
  - `status: new BallStatus`
- 禁止使用过时或自造接口名（如 `cmd/bank_ctrl/we`）。

示例代码（core IO 定义，来自 `Transpose.scala`）：

```scala
@public
val io = IO(new Bundle {
  val cmdReq    = Flipped(Decoupled(new BallRsIssue(b)))
  val cmdResp   = Decoupled(new BallRsComplete(b))
  val bankRead  = Vec(inBW, Flipped(new BankRead(b)))
  val bankWrite = Vec(outBW, Flipped(new BankWrite(b)))
  val status    = new BallStatus
})
```

### 2.3 FSM 与握手语义

- 单 FSM core：`cmdReq.ready` 通常仅在 `idle` 拉高。
- 多子模块路由型：允许按目标消费者可用性拉高（如 `Mux(isExUnit, exCtrl.ready, ...)`），但必须保证不会接收不可执行命令。
- 在 `cmdReq.fire` 当拍锁存后续需要的字段（`rob_id/op1_bank/wr_bank/iter/...`）。
- 后续状态禁止直接依赖瞬时 `cmdReq.bits`。
- 状态推进必须以 `fire` 事件为准，不依赖理想无阻塞路径。
- 完成通过 `cmdResp.valid`，并在 `cmdResp.fire` 后回到 `idle`。
- 复杂 Ball 若使用多模块路由控制面，按第 10 节“分级约束矩阵”执行。

参考示例：
- `Relu.scala`: `idle -> sRead -> sWrite -> complete`
- `Transpose.scala`: `idle -> fill -> drain`

示例代码（命令锁存 + ready/resp 语义，来自 `Transpose.scala`）：

```scala
val rob_id_reg = RegInit(0.U(log2Up(b.frontend.rob_entries).W))
when(io.cmdReq.fire) {
  rob_id_reg := io.cmdReq.bits.rob_id
}

io.cmdReq.ready        := (state === idle)
io.cmdResp.valid       := false.B
io.cmdResp.bits.rob_id := rob_id_reg

is(idle) {
  when(io.cmdReq.fire) {
    rbank_reg := io.cmdReq.bits.cmd.op1_bank
    wbank_reg := io.cmdReq.bits.cmd.wr_bank
    iter_reg  := io.cmdReq.bits.cmd.iter
    state     := fill
  }
}
```

## 3. Bank/SRAM 精确约束

### 3.1 默认值纪律

- 所有 lane 在 FSM override 之前必须默认：
  - `req.valid := false.B`
  - `resp.ready := false.B`
- 仅对当前状态真正消费的 lane 拉高 `resp.ready`。
- 单通道实现不得对全部 lane 同时拉高 `resp.ready`。
- 元数据字段（`bank_id/rob_id/ball_id/group_id`）允许两种等价风格：
  - 常驻赋值（参考 `relu/transpose/trace/vector/systolicarray`）
  - 按请求赋值（在 `when(req.valid)` 或模块边界路由时）
- 约束目标是“请求语义正确”，而不是强制某一种元数据赋值位置。
- 复杂 Ball 出现跨模块路由时，以“最终发出请求的 lane 语义正确”为验收标准。

示例代码（lane 默认值纪律，来自 `Transpose.scala`）：

```scala
for (i <- 0 until inBW) {
  io.bankRead(i).io.req.valid     := false.B
  io.bankRead(i).io.req.bits.addr := 0.U
  io.bankRead(i).io.resp.ready    := false.B
}
for (i <- 0 until outBW) {
  io.bankWrite(i).io.req.valid      := false.B
  io.bankWrite(i).io.req.bits.addr  := 0.U
  io.bankWrite(i).io.req.bits.data  := 0.U
  io.bankWrite(i).io.req.bits.mask  := VecInit(Seq.fill(b.memDomain.bankMaskLen)(0.U(1.W)))
  io.bankWrite(i).io.req.bits.wmode := false.B
  io.bankWrite(i).io.resp.ready     := false.B
}

io.bankRead(0).io.resp.ready  := (state =/= idle)
io.bankWrite(0).io.resp.ready := (state =/= idle)
```

### 3.2 SRAM 时序

- 遵循 `SramBank`：读请求被接收后 1 拍返回 `resp.valid`。
- 读写均以 Decoupled 语义为准：`fire = valid && ready`。

### 3.3 数据布局契约（必须声明）

- 必须在 Design Notes 明确：
  - `scalar-per-address` 或
  - `packed-word`
- 实现必须与声明一致，禁止“按标量读 + 按整字写”的隐式混搭。

参考示例：
- `Relu.scala`、`Transpose.scala` 使用 packed-word 切片风格。

示例代码（packed-word 切片，来自 `Relu.scala`）：

```scala
val dataWord = io.bankRead(0).io.resp.bits.data

for (col <- 0 until InputNum) {
  val hi     = (col + 1) * inputWidth - 1
  val lo     = col * inputWidth
  val raw    = dataWord(hi, lo)
  val signed = raw.asSInt
  val relu   = Mux(signed < 0.S, 0.S(inputWidth.W), signed)
  regArray(respCounter)(col) := relu.asUInt
}
```

## 4. 鲁棒性与可扩展性（关键新增）

### 4.1 固定语义 vs 固定实现

- 固定语义可接受：例如“4x4 转置”。
- 固定实现默认不接受：例如地址长期固定 `0.U`、仅单轮可运行。

### 4.2 必须避免的反模式

- 读取了配置参数却用 `require` 把行为完全锁死，且无扩展路径。
- 忽略 `iter`，导致多 tile 工作负载下只处理首包。
- 地址生成与命令字段脱钩（读写地址硬编码）。

### 4.3 推荐实现策略

- 用 tile 语义定义算子功能边界。
- 用 `iter/stride/counter` 驱动地址与轮次推进。
- 支持 backpressure 下的稳定推进与完成。

示例代码（`iter -> stride -> round` 推进，来自 `Transpose.scala`）：

```scala
val iterVal   = io.cmdReq.bits.cmd.iter
val strideVal = iterVal >> log2Ceil(InputNum)
stride        := Mux(strideVal === 0.U, 1.U, strideVal)
round         := 0.U

def readAddr(row: UInt, r: UInt): UInt = row * stride + r

io.bankRead(0).io.req.valid     := (fillIdx < InputNum.U)
io.bankRead(0).io.req.bits.addr := readAddr(fillIdx, round)

when(round === stride - 1.U) {
  io.cmdResp.valid := true.B
}.otherwise {
  round   := round + 1.U
  fillIdx := 0.U
  state   := fill
}
```

### 4.4 特例管理

- 若确需教学或 benchmark-only 固定实现：
  - 必须在 Design Notes 增加 `Robustness Exception`。
  - 说明限制范围与迁移计划。
  - 标注“不可作为标准 Ball 模板复用”。

## 5. 参数化与集成来源

- `inBW/outBW` 由 `ballIdMappings` 决定，并传播到 BBus/MemRouter 聚合宽度。
- `bankNum/bankEntries/bankWidth/bankMaskLen` 由 mem config 决定。
- 新 Ball 接入注册时需修改 mapping/generator/decode 三平面（不在本文执行）。

## 6. 从现有参考 Ball 提炼的架构样例

- `relu/`：单通道向量化切片 + 分阶段 FSM 的基础模板。

```scala
val idle :: sRead :: sWrite :: complete :: Nil = Enum(4)
io.cmdReq.ready := state === idle
is(sRead) {
  io.bankRead(0).io.req.valid := (readCounter < InputNum.U)
}
```

- `transpose/`：`iter->stride` 多轮 fill/drain 的鲁棒地址推进模板。

```scala
val strideVal = iterVal >> log2Ceil(InputNum)
stride        := Mux(strideVal === 0.U, 1.U, strideVal)
io.bankWrite(0).io.req.bits.addr := round * InputNum.U + drainIdx
```

- `im2col/`：多模块协作（行缓冲/流式写出）示例。

```scala
val lineBuf: Instance[LineBufferManager] = Instantiate(new LineBufferManager(b))
val writer:  Instance[StreamWriter]      = Instantiate(new StreamWriter(b))
writer.io.elemIn.bits := lineBuf.io.elemData
```

- `vector/`：复杂算子分解（load/ex/store/ctrl/thread/warp）示例。

```scala
val vecUnit: Instance[VecUnit] = Instantiate(new VecUnit(b))
vecUnit.io.cmdReq <> io.cmdReq
vecUnit.io.cmdResp <> io.cmdResp
```

- `vector/` 与 `systolicarray/`：控制/加载/执行/存储解耦流水示例。

```scala
VecLoadUnit.io.ctrl_ld_i <> VecCtrlUnit.io.ctrl_ld_o
VecEX.io.ctrl_ex_i <> VecCtrlUnit.io.ctrl_ex_o
VecStoreUnit.io.ctrl_st_i <> VecCtrlUnit.io.ctrl_st_o
VecCtrlUnit.io.cmdResp_i <> VecStoreUnit.io.cmdResp_o
```

- `quant/` 与 `dequant/`：成对算子和配置驱动写法示例。

```scala
val quantUnit: Instance[Quant] = Instantiate(new Quant(b))
val dequantUnit: Instance[Dequant] = Instantiate(new Dequant(b))
```

- `trace/`：带可观测性与调试接口（DPI）示例。

```scala
val traceUnit: Instance[Trace] = Instantiate(new Trace(b))
traceUnit.io.cmdReq <> io.cmdReq
traceUnit.io.cmdResp <> io.cmdResp
```

- `trace/`：DPI 驱动外部 bank 回读/回写（调试型路径）。

```scala
bdGetReadAddr.io.enable := true.B
io.bankRead(0).io.req.valid     := true.B
io.bankRead(0).io.req.bits.addr := row
bdPutReadData.io.enable         := true.B
```

- `gemmini/` 与 `systolicarray/`：大算子多文件组织与控制路径示例。

```scala
val exCtrl:         Instance[GemminiExCtrl]      = Instantiate(new GemminiExCtrl(b))
val matmulUnroller: Instance[LoopMatmulUnroller] = Instantiate(new LoopMatmulUnroller(b))
val convUnroller:   Instance[LoopConvUnroller]   = Instantiate(new LoopConvUnroller(b))

val systolicArrayUnit: Instance[SystolicArrayUnit] = Instantiate(new SystolicArrayUnit(b))
systolicArrayUnit.io.cmdReq <> io.cmdReq
```

- `gemmini/`：命令分类路由 + 即时 config 响应 + loop trigger 组合示例。

```scala
val isExUnit = isConfig || isPreload || isComputePre || isComputeAcc || isFlush
exCtrl.io.cmdReq.valid := io.cmdReq.valid && isExUnit
io.cmdReq.ready := Mux(isExUnit, exCtrl.io.cmdReq.ready, true.B)

when(io.cmdReq.fire && isLoopWsConfig) {
  configRespValid := true.B
}
```

## 7. 交付前最小自检（必须通过）

- `cmdReq.fire` 后字段均由寄存器驱动。
- lane 默认值和消费 ready 纪律满足。
- 数据布局声明与实现一致。
- 非 benchmark-only 路径下无地址硬编码。
- `iter > base_tile` 时可推进多轮，不提前完成。
- `cmdResp` 仅在真实完成后拉高。

## 8. 从 Ball Skill 同步的可复用内容

### 8.1 需求确认清单（实现前）

- 计算语义：算子要完成什么运算。
- 通道规模：`inBW/outBW` 取值。
- 解码需求：是否需要 `op2`。
- 运行语义：`iter` 表示什么（元素数、tile 数、轮次）。

### 8.2 最小模板库（可直接复制）

#### 模板 A：Wrapper 最小透传

适用场景 + 禁止误用：用于新 Ball 的标准 wrapper 接线；禁止在此层加入计算状态机或数据路径逻辑。若 Ball 需要 sub-ROB 下发，禁止继续使用 tie-off 版本。

```scala
@instantiable
class <Name>Ball(val b: GlobalConfig) extends Module with HasBlink {
  val ballCommonConfig = b.ballDomain.ballIdMappings.find(_.ballName == "<Name>Ball")
    .getOrElse(throw new IllegalArgumentException("<Name>Ball not found in config"))
  val inBW  = ballCommonConfig.inBW
  val outBW = ballCommonConfig.outBW

  @public
  val io = IO(new BlinkIO(b, inBW, outBW))
  def blink: BlinkIO = io

  val core: Instance[<Name>] = Instantiate(new <Name>(b))
  core.io.cmdReq  <> io.cmdReq
  core.io.cmdResp <> io.cmdResp
  for (i <- 0 until inBW)  { core.io.bankRead(i)  <> io.bankRead(i)  }
  for (i <- 0 until outBW) { core.io.bankWrite(i) <> io.bankWrite(i) }
  io.status <> core.io.status

  // 简单 Ball：无需 sub-ROB 时使用 tie-off
  io.subRobReq.valid := false.B
  io.subRobReq.bits  := SubRobRow.tieOff(b)
}
```

#### 模板 F：复杂 Wrapper（命令路由 + subRobReq）

适用场景 + 禁止误用：用于 gemmini/vector/systolicarray 这类多子模块控制面；禁止把路由 ready 写成恒真导致吞命令。

```scala
val coreA: Instance[CoreA] = Instantiate(new CoreA(b))
val coreB: Instance[CoreB] = Instantiate(new CoreB(b))

val useA = io.cmdReq.bits.cmd.funct7 === 0x12.U
coreA.io.cmdReq.valid := io.cmdReq.valid && useA
coreA.io.cmdReq.bits  := io.cmdReq.bits
coreB.io.cmdReq.valid := io.cmdReq.valid && !useA
coreB.io.cmdReq.bits  := io.cmdReq.bits

io.cmdReq.ready := Mux(useA, coreA.io.cmdReq.ready, coreB.io.cmdReq.ready)

// 需要下发 sub-ROB 时：
encoder.io.subRobRow <> io.subRobReq
```

#### 模板 B：Core 最小骨架（带握手与命令锁存）

适用场景 + 禁止误用：用于单 FSM core 起步（如 relu/transpose/quant/dequant/trace/im2col）；禁止直接套用于多子模块路由型控制面（应改用模板 F）。

```scala
@instantiable
class <Name>(val b: GlobalConfig) extends Module {
  val ballMapping = b.ballDomain.ballIdMappings.find(_.ballName == "<Name>Ball")
    .getOrElse(throw new IllegalArgumentException("<Name>Ball not found in config"))
  val inBW  = ballMapping.inBW
  val outBW = ballMapping.outBW

  @public
  val io = IO(new Bundle {
    val cmdReq    = Flipped(Decoupled(new BallRsIssue(b)))
    val cmdResp   = Decoupled(new BallRsComplete(b))
    val bankRead  = Vec(inBW, Flipped(new BankRead(b)))
    val bankWrite = Vec(outBW, Flipped(new BankWrite(b)))
    val status    = new BallStatus
  })

  val rob_id_reg = RegInit(0.U(log2Up(b.frontend.rob_entries).W))
  when(io.cmdReq.fire) { rob_id_reg := io.cmdReq.bits.rob_id }

  for (i <- 0 until inBW) {
    io.bankRead(i).io.req.valid     := false.B
    io.bankRead(i).io.req.bits.addr := 0.U
    io.bankRead(i).io.resp.ready    := false.B
    io.bankRead(i).bank_id          := 0.U
    io.bankRead(i).group_id         := 0.U
    io.bankRead(i).rob_id           := rob_id_reg
    io.bankRead(i).ball_id          := 0.U
  }
  for (i <- 0 until outBW) {
    io.bankWrite(i).io.req.valid      := false.B
    io.bankWrite(i).io.req.bits.addr  := 0.U
    io.bankWrite(i).io.req.bits.data  := 0.U
    io.bankWrite(i).io.req.bits.mask  := VecInit(Seq.fill(b.memDomain.bankMaskLen)(0.U(1.W)))
    io.bankWrite(i).io.req.bits.wmode := false.B
    io.bankWrite(i).io.resp.ready     := false.B
    io.bankWrite(i).bank_id           := 0.U
    io.bankWrite(i).group_id          := 0.U
    io.bankWrite(i).rob_id            := rob_id_reg
    io.bankWrite(i).ball_id           := 0.U
  }

  val idle :: sRead :: sCompute :: sWrite :: complete :: Nil = Enum(5)
  val state = RegInit(idle)

  io.cmdReq.ready        := state === idle
  io.cmdResp.valid       := false.B
  io.cmdResp.bits.rob_id := rob_id_reg

  val rbank_reg = RegInit(0.U(log2Up(b.memDomain.bankNum).W))
  val wbank_reg = RegInit(0.U(log2Up(b.memDomain.bankNum).W))
  val iter_reg  = RegInit(0.U(b.frontend.iter_len.W))

  switch(state) {
    is(idle) {
      when(io.cmdReq.fire) {
        rbank_reg := io.cmdReq.bits.cmd.op1_bank
        wbank_reg := io.cmdReq.bits.cmd.wr_bank
        iter_reg  := io.cmdReq.bits.cmd.iter
        state     := sRead
      }
    }
    is(complete) {
      io.cmdResp.valid := true.B
      when(io.cmdResp.fire) { state := idle }
    }
  }

  io.status.idle    := (state === idle)
  io.status.running := (state =/= idle) && (state =/= complete)
}
```

#### 模板 C：参数文件最小骨架

适用场景 + 禁止误用：用于所有需要 JSON 参数加载的 Ball；禁止把配置读入后再用硬编码 `require` 锁死运行路径。

```scala
case class <Name>BallParam(
  // TODO: Ball-specific parameters
)

object <Name>BallParam {
  implicit val rw: ReadWriter[<Name>BallParam] = macroRW

  def apply(): <Name>BallParam = {
    val jsonStr = scala.io.Source
      .fromFile("src/main/scala/framework/balldomain/prototype/<name>/configs/default.json")
      .mkString
    read[<Name>BallParam](jsonStr)
  }
}
```

#### 模板 D：ISA 宏最小骨架

适用场景 + 禁止误用：用于新指令 C 宏接入；禁止 funct7 与已有指令冲突或遗漏 `isa.h` 引入。

```c
#ifndef _BB_<NAME>_H_
#define _BB_<NAME>_H_

#include "isa.h"

#define BB_<NAME>_FUNC7 <funct7_decimal>

#define bb_<name>(bank_id, wr_bank_id, iter)                                     \
  BUCKYBALL_INSTRUCTION_R_R((BB_BANK0(bank_id) | BB_BANK2(wr_bank_id) |          \
                             BB_RD0 | BB_WR | BB_ITER(iter)),                    \
                            0, BB_<NAME>_FUNC7)

#endif
```

#### 模板 E：CTest 最小骨架

适用场景 + 禁止误用：用于功能冒烟与回归测试；禁止只测 `DIM` 固定 happy-path 而不覆盖非零地址或多轮 `iter`。

```c
#include "buckyball.h"
#include <bbhw/isa/isa.h>
#include <bbhw/mem/mem.h>
#include <stdint.h>
#include <stdio.h>

void hw_<name>(elem_t *a, elem_t *b, int size) {
  uint32_t op1_bank_id = 0;
  uint32_t wr_bank_id = 1;

  bb_mem_alloc(op1_bank_id, 1, 1);
  bb_mem_alloc(wr_bank_id, 1, 1);
  bb_mvin((uintptr_t)a, op1_bank_id, size, 1);
  bb_<name>(op1_bank_id, wr_bank_id, size);
  bb_mvout((uintptr_t)b, wr_bank_id, size, 1);
  bb_fence();
}
```

### 8.2.1 复制后替换清单（逐项勾选）

- 通用占位符：
  - [ ] `<Name>` 已替换为 Scala 类名（大驼峰，例如 `Transpose4x4`）
  - [ ] `<name>` 已替换为目录/包名（小写，例如 `transpose4x4`）
  - [ ] `<NAME>` 已替换为宏名（全大写，例如 `TRANSPOSE4X4`）
- 模板 A（Wrapper）：
  - [ ] `"<Name>Ball"` 与 `default.json` 中 `ballName` 完全一致
  - [ ] `Instance[<Name>]` 与 core 类名一致
  - [ ] 已明确选择 `subRobReq` 策略：tie-off 或 encoder 驱动（二选一）
- 模板 F（复杂 Wrapper）：
  - [ ] `io.cmdReq.ready` 由目标消费者 `ready` 决定，而非恒真
  - [ ] 命令分类条件（如 funct7）与下游模块语义一致
  - [ ] `cmdResp` 合并策略明确（arbiter 或优先级）且无冲突
- 模板 B（Core）：
  - [ ] `rbank_reg/wbank_reg/iter_reg` 在 `cmdReq.fire` 当拍锁存
  - [ ] 未在后续状态直接依赖瞬时 `io.cmdReq.bits`
  - [ ] 所有 lane 默认值先置 `req.valid=false`、`resp.ready=false`
- 模板 C（Param）：
  - [ ] JSON 路径 `prototype/<name>/configs/default.json` 已替换为真实目录
  - [ ] `case class` 字段与 `default.json` 键集合一致
- 模板 D（ISA 宏）：
  - [ ] `<funct7_decimal>` 已替换且与 `DISA.scala` 保持一致
  - [ ] `bb_<name>` 与 CTest 中调用名一致
  - [ ] 新宏文件已在 `bb-tests/workloads/lib/bbhw/isa/isa.h` 中 include
- 模板 E（CTest）：
  - [ ] `bb_<name>(...)` 与 ISA 宏函数名一致
  - [ ] 已注册 `add_cross_platform_test_target(...)` 到 CMake
  - [ ] 覆盖至少一个非零地址/多轮 `iter` 用例（不是仅固定 happy-path）

### 8.3 全流程参考清单（供编排器/全流程 skill）

- Ball 实现完成后，注册平面通常需要依次处理：
  - `framework/balldomain/configs/default.json`
  - `examples/toy/balldomain/bbus/busRegister.scala`
  - `examples/toy/balldomain/DISA.scala`
  - `examples/toy/balldomain/DomainDecoder.scala`
- ISA/C 测试通常需要补齐：
  - `bb-tests/workloads/lib/bbhw/isa/<funct7>_<name>.c`
  - `bb-tests/workloads/lib/bbhw/isa/isa.h`
  - `bb-tests/workloads/src/CTest/toy/<name>_test.c`
  - `bb-tests/workloads/src/CTest/toy/CMakeLists.txt`

### 8.4 阶段边界（避免冲突）

- 本文作为通用规则，允许描述全流程参考。
- 但在多 agent 工作流中必须遵守职责隔离：
  - Author 阶段仅修改 prototype 实现。
  - Registrar 阶段仅修改 mapping/generator/decode。
  - CTest 阶段仅修改测试与 ISA 工件。
  - Runtime 阶段仅执行构建/仿真与日志分析。

## 9. Source of truth

- `arch/src/main/scala/framework/balldomain/prototype/relu/*`
- `arch/src/main/scala/framework/balldomain/prototype/transpose/*`
- `arch/src/main/scala/framework/balldomain/prototype/im2col/*`
- `arch/src/main/scala/framework/balldomain/prototype/vector/*`
- `arch/src/main/scala/framework/balldomain/prototype/quant/*`
- `arch/src/main/scala/framework/balldomain/prototype/dequant/*`
- `arch/src/main/scala/framework/balldomain/prototype/trace/*`
- `arch/src/main/scala/framework/balldomain/prototype/gemmini/*`
- `arch/src/main/scala/framework/balldomain/prototype/systolicarray/*`

## 10. 分级约束矩阵（复杂 Ball 兼容）

### 10.1 全类型 MUST（所有 Ball 必须满足）

- 接口命名与类型一致：`cmdReq/cmdResp/bankRead/bankWrite/status`。
- 命令语义安全：除路由当拍透传外，后续状态不得依赖未锁存的瞬时 `cmdReq.bits`。
- 握手驱动推进：核心状态推进由 `fire` 驱动，不依赖理想无阻塞假设。
- lane 纪律：默认 `req.valid=false`、`resp.ready=false`，只对实际消费通道拉高 ready。
- 完成语义：`cmdResp` 仅在真实完成时拉高，且可被 backpressure 正确处理。
- 数据布局声明：必须声明并实现一致（`scalar-per-address` 或 `packed-word`）。

### 10.2 单 FSM core SHOULD（简单 Ball 强烈建议）

- `cmdReq.ready` 在 `idle` 拉高。
- 状态命名采用 `idle -> read -> compute -> write -> complete` 或等价变体。
- 单 core 内完成全部控制与数据路径，不引入额外路由层。

### 10.3 路由型控制面 ALLOWED（复杂 Ball 合法例外）

- `cmdReq.ready` 可由目标消费者 ready 路由决定（例如 gemmini 的分类分发）。
- `subRobReq` 可由编码器或仲裁器主动驱动，不要求 tie-off。
- 可采用“控制器 + load/ex/store 子模块”解耦结构（如 vector/systolicarray）。
- 元数据字段可常驻赋值，也可按请求赋值；二者择一且语义一致即可。

### 10.4 例外使用门槛（必须文档化）

- 若使用 10.3 例外，Design Notes 必须写明：
  - 命令分发规则（按 funct7/子命令/模式位）
  - `cmdReq.ready` 计算来源
  - `cmdResp` 合并策略（优先级或仲裁）
  - `subRobReq` 触发条件
- 未文档化的例外视为不合规实现。

### 10.5 审计结论（当前参考实现）

- `relu/transpose/quant/dequant/im2col/trace`：基本满足 10.1，符合 10.2 风格。
- `vector/systolicarray`：满足 10.1，使用 10.3 的模块解耦控制面。
- `gemmini`：满足 10.1，属于 10.3 的命令路由 + subRob 主动驱动范式。

## 11. 复杂算子外部检索策略（Author 可自动执行）

### 11.1 总原则

- 默认本地优先：先使用本仓库规则与参考 Ball。
- 遇到复杂算子且本地样例不足时，Author 允许自动外部检索，不视为越权。
- 外部方案仅作“思路参考”，最终接口与语义必须回归本仓库规范。

### 11.2 自动触发条件（满足任一条即触发）

- 需要多子模块路由控制面（类似 gemmini/vector/systolicarray）。
- 需要复杂 dataflow（如 preload/compute/flush、转置/展开、双缓冲、流水排空）。
- 需要特殊数值路径（量化/反量化、混合精度、定制饱和/舍入规则）。
- 本地参考无法覆盖关键决策（例如 `cmdReq.ready` 路由、`cmdResp` 合并、subRob 触发时机）。

### 11.3 强制产出物（必须写入 Design Notes）

- `External References`：列出外部来源标题/链接/版本。
- `Adoption Boundary`：哪些点被采纳，哪些点被拒绝。
- `Local Alignment Diff`：外部实现与本仓库规则的差异及对齐方法。
- `Risk Notes`：版本差异风险（尤其 Chisel 版本 API 差异）。

### 11.4 禁止事项

- 禁止直接复制外部实现并绕过本仓库接口契约。
- 禁止引入与 `01-hw-interface` 冲突的命名、握手或状态语义。
- 禁止省略来源说明（未记录来源等同未审计）。
