# Buckyball Ball Registration Result

## Applied Changes

- mapping plane: 更新 `arch/src/main/scala/framework/balldomain/configs/default.json`，新增 `ColNormBall` 映射并将 `ballNum` 从 4 调整为 5。
- generator plane: 更新 `arch/src/main/scala/examples/toy/balldomain/bbus/busRegister.scala`，新增 import 与 `case "ColNormBall"` 生成器。
- decode plane:
  - 更新 `arch/src/main/scala/examples/toy/balldomain/DISA.scala`，新增 `COLNORM = BitPat("b0100111")`。
  - 更新 `arch/src/main/scala/examples/toy/balldomain/DomainDecoder.scala`，新增 `COLNORM` decode row，`BID = 4.U`。

## Invariant Checks

- `decode.bid == mapping.ballId`：通过（4 == 4）。
- `mapping.ballName == ball_name`：通过（`ColNormBall`）。
- `ballId` 无重复：通过（0,1,2,3,4）。
- `funct7/symbol` 无冲突：通过（`b0100111/COLNORM` 为新值）。

## Contract Source

- 本文 JSON 为示例实例，不是 schema 定义。
- 权威 schema 与必填字段来源：
  - `.github/promote/BALL_REGISTRATION_RESULT_V1.template.json`
  - `.github/promote/contracts.meta.json`

## BALL_REGISTRATION_RESULT_V1

```json
{
  "result_version": "BALL_REGISTRATION_RESULT_V1",
  "ball_name": "ColNormBall",
  "mapping_applied": true,
  "generator_applied": true,
  "decode_applied": true,
  "touched_files": [
    "arch/src/main/scala/framework/balldomain/configs/default.json",
    "arch/src/main/scala/examples/toy/balldomain/bbus/busRegister.scala",
    "arch/src/main/scala/examples/toy/balldomain/DISA.scala",
    "arch/src/main/scala/examples/toy/balldomain/DomainDecoder.scala"
  ],
  "errors": []
}
```

请将本文保存为 .buckyball-rules/05-ball-registrar-output.md.
