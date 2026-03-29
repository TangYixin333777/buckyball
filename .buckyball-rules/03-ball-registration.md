# Buckyball Ball Registration Baseline

scope: registrar
source_of_truth:
- arch/src/main/scala/framework/balldomain/configs/default.json
- arch/src/main/scala/examples/toy/balldomain/bbus/busRegister.scala
- arch/src/main/scala/examples/toy/balldomain/DISA.scala
- arch/src/main/scala/examples/toy/balldomain/DomainDecoder.scala

## must

- Update exactly three planes for each new Ball registration.
- Keep mapping, generator, and decode mutually consistent.
- Allocate ballId by strict increment: max(existing ballId) + 1.
- Allocate funct7 by strict increment from existing DISA bit patterns.
- Keep ballNum equal to ballIdMappings count.
- Keep generator match key equal to mapping.ballName.
- Keep decode BID equal to mapping.ballId.

## forbidden

- Do not skip any registration plane.
- Do not reuse old ballId/funct7 values.
- Do not reorder existing entries unless explicitly requested.

## current_baseline

- Mapping entries:
  - 0 -> VecBall (inBW=2, outBW=4)
  - 1 -> ReluBall (inBW=1, outBW=1)
  - 2 -> TransposeBall (inBW=1, outBW=1)
  - 3 -> Im2colBall (inBW=1, outBW=1)
- DISA entries:
  - MATMUL_WARP16 = b0100000
  - IM2COL = b0100001
  - TRANSPOSE = b0100010
  - RELU = b0100110

## examples

- Mapping plane:
  - arch/src/main/scala/framework/balldomain/configs/default.json
- Generator plane:
  - arch/src/main/scala/examples/toy/balldomain/bbus/busRegister.scala
- Decode plane:
  - arch/src/main/scala/examples/toy/balldomain/DISA.scala
  - arch/src/main/scala/examples/toy/balldomain/DomainDecoder.scala

## validation

- Unique check:
  - ballId appears once in ballIdMappings.
  - funct7 symbol and value appear once in DISA.
- Consistency check:
  - decode.bid == mapping.ballId
  - mapping.ballName == wrapper class simple name
  - ballNum == len(ballIdMappings)

## failure_cases

- Added mapping but decode BID unchanged.
- Added decode row but missing generator case.
- Increased ballNum without mapping append.
