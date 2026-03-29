# Compiler Markdown 全量算子扫描报告

## 扫描范围
- 根目录: /home/ROXY/Code/buckyball/compiler
- Markdown 总数: 334
- 命中关键词文件数: 115

## 关键词全局频次
| 关键词 | 次数 |
|---|---:|
| fir | 2068 |
| vector | 917 |
| matmul | 154 |
| transpose | 82 |
| conv | 28 |
| rvv | 26 |
| convolution | 25 |
| relu | 24 |
| iir | 17 |
| gemmini | 6 |
| attention | 6 |
| fft | 4 |
| pool | 3 |
| mvin | 3 |
| mvout | 3 |
| quant | 2 |
| im2col | 0 |
| dequant | 0 |
| softmax | 0 |
| bfp | 0 |
| systolic | 0 |

## 文件级命中（Top 80，按总命中降序）
| 文件 | 总命中 | 主要关键词 |
|---|---:|---|
| compiler/llvm/flang/docs/HighLevelFIR.md | 594 | matmul:7, transpose:4, vector:11, fir:572 |
| compiler/llvm/flang/docs/PolymorphicEntities.md | 276 | fir:276 |
| compiler/llvm/flang/docs/FIRArrayOperations.md | 210 | fir:210 |
| compiler/llvm/flang/docs/ProcedurePointer.md | 209 | fir:209 |
| compiler/llvm/flang/docs/ParameterizedDerivedTypes.md | 193 | vector:7, fir:186 |
| compiler/llvm/mlir/docs/Dialects/Vector.md | 187 | matmul:1, vector:186 |
| compiler/docs/DynamicVector.md | 178 | rvv:19, vector:159 |
| compiler/llvm/flang/docs/AssumedRank.md | 164 | attention:1, fir:163 |
| compiler/llvm/flang/docs/ArrayRepacking.md | 133 | fir:133 |
| compiler/docs/RVVInstructionSupport.md | 92 | rvv:2, vector:90 |
| compiler/llvm/flang/docs/OpenMP-descriptor-management.md | 72 | fir:72 |
| compiler/llvm/mlir/docs/Tutorials/transform/ChH.md | 69 | conv:16, convolution:11, relu:16, vector:26 |
| compiler/llvm/lldb/docs/resources/lldbgdbremote.md | 58 | vector:58 |
| compiler/llvm/flang/docs/OpenACC-descriptor-management.md | 51 | vector:2, fir:49 |
| compiler/llvm/llvm/docs/AMDGPUDwarfExtensionAllowLocationDescriptionOnTheDwarfExpressionStack/AMDGPUDwarfExtensionAllowLocationDescriptionOnTheDwarfExpressionStack.md | 47 | vector:47 |
| compiler/llvm/flang/docs/Intrinsics.md | 42 | matmul:10, transpose:2, vector:30 |
| compiler/llvm/mlir/docs/Tutorials/transform/Ch1.md | 39 | matmul:37, relu:2 |
| compiler/llvm/lldb/docs/use/aarch64-linux.md | 38 | vector:38 |
| compiler/llvm/mlir/docs/Tutorials/transform/Ch0.md | 37 | matmul:5, convolution:1, relu:2, vector:29 |
| compiler/docs/AddPass.md | 35 | matmul:5, vector:30 |
| compiler/llvm/mlir/docs/Tutorials/transform/Ch4.md | 34 | matmul:33, relu:1 |
| compiler/llvm/flang/docs/DoConcurrentConversionToOpenMP.md | 30 | fir:30 |
| compiler/llvm/flang/docs/ComplexOperations.md | 29 | fir:29 |
| compiler/llvm/flang/docs/AliasingAnalysisFIR.md | 25 | fir:25 |
| compiler/llvm/mlir/docs/SPIRVToLLVMDialectConversion.md | 24 | vector:24 |
| compiler/llvm/flang/docs/DebugGeneration.md | 23 | fir:23 |
| compiler/examples/README.md | 22 | conv:4, convolution:4, vector:2, iir:6, fir:6 |
| compiler/llvm/flang/docs/fstack-arrays.md | 22 | fir:22 |
| compiler/llvm/flang/docs/FortranIR.md | 20 | fir:20 |
| compiler/llvm/mlir/docs/Dialects/LLVM.md | 20 | vector:20 |
| compiler/llvm/mlir/docs/Tutorials/Toy/Ch-3.md | 19 | transpose:19 |
| compiler/docs/IIRVectorizationAlgorithm.md | 17 | vector:6, iir:11 |
| compiler/llvm/mlir/docs/Dialects/Linalg/_index.md | 16 | matmul:1, conv:1, transpose:1, vector:13 |
| compiler/llvm/mlir/docs/Rationale/Rationale.md | 14 | matmul:2, convolution:3, vector:8, fft:1 |
| compiler/llvm/flang/docs/ArrayComposition.md | 13 | matmul:3, transpose:6, vector:4 |
| compiler/docs/conv-opt.md | 12 | conv:1, convolution:2, vector:9 |
| compiler/llvm/mlir/docs/Tutorials/Toy/Ch-2.md | 12 | transpose:12 |
| compiler/examples/RISCVBuddyExt/README.md | 11 | gemmini:5, mvin:3, mvout:3 |
| compiler/llvm/flang/docs/Overview.md | 11 | fir:11 |
| compiler/llvm/mlir/docs/Rationale/RationaleLinalgDialect.md | 11 | matmul:5, conv:2, vector:4 |
| compiler/llvm/llvm/docs/SandboxVectorizer.md | 10 | vector:10 |
| compiler/llvm/mlir/docs/DataLayout.md | 10 | vector:10 |
| compiler/llvm/llvm/docs/InstCombineContributorGuide.md | 9 | vector:9 |
| compiler/llvm/mlir/docs/Dialects/SPIR-V.md | 9 | vector:9 |
| compiler/llvm/mlir/docs/Tutorials/Toy/Ch-7.md | 9 | transpose:9 |
| compiler/examples/BuddyGPU/README.md | 8 | matmul:8 |
| compiler/llvm/flang/docs/DesignGuideline.md | 8 | fir:8 |
| compiler/llvm/mlir/docs/Tutorials/Toy/Ch-1.md | 8 | transpose:8 |
| compiler/llvm/mlir/docs/Tutorials/Toy/Ch-5.md | 7 | transpose:7 |
| compiler/llvm/mlir/docs/Bufferization.md | 6 | matmul:4, vector:2 |
| compiler/llvm/mlir/docs/Dialects/OpenACCDialect.md | 6 | fir:6 |
| compiler/llvm/mlir/docs/LangRef.md | 6 | matmul:1, vector:5 |
| compiler/llvm/mlir/docs/TargetLLVMIR.md | 6 | vector:6 |
| compiler/docs/Quantization.md | 5 | matmul:5 |
| compiler/docs/RVVEnvironment.md | 5 | rvv:4, vector:1 |
| compiler/frontend/Python/graph/transform/quantization/readme.md | 5 | matmul:4, transpose:1 |
| compiler/llvm/flang/docs/Calls.md | 5 | vector:4, pool:1 |
| compiler/llvm/flang/docs/InternalProcedureTrampolines.md | 5 | pool:1, fir:4 |
| compiler/llvm/mlir/docs/Canonicalization.md | 5 | transpose:5 |
| compiler/llvm/mlir/docs/DefiningDialects/Operations.md | 5 | convolution:1, vector:4 |
| compiler/llvm/mlir/docs/Dialects/ArmSME.md | 5 | matmul:3, vector:2 |
| compiler/llvm/mlir/docs/Dialects/Linalg/OpDSL.md | 5 | matmul:3, vector:2 |
| compiler/llvm/mlir/docs/Dialects/ShapeDialect.md | 5 | matmul:5 |
| compiler/llvm/mlir/docs/Tutorials/Toy/Ch-4.md | 5 | transpose:5 |
| compiler/llvm/third-party/benchmark/docs/user_guide.md | 5 | vector:5 |
| compiler/docs/RFFTAlgorithmDev.md | 4 | vector:2, fft:2 |
| compiler/docs/dip-opt.md | 4 | convolution:1, vector:3 |
| compiler/examples/PyTorchTriton/README.md | 4 | matmul:4 |
| compiler/llvm/flang/docs/OpenMP-declare-target.md | 4 | vector:1, fir:3 |
| compiler/llvm/llvm/docs/ReleaseNotes.md | 4 | vector:4 |
| compiler/docs/AddingOperatorsAndModelIntegration.md | 3 | conv:1, transpose:1, pool:1 |
| compiler/examples/BuddyOneDNN/README.md | 3 | matmul:2, relu:1 |
| compiler/examples/BuddyTransformer/README.md | 3 | vector:1, attention:2 |
| compiler/llvm/flang/docs/Aliasing.md | 3 | vector:3 |
| compiler/llvm/mlir/docs/Diagnostics.md | 3 | vector:3 |
| compiler/llvm/mlir/docs/PassManagement.md | 3 | conv:3 |
| compiler/llvm/mlir/docs/Tutorials/transform/Ch2.md | 3 | matmul:3 |
| compiler/docs/BuildMethods.md | 2 | gemmini:1, rvv:1 |
| compiler/llvm/clang/docs/DataFlowAnalysisIntro.md | 2 | vector:2 |
| compiler/llvm/flang/Maintainers.md | 2 | fir:2 |

## 可直接复用为 Buckyball 负载设计的高价值文档
- compiler/README.md
- compiler/docs/BuildMethods.md
- compiler/docs/DomainSpecificSupport.md
- compiler/docs/Quantization.md
- compiler/docs/conv-opt.md
- compiler/docs/dip-opt.md
- compiler/docs/RVVInstructionSupport.md
- compiler/examples/README.md
