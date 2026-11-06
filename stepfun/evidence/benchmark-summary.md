# StepKB 实测汇总

生成时间：2026-11-06T02:25:38.401Z

## 环境

- os: Windows 11 26300
- browser: Microsoft Edge 156.0.4314.50
- cpu: Intel Core Ultra 7 155H (16C/22T)
- gpu: Intel Arc Graphics
- ram: 31.5 GiB
- seekdb: seekdb 1.4.0 (server mode, v1.4.0.0)
- corpus: 20 docs / 20 chunks / 15 labelled queries
- protocol: fresh browser context per run; 3 runs per backend; 15 queries per run

## 浏览器 / 后端对比（3 次运行的中位数，热态 42 条查询）

| 指标 | WebGPU · FP16 | WASM · INT8 |
| --- | ---: | ---: |
| 模型文件体积 | 45.3 MiB | 22.9 MiB |
| 模型加载（冷启动） | 1269 ms | 1032 ms |
| 模型预热 | 842 ms | 65 ms |
| 20 篇导入 · 浏览器向量化 | 732 ms | 2197 ms |
| 20 篇导入 · 写入 + 刷新 | 881 ms | 761 ms |
| 其中索引刷新 | 521 ms | 516 ms |
| 导入端到端 | 1748 ms | 3020 ms |
| 查询向量化 | 34 ms | 31 ms |
| seekdb 检索 | 13 ms | 8 ms |
| 端到端查询 | 83 ms | 78 ms |
| 端到端 p95 | 145 ms | 119 ms |
| 首次查询端到端 | 439 ms | 159 ms |
| 混合检索 Recall@5 | 0.8667 | 0.9 |
| 混合检索 nDCG@5 | 0.8787 | 0.8945 |
| Top-1 命中 | 45/45 | 45/45 |

## 自动降级验证

- 结果：WASM · INT8 降级
- 界面提示：已自动降级到 WASM · INT8 当前浏览器没有暴露 navigator.gpu
- 混合检索 Recall@5 / nDCG@5：0.9 / 0.8945

## 原始数据

- `benchmark-webgpu-1..3.json` / `benchmark-wasm-1..3.json`
- `benchmark-fallback.json`
- `quality-eval.json`
