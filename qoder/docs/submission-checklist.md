# 提交清单（Qoder × OceanBase 赛道）

> 提交入口：大赛测试平台 → Qoder 赛题。提交前逐项打勾，不要把真实 API Key/密码放进仓库或网站。

## 1. 必填材料

| 材料 | 位置 / 值 | 状态 |
| --- | --- | --- |
| 项目网站网址 | `待填写`（Qoder Sites，任何人都可访问） | [ ] |
| 代码仓库 | `https://github.com/xzhtry/powercontext/tree/2026-competition-ecosystem/qoder`（按实际改） | [ ] |
| 运行说明 | `README.md` 第 3 节 / `docs/validation.md` | [ ] |
| 验证样例 | `scripts/verify.py` + 本文第 2 节手工路径 | [ ] |
| Qoder 开发记录 | `docs/qoder-development-log.md` + `docs/screenshots/` | [ ] |
| Qoder 账号 UID | `待填写` | [ ] |
| 使用效果材料（鼓励） | 真实用户数据；没有就如实写“尚未开展”，不要编造 | [ ] |

## 2. 提交前 30 分钟检查

### 网站

- [ ] Qoder Sites 已点击「发布」，不是仅保存草稿；
- [ ] 可见范围是「任何人都可访问」；企业版账号无法公开，改用个人账号；
- [ ] 无痕窗口打开站点，首页、截图、运行说明、代码仓库链接都可用；
- [ ] 移动端 390px 宽度不横向溢出；
- [ ] 站点图片不是本地绝对路径（不能是 `C:\...` 或 `file://`）；
- [ ] 站点未暂停/删除；评审结束前保持在线。

### 仓库

- [ ] 代码已 push 到 `2026-competition-ecosystem` 的 `qoder/` 目录；
- [ ] 仓库公开，或已给评审开放权限；
- [ ] 没有提交 `.venv/`、`runtime/`、`data/raw/`、日志、真实 API Key；
- [ ] `data/papers.json`、`data/demo.json`、`site/assets/*.png` 已提交；
- [ ] `git status` 干净；记录 commit hash。

### 本地

- [ ] `python scripts/verify.py` 全 PASS；
- [ ] `python -m pytest` 全 PASS；
- [ ] 重置后（`scripts/reset.ps1`）能重新播种 508 篇 + 9 条证据；
- [ ] 关闭浏览器再打开，研究 brief 与记忆仍在；
- [ ] 点击「开始新会话」，交接摘要写入 PowerContext；
- [ ] 停掉 PowerContext 时，seekdb 证据仍可写入（降级路径）。

### Qoder

- [ ] 至少 3 个关键会话有真实截图（需求拆解 / 修改 / 命令 / 报错 / 验证）；
- [ ] 截图里能看到 Qoder 账号或工作区，能对应 UID；
- [ ] 每个会话对应实际 commit / diff；
- [ ] 开发记录中的“Qoder 实际完成的工作”没有夸大；
- [ ] 截图隐去个人信息、API Key、密码。

## 3. 运行说明（给评审的最小路径）

```powershell
cd qoder
powershell -ExecutionPolicy Bypass -File scripts\setup.ps1
powershell -ExecutionPolicy Bypass -File scripts\run.ps1
# 浏览器打开 http://127.0.0.1:8787
# 另一个终端：
.\.venv\Scripts\python.exe scripts\verify.py
```

Linux/macOS：

```bash
cd qoder
bash scripts/setup.sh
bash scripts/run.sh
.venv/bin/python scripts/verify.py
```

## 4. 验证样例（提交时附在材料里）

- 初始数据：`data/papers.json`（508 篇）、`data/demo.json`（9 条证据）
- 输入：`RAG hallucination`
- 预期：35 条命中，首条 `RAGTruth`，SQL 轨迹含 `MATCH ... AGAINST`
- 操作：加入一条“挑战”判断 → 生成综述 → 开始新会话
- 预期技术记录：
  - seekdb：`papers` / `evidence` / `syntheses` / `search_log` 可查询；
  - PowerContext：`research-brief`、`evidence-decision`、`synthesis`、`session-summary` 可在记忆时间线看到；
  - 刷新/重启后 brief 与上次会话摘要仍能恢复。

## 5. 提交话术（可直接改）

> 研脉是一个本地优先的科研阅读与证据工作台。它用 seekdb 的全文检索管理 508 篇 arXiv 摘要并保存证据判断，用 PowerContext 记住研究 brief、判断理由与会话进度；综述提纲由证据表规则生成，引用可逐条核对。项目在 Qoder 中完成关键功能开发与 Qoder Sites 发布，运行说明、验证脚本与开发记录均在仓库中。

## 6. 提交后

- [ ] 记录提交时间、站点 URL、commit hash；
- [ ] 保持站点在线，直到评审结束；
- [ ] 如修改网站内容，回到 Qoder Sites 再次点击「发布」（只保存不会更新线上）；
- [ ] 如评审反馈无法运行，优先检查：Python 版本、端口占用、运行时路径是否 ASCII、是否完成 `pip install -r requirements.txt`。
