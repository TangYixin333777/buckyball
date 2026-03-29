# Buckyball Ball Authoring Result

## Files Created

- arch/src/main/scala/framework/balldomain/prototype/colnorm/ColNormBall.scala
- arch/src/main/scala/framework/balldomain/prototype/colnorm/ColNorm.scala
- arch/src/main/scala/framework/balldomain/prototype/colnorm/configs/ColNormBallParam.scala
- arch/src/main/scala/framework/balldomain/prototype/colnorm/configs/default.json

## Design Notes

- 保持 wrapper/core 分层，wrapper 仅做 BlinkIO 适配与透传。
- 核心状态机采用 `idle -> sRead -> sCompute -> sWrite -> complete`。
- `io.cmdReq.ready` 仅在 `idle` 拉高，命令字段在 `cmdReq.fire` 时锁存。
- 读路径与写路径均遵循单通道 Decoupled SRAM 协议，满足规则中的 1-cycle read response 假设。

## Contract Checks

- `mapping.ballName == ball_name`：通过（`ColNormBall`）。
- `decode.bid == mapping.ballId`：通过（均为 `4`）。
- wrapper 类名与 `ballName` 一致：通过（`ColNormBall`）。

## Minimal Contract Guidance

- 仅保留下游注册所需字段，避免在 handoff 中携带实现细节注释。
- `mapping` 与 `decode` 字段必须可直接用于三平面注册，不应再推导。
- 本文 JSON 为示例实例，不是 schema 定义。
- 若字段来源不确定，优先回到 `.github/promote/BALL_HANDOFF_V1.template.json` 与 `.github/promote/contracts.meta.json` 对齐键名、类型和必填字段。

## BALL_HANDOFF_V1

```json
{
  "handoff_version": "BALL_HANDOFF_V1",
  "ball_name": "ColNormBall",
  "core_name": "ColNorm",
  "package": "framework.balldomain.prototype.colnorm",
  "mapping": {
    "ballId": 4,
    "ballName": "ColNormBall",
    "inBW": 1,
    "outBW": 1
  },
  "decode": {
    "disa_symbol": "COLNORM",
    "funct7": "b0100111",
    "bid": 4,
    "needs_op2": false,
    "iter_from": "rs2[9:0]"
  },
  "files": {
    "wrapper": "arch/src/main/scala/framework/balldomain/prototype/colnorm/ColNormBall.scala",
    "core": "arch/src/main/scala/framework/balldomain/prototype/colnorm/ColNorm.scala",
    "config_scala": "arch/src/main/scala/framework/balldomain/prototype/colnorm/configs/ColNormBallParam.scala",
    "config_json": "arch/src/main/scala/framework/balldomain/prototype/colnorm/configs/default.json"
  },
  "constraints": {
    "class_name_must_equal_ballName": true,
    "bid_must_equal_ballId": true
  }
}
```
