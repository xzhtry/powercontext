# Qoder 接下来 4 步（照着做）

> 工作目录：`D:\oceanbase大赛\eco-work\qoder`
>
> 应用已恢复并运行在 <http://127.0.0.1:18890>；`seekdb` 用 `18884`，PowerContext 用 `18767`。
> 如果它停了，先在该目录启动：
>
> ```powershell
> $env:RT_RUNTIME="C:\ob\eco-work\qoder\runtime"
> $env:RT_SEEKDB_PORT="18884"
> $env:RT_PC_PORT="18767"
> $env:RT_PORT="18890"
> .\.venv\Scripts\python.exe -m app
> ```
>
> 验收命令：
>
> ```powershell
> .\.venv\Scripts\python.exe scripts\verify.py --base-url http://127.0.0.1:18890
> ```

## 先截一张“现在能跑”的证据（2 分钟）

```powershell
curl.exe -s http://127.0.0.1:18890/api/health
```

期望看到：

```json
{"seekdb":true,"powercontext":true,"papers":508,"memory_available":true}
```

打开 <http://127.0.0.1:18890>，截一张今日研究台。命名：

```
qoder-01-run.png
```

## 会话 1：让 Qoder 读懂并跑通（5–10 分钟）

在 Qoder 中打开 `eco-work/qoder`，粘贴：

```text
你是这个仓库的开发者。请先不要改代码：
1. 阅读 README.md、docs/architecture.md、app/main.py、app/seekdb.py、app/memory.py，说明项目如何同时使用 seekdb 和 PowerContext；
2. 按 README 启动（本机用 RT_RUNTIME=C:\ob\eco-work\qoder\runtime，RT_PORT=18890，RT_SEEKDB_PORT=18884，RT_PC_PORT=18767）；
3. 访问 http://127.0.0.1:18890/api/health 和 /api/bootstrap，贴出 papers、evidence、memory 数量；
4. 如果启动失败，定位根因（端口、路径、依赖、权限），修复后重新验证；不要用假数据绕过。
验收：/api/health 中 seekdb=true、memory_available=true、papers>=500。
保留关键命令、失败与修复过程，我要用于 Qoder 开发记录。
```

截图：

```
qoder-01-prompt.png
qoder-01-health.png
qoder-01-today.png
```

## 会话 2：新增“综述 v2”模板（30–45 分钟，必做）

这是**当前代码没有的功能**，Qoder 需要实际改 3 个文件。

粘贴：

```text
请在 app/synthesis.py 新增 review_v2 模板，并在综述台增加选项。
要求：
- 结构固定为：背景 / 方法 / 结果 / 局限 / 研究空白；
- 仍然使用证据表的 note 与论文元数据，不调用外部模型；
- 引用编号 [n] 与参考列表一一对应，编号按“支持→挑战→混合→年份倒序”；
- 没有证据时返回明确提示，不生成空引用；
- 在 app/main.py 的 SynthesisIn 中允许 template="review_v2"；
- 在 app/static/app.js 的模板选项里加“综述 v2（背景-方法-结果-局限-空白）”；
- 补一个纯函数测试，断言 5 个二级标题和参考条数。
完成后运行 pytest 和 .\.venv\Scripts\python.exe scripts\verify.py --base-url http://127.0.0.1:18890，
然后在页面生成一次 review_v2，贴出 5 个标题和截图。
```

验收：

- `pytest` 全绿；
- `verify.py` 全 PASS；
- 页面能选“综述 v2”，生成结果含 5 个二级标题；
- 参考列表条数 = 选中证据数。

截图：

```
qoder-02-prompt.png
qoder-02-diff.png
qoder-02-review-v2.png
qoder-02-verify.png
```

## 会话 3：BibTeX 导出（30 分钟，推荐）

这也是**当前没有的功能**，能体现完整的“接口 + UI + 测试”能力。

粘贴：

```text
请为证据表增加 BibTeX 导出：
- 新接口 GET /api/export/evidence.bib；
- 每条证据输出 @article{...}，字段包含 title、author、year、journal/booktitle、url、note；
- 正确处理 & % _ # 等 LaTeX 特殊字符和中文；
- 在证据表工具栏增加“BibTeX”下载按钮；
- 补测试：生成内容包含与证据数量相同的 @article 条目，特殊字符不破坏语法。
完成后运行 pytest 和 .\.venv\Scripts\python.exe scripts\verify.py --base-url http://127.0.0.1:18890，
下载一次 .bib，贴出前 20 行和测试输出。
```

验收：

- 下载的 `.bib` 条目数 = 证据数；
- 特殊字符（`& % _ #`）被正确转义；
- `verify.py` 仍全 PASS。

截图：

```
qoder-03-prompt.png
qoder-03-bib.png
qoder-03-verify.png
```

## 会话 4：Qoder Sites 发布（15 分钟，必做）

1. 在 Qoder 中打开 `eco-work/qoder/site`；
2. 用 Qoder Sites 创建站点，可见范围设为「任何人都可访问」；
3. 发布后用**无痕窗口**打开，确认首页、5 张截图、代码块、运行命令、GitHub 链接都正常；
4. 记录完整 URL。

截图：

```
qoder-04-sites-publish.png
qoder-04-sites-incognito.png
```

> 网站里的 GitHub 链接目前是 `xzhtry/powercontext/tree/2026-competition-ecosystem/qoder`；如果实际仓库不同，先改 `site/index.html` 再发布。

## 最后 10 分钟：填记录、提交、推送

1. 把 Qoder 账号 UID、上述截图、每个会话的 prompt/修改文件/验证输出填进：

   [`docs/qoder-development-log.md`](qoder-development-log.md)

2. 把站点 URL 填进：

   [`docs/submission-checklist.md`](submission-checklist.md)

3. 提交并推送：

   ```powershell
   cd D:\oceanbase大赛\eco-work
   git add qoder
   git commit -m "feat(qoder): complete Qoder track submission"
   git push origin 2026-competition-ecosystem
   ```

4. 提交前用无痕窗口再打开一次站点，确认未登录可访问。

## 不要做

- 不要只让 Qoder 写 README 或解释代码——评委要看实际修改和验证；
- 不要把已有功能说成新功能；会话 2/3 是当前确实没有的；
- 不要伪造截图、UID 或站点归属；
- 不要提交真实 API Key/密码。
