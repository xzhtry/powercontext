# Qoder 开发记录（提交模板）

> **重要（提交前删除本块）**：赛道要求“项目的主要开发工作必须在 Qoder 中完成”，并要求保留 Qoder 对话截图与账号 UID 供核对。本仓库提供可运行初版、任务清单和验证脚本；**提交者必须在 Qoder 中完成至少 3 个关键开发/修复环节，保存真实截图，再填写本文件**。不要编造截图、UID 或站点归属；评委可核对 Qoder 账号与 Qoder Sites 站点。
>
> 推荐最小合规路径：按 [`qoder-prompts.md`](qoder-prompts.md) 完成「核心检索排序」「综述模板扩展」「Qoder Sites 发布」三项，并在每项完成后运行 `python scripts/verify.py`。如果希望更稳，再补「证据导出」「PowerContext 降级测试」两项。

## 0. 提交信息

| 字段 | 填写 |
| --- | --- |
| Qoder 账号 UID | `待填写` |
| 使用的 Qoder 形态 | `Desktop / IDE / JetBrains 插件 / CLI`（保留实际使用的一种或多种） |
| 代码仓库 | `https://github.com/xzhtry/powercontext/tree/2026-competition-ecosystem/qoder`（如实际仓库不同请改） |
| 分支 / commit | `2026-competition-ecosystem` / `待填写` |
| Qoder Sites 网址 | `待填写（必须是任何人都可访问）` |
| 本地验证日期 | `待填写` |
| 验证环境 | `Windows 11 + Python 3.12 + seekdb 1.4.0 + PowerContext 1.4.1` |

## 1. 开发记录总览

| # | 日期 | Qoder 任务 | Qoder 实际完成的工作 | 改动文件 | 验证方式 | 截图 |
| ---: | --- | --- | --- | --- | --- | --- |
| 1 | 待填 | 读懂项目并跑通 | 阅读 README/架构，启动 seekdb、PowerContext、Web，定位首次启动问题 | `README.md` / `scripts/*` | `python scripts/verify.py` | `docs/screenshots/qoder-01-run.png` |
| 2 | 待填 | 核心检索排序 | 在 `app/seekdb.py` 实现/调整词法核验与标题加权，补测试 | `app/seekdb.py` | `pytest` + 搜索 `RAG hallucination` | `docs/screenshots/qoder-02-search.png` |
| 3 | 待填 | 综述模板扩展 | 在 `app/synthesis.py` 增加“背景-方法-结果-局限-空白”模板，保持引用编号 | `app/synthesis.py` / `app/main.py` | `python scripts/verify.py` + 页面生成 | `docs/screenshots/qoder-03-synthesis.png` |
| 4 | 待填 | 证据导出 | 增加 BibTeX 导出与 UI 按钮，处理特殊字符 | `app/main.py` / `app/static/*` | 下载并检查 `.bib` | `docs/screenshots/qoder-04-export.png` |
| 5 | 待填 | PowerContext 降级 | 写失败注入测试，确保 seekdb 证据不丢、UI 显示降级 | `app/memory.py` / `app/main.py` / `tests/*` | 停掉 PowerContext 后复跑 | `docs/screenshots/qoder-05-degrade.png` |
| 6 | 待填 | Qoder Sites 发布 | 用 Qoder Sites 发布 `site/`，设为公开，检查无痕访问 | `site/*` | 无痕窗口打开站点 | `docs/screenshots/qoder-06-sites.png` |

> 上表是**模板**，不是已完成的记录。请按实际会话改写“Qoder 实际完成的工作”，删除没有做的行。

## 2. 每次会话的记录格式

对每个关键会话，保存：

1. **Prompt 原文**（可复制文本，不必截图全部上下文）；
2. **Qoder 的关键动作截图**：需求拆解、读取文件、修改、运行命令、报错与修复；
3. **改动文件与 diff 摘要**：`git diff --stat`；
4. **验证输出**：`python scripts/verify.py` 的 PASS 行；
5. **结果截图**：页面/接口/导出文件；
6. **你的复核结论**：哪些逻辑你检查过，哪些是 Qoder 完成。

建议命名：

```
docs/screenshots/qoder-01-prompt.png
docs/screenshots/qoder-01-run.png
docs/screenshots/qoder-02-diff.png
docs/screenshots/qoder-03-verify.png
docs/screenshots/qoder-06-sites-public.png
```

## 3. 会话 1：读懂项目并跑通

- **目标**：让 Qoder 在不看额外说明的情况下，根据 README 启动项目，并指出一个真实的启动/配置问题。
- **建议 prompt**：见 `qoder-prompts.md` 第 1 条。
- **预期 Qoder 动作**：读取 `README.md`、`app/config.py`、`scripts/run.ps1`；检查 Python/依赖；启动 seekdb/PowerContext；访问 `/api/health`；报告 508 篇文献、9 条证据、记忆可用。
- **通过标准**：`/api/health` 返回 `seekdb=true`、`memory_available=true`、`papers>=500`。
- **截图**：Qoder 终端输出 + 浏览器今日研究台。

## 4. 会话 2：核心检索排序

- **目标**：让 Qoder 针对“搜索 `RAG hallucination` 时前 5 条里出现弱相关论文”的问题，调整 `app/seekdb.py` 的排序/过滤，并补一个可复跑的测试。
- **约束**：不能把结果写死；不能只按标题硬编码；必须保留 SQL 轨迹；必须仍然使用 seekdb `MATCH`。
- **通过标准**：前 5 条至少 4 条标题含 `RAG` 或 `hallucination`；`RAGTruth` 在前 2；`scripts/verify.py` 仍 PASS。
- **截图**：Qoder diff + 搜索结果 + SQL 轨迹。

## 5. 会话 3：综述模板扩展

- **目标**：新增 `review_v2` 模板，按“背景 / 方法 / 结果 / 局限 / 研究空白”组织，保留 `[n]` 引用编号与参考列表；在综述台加一个模板选项。
- **约束**：仍然不调用外部模型；无证据时给出明确提示；引用编号必须与证据表一一对应。
- **通过标准**：生成文档包含 5 个二级标题；参考列表条数 = 选中证据数；`scripts/verify.py` 仍 PASS。
- **截图**：Qoder 修改 + 页面生成结果。

## 6. 会话 4（可选）：BibTeX 导出

- **目标**：新增 `/api/export/evidence.bib`，为证据表生成 BibTeX；处理 `&`、`%`、中文标点；在证据表加下载按钮。
- **通过标准**：下载文件可被 Zotero/TeX 解析；特殊字符不破坏条目；UI 按钮可用。

## 7. 会话 5（可选）：PowerContext 降级测试

- **目标**：停掉 PowerContext，验证 seekdb 证据仍可写入、UI 显示降级；恢复后“重新连接”能把新判断补写进记忆。
- **通过标准**：停服时 POST `/api/evidence` 返回 200 且 `memory_available=false`；恢复后 `/api/memory` 能看到该判断。
- **注意**：这是本项目“两个技术分工”的关键证据，建议做。

## 8. 会话 6：Qoder Sites 发布

- **目标**：用 Qoder Sites 发布 `site/`，可见范围设为「任何人都可访问」，用无痕窗口验证。
- **通过标准**：站点 URL 可在未登录状态打开；首页、截图、运行说明、代码仓库链接、验证数据完整；提交后未暂停/删除站点。
- **截图**：Qoder Sites 发布面板 + 无痕窗口页面 + 访问统计（如可用）。

## 9. 提交前检查

- [ ] Qoder UID 已填写，且与站点归属账号一致；
- [ ] 至少 3 个关键会话有真实截图（不是合成图）；
- [ ] 每个会话都有对应 commit / diff；
- [ ] `python scripts/verify.py` 最近一次输出为 PASS；
- [ ] Qoder Sites 在无痕窗口可访问；
- [ ] 截图隐去 API Key、密码、个人信息；
- [ ] 没有把往年题解/他人代码直接搬入。
