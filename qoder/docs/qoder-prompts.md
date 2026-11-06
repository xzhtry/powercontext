# Qoder 任务清单与提示词

> 用法：在 Qoder 中打开 `qoder/` 目录，逐条粘贴 prompt；每完成一项，运行验收命令，保存 Qoder 对话/终端/页面截图，并填回 `qoder-development-log.md`。
>
> 这些任务都建立在仓库现有代码上，Qoder 需要**实际修改文件、运行命令、处理失败**，而不是只写说明。
>
> **本机恢复后的运行参数（2026-11-06）**
>
> - 工作目录：`D:\oceanbase大赛\eco-work\qoder`
> - 为了避开本机 `8787` 的占用，预览使用 `18890`；`seekdb` 用 `18884`，PowerContext 用 `18767`
> - 启动：
>
> ```powershell
> $env:RT_RUNTIME="C:\ob\eco-work\qoder\runtime"
> $env:RT_SEEKDB_PORT="18884"
> $env:RT_PC_PORT="18767"
> $env:RT_PORT="18890"
> .\.venv\Scripts\python.exe -m app
> ```
>
> - 健康检查：`http://127.0.0.1:18890/api/health`
> - 验收：`.\.venv\Scripts\python.exe scripts\verify.py --base-url http://127.0.0.1:18890`
>
> 如果你在 Qoder 中重新安装环境，也可以把 `RT_RUNTIME` 换成一个 ASCII 路径；路径含中文时 Windows 原生 seekdb 可能打不开数据目录。

## 任务 1：读懂项目并跑通（必做）

```text
你是这个仓库的开发者。请先不要改代码：
1. 阅读 README.md、docs/architecture.md、app/main.py、app/seekdb.py、app/memory.py，说明项目如何同时使用 seekdb 和 PowerContext；
2. 按 README 的 Windows 步骤安装依赖并启动（Python 3.12，seekdb 1.4.0，PowerContext 1.4.1）；
3. 访问 http://127.0.0.1:18890/api/health 和 /api/bootstrap，把 papers、evidence、memory 数量贴出来；
4. 如果启动失败，定位根因（端口、路径、依赖、权限），修复后重新验证；不要用假数据绕过。
验收：/api/health 中 seekdb=true、memory_available=true、papers>=500；页面能打开今日研究台。
请把关键命令、失败与修复过程保留在对话里，我要用于 Qoder 开发记录。
```

## 任务 2：核心检索解释（可选；当前排序已实现，不建议重复做）

> 当前 `app/seekdb.py` 已有词法核验与标题加权。如果你还想完成这个会话，请把它改成“给每条结果增加可解释的命中字段”，而不是重复已有排序。更推荐把时间花在任务 3 / 4。

```text
现在检索 "RAG hallucination" 时，前 5 条里有一些论文只是摘要后半段偶然出现 RAG，相关性不够。
请在 app/seekdb.py 中改进排序/过滤，要求：
- 仍然由 seekdb 的 MATCH ... AGAINST 产生候选，不能改成纯 Python 遍历；
- 利用 query term 在 title / abstract 的命中数做可解释的二次核验；
- 对 2 个词的 query 要求两个词都出现；对更长 query 至少命中 max(2, n-2) 个；
- 增加 title 命中权重，但不要把结果写死；
- 在返回结果中保留 matched_terms 和 SQL trace；
- 在 tests/ 下补一个不依赖数据库的测试，覆盖 term 提取/最小命中数逻辑（可以抽成纯函数）。
完成后运行 pytest 和 `.\.venv\Scripts\python.exe scripts\verify.py --base-url http://127.0.0.1:18890`，并贴出 "RAG hallucination" 前 5 条标题与分数。
验收：RAGTruth 仍在前 2；前 5 条至少 4 条标题含 RAG 或 hallucination；verify.py 全 PASS。
```

## 任务 3：综述模板扩展（必做）

```text
请在 app/synthesis.py 新增一个 review_v2 模板，并在综述台增加选项。
要求：
- 结构固定为：背景 / 方法 / 结果 / 局限 / 研究空白；
- 仍然使用证据表的 note 与论文元数据，不调用外部模型；
- 引用编号 [n] 与参考列表一一对应，编号按“支持→挑战→混合→年份倒序”；
- 没有证据时返回明确提示，不生成空引用；
- 在 app/main.py 的 SynthesisIn 中允许 template="review_v2"；
- 在 app/static/app.js 的模板选项里加“综述 v2（背景-方法-结果-局限-空白）”；
- 补一个纯函数测试，断言 5 个二级标题和参考条数。
完成后运行 pytest、`.\.venv\Scripts\python.exe scripts\verify.py --base-url http://127.0.0.1:18890`，并在页面生成一次 review_v2 截图。
```

## 任务 4：BibTeX 导出（可选，但很适合展示完成度）

```text
请为证据表增加 BibTeX 导出：
- 新接口 GET /api/export/evidence.bib；
- 每条证据输出 @article{...}，字段包含 title、author、year、journal/booktitle、url、note；
- 正确处理 & % _ # 等 LaTeX 特殊字符和中文；
- 在证据表工具栏增加“BibTeX”下载按钮；
- 补测试：生成内容包含与证据数量相同的 @article 条目，特殊字符不破坏语法。
完成后下载一次 .bib，贴出前 20 行和测试输出。
```

## 任务 5：PowerContext 降级与恢复（可选，但强烈建议）

```text
请验证并加固“PowerContext 不可用但 seekdb 证据不丢”的路径：
1. 启动应用后，手动停掉 PowerContext Server（不要停 seekdb / Web）；
2. POST /api/evidence 新增一条判断，确认返回 200 且 memory_available=false；
3. 确认 GET /api/evidence 能读到这条判断；
4. 重启 PowerContext，点击记忆页“重新连接”，确认这条判断被补写进 Memory（或给出明确的补写策略）；
5. 如果现有代码不能补写，请实现一个幂等的补写逻辑（按 paper_id 去重），并补测试。
验收：停服不丢证据；恢复后记忆时间线能看到该判断；verify.py 仍 PASS。
请保留停服/恢复的命令与输出截图。
```

## 任务 6：Qoder Sites 发布（必做）

```text
请把 site/ 目录通过 Qoder Sites 发布：
1. 检查 site/index.html 的所有相对路径、图片、链接在静态托管下可用；
2. 用 Qoder Sites 创建站点，可见范围设为“任何人都可访问”；
3. 发布后复制完整 URL，用无痕窗口打开，确认首页、截图、运行说明、代码仓库链接、验证数据都可访问；
4. 如果图片 404 或样式错位，修复 site/ 后重新发布；
5. 把站点 URL、发布时间、无痕访问截图写进 docs/qoder-development-log.md。
验收：未登录状态可打开；页面无 404；移动端宽度 390px 不横向溢出。
```

## 任务 7：整理 Qoder 开发记录（必做）

```text
请根据我们刚才的会话，整理 docs/qoder-development-log.md：
- 填写 Qoder 账号 UID、使用形态、仓库/分支/commit、站点 URL；
- 每个关键会话记录：日期、prompt 摘要、Qoder 实际动作、修改文件、验证输出、截图路径；
- 删除模板中未实际完成的条目；
- 截图放在 docs/screenshots/，文件名遵循 qoder-XX-*.png；
- 最后运行 python scripts/verify.py，把 PASS 输出贴进记录。
不要编造任何未发生的操作或截图。
```

## 建议的 Qoder 会话顺序

1. 任务 1（跑通）→ 截图 01
2. 任务 2（检索排序）→ 截图 02
3. 任务 3（综述 v2）→ 截图 03
4. 任务 6（Sites 发布）→ 截图 06
5. 任务 7（整理记录）
6. 如时间允许：任务 4 / 任务 5

## 提交时最容易被扣分的点

- 只在 Qoder 里让 AI 写 README，代码却在别处完成 → 开发记录无法体现“主要开发工作”；
- 截图只截结果、不截 Qoder 的修改/命令/报错 → 无法核对过程；
- Qoder Sites 设为私有/企业版 → 评审未登录打不开；
- 只安装 seekdb/PowerContext 但没有实际读写 → 技术结合不成立；
- 把示例数据说成真实用户数据 → 使用效果不可核对。
