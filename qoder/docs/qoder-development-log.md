# Qoder 开发记录

## 0. 提交信息

| 字段 | 值 |
| --- | --- |
| Qoder 账号 UID | `01a1ae9f-8582-7830-820d-5c3a81b453d9` |
| 使用的 Qoder 形态 | Qoder CN 桌面端（Desktop） |
| 代码仓库 | `https://github.com/xzhtry/powercontext/tree/2026-competition-ecosystem/qoder` |
| 分支 / commit | `2026-competition-ecosystem` / `80afba26` |
| Qoder Sites 网址 | `https://researchthread-h1wllzi3wl6.qoder.zone/` |
| 本地验证日期 | 2026-11-06 — 2026-11-07 |
| 验证环境 | Windows 11 + Python 3.12 + seekdb 1.4.0 + PowerContext 1.4.1 |

## 1. 这次 Qoder 实际做了什么

1. **读懂并跑通项目**：阅读 `app/main.py`、`app/seekdb.py`、`app/memory.py`、`README` 和架构文档；检查 `18890` 的 `/api/health` 与 `/api/bootstrap`，确认 `papers=508`、seekdb / PowerContext 可用。期间发现 `18891` 实例的 PowerContext 因运行时路径权限不可用，改回 `18890` 做验收。
2. **新增综述 v2 模板**：在 `app/synthesis.py` 增加五段式 `review_v2`（背景 / 方法 / 结果 / 局限 / 研究空白），在 `app/main.py` 放宽模板枚举，在 `app/static/app.js` 增加模板选项与按钮文案，并补测试。
3. **新增 BibTeX 导出**：在 `app/main.py` 增加 `/api/export/evidence.bib`、单次扫描的 `_latex_escape` 与 BibTeX key 生成；在证据表加下载按钮；补特殊字符与 key 生成测试。
4. **发布 Qoder Sites**：把 `site/` 发布为公开站点，未登录可访问；URL 见上表。

## 2. 会话记录

| # | 日期 | Qoder 任务 | Qoder 实际完成的工作 | 改动文件 | 验证 | 截图 |
| ---: | --- | --- | --- | --- | --- | --- |
| 1 | 2026-11-06 | 跑通 / 验证 | 读关键源码；检查 18890 health；确认 508 篇、seekdb 与 PowerContext 可用；区分 18891 的 PowerContext 权限问题 | 无代码改动 | `/api/health`、`scripts/verify.py` | `qoder-01-overview.png`、`qoder-01-prompt.png`、`qoder-01-tools.png`、`qoder-01-today.png`、`qoder-01-health.png` |
| 2 | 2026-11-06 | 综述 v2 | 新增 `_review_v2`、五段式结构、模板枚举、UI 选项、生成按钮文案；补 5 个二级标题 / 参考条数 / 空证据测试 | `app/synthesis.py`、`app/main.py`、`app/static/app.js`、`tests/test_units.py` | `pytest` 13 passed；`verify.py` PASS；页面生成 review_v2 | `qoder-02-prompt.png`、`qoder-02-reviewv2.png`、`qoder-02-diff.png`；**待补**：`qoder-02-tests.png` |
| 3 | 2026-11-06–07 | BibTeX 导出 | 新增 `/api/export/evidence.bib`；单次扫描转义 `\ & % _ # { } ~ ^`；生成 `@article`；证据表加 BibTeX 按钮；补转义与 key 测试 | `app/main.py`、`app/static/app.js`、`tests/test_units.py` | `pytest` 13 passed；接口 200，10 条 `@article` | `qoder-03-prompt.png`、`qoder-03-process.png`、`qoder-03-bib.png`；**待补**：`qoder-03-tests.png` |
| 4 | 2026-11-07 | Qoder Sites 发布 | 发布 `site/`，设置公开；无痕访问确认 200 | `site/*`、`.qoder.site` 元数据 | 未登录 HTTP 200；CSS/JS/6 张图均 200 | `qoder-04-sites-live.png`；**待补**：`qoder-04-sites-publish.png`、`qoder-04-sites-incognito.png` |

## 3. 截图状态

已归档在 `docs/screenshots/`：

| 文件 | 内容 | 状态 |
| --- | --- | --- |
| `qoder-01-overview.png` | Qoder 工具调用 + 应用页面总览 | ✅ |
| `qoder-01-prompt.png` | 跑通任务的完整 prompt | ✅ |
| `qoder-01-tools.png` | 工具调用 / 失败重试 / All checks pass | ✅ |
| `qoder-01-health.png` | `18890/api/health` 运行截图（JSON） | ✅ 运行证据，非 Qoder 对话 |
| `qoder-01-today.png` | 18890 今日研究台（508 篇 / 10 条判断 / 15 条记忆） | ✅ |
| `qoder-02-prompt.png` | review_v2 完整 prompt | ✅ |
| `qoder-02-diff.png` | review_v2 文件改动 `app.js +2/-1`、`synthesis.py +189/-1` | ✅ |
| `qoder-02-reviewv2.png` | 综述 v2 生成结果（背景 / 方法） | ✅ 建议再补一张 1–5 全标题 |
| `qoder-03-prompt.png` | BibTeX 完整 prompt | ✅ |
| `qoder-03-process.png` | Qoder 修改 / 13 tests pass / 下载 .bib | ✅ |
| `qoder-03-bib.png` | 实际 `.bib` 内容（10 条 `@article`，UTF-8 预览） | ✅ |
| `qoder-04-sites-live.png` | 已发布站点首页（公开访问） | ✅ |
| `qoder-account-uid.png` | Qoder 账号 ID（已裁掉手机号） | ✅ |

还需要补：

| 文件 | 内容 |
| --- | --- |
| `qoder-02-tests.png` | 终端 `pytest` 13 passed + `verify.py` PASS |
| `qoder-02-reviewv2-bottom.png`（可选） | 综述 v2 的 `3. 结果 / 4. 局限 / 5. 研究空白`，或一张 1–5 全标题的截图 |
| `qoder-03-tests.png` | BibTeX 改动后的测试输出 |
| `qoder-04-sites-publish.png` | Qoder Sites 发布面板 + 「任何人都可访问」 |
| `qoder-04-sites-incognito.png` | 无痕窗口打开线上站点 |

## 4. 复跑验证

在 `D:\oceanbase大赛\eco-work\qoder`：

```powershell
.\.venv\Scripts\python.exe -m pytest
.\.venv\Scripts\python.exe scripts\verify.py --base-url http://127.0.0.1:18890
```

最近一次结果：

- `pytest`：13 passed
- `verify.py`：全 PASS（508 篇 / 35 条检索命中 / 证据写入 / 综述写入 PowerContext / 新会话交接）
- `GET /api/export/evidence.bib`：200，10 条 `@article`
- 线上站点：`https://researchthread-h1wllzi3wl6.qoder.zone/`，未登录 200

## 5. 提交前检查

- [x] Qoder 账号 UID 已填写；
- [x] 至少 3 个关键会话有真实截图；
- [x] 每个会话有对应 commit / 文件改动；
- [x] `pytest` / `verify.py` 最近一次 PASS；
- [x] Qoder Sites 在未登录状态可访问；
- [ ] 补齐上面「还需要补」的截图；
- [ ] 提交前删除本节未完成项，或确认平台允许单独上传截图；
- [ ] 截图隐去手机号等个人信息（`qoder-account-uid.png` 已裁掉）；
- [ ] 没有把往年题解/他人代码直接搬入。
