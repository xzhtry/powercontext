# MiniMax 网页版响应

把 MiniMax（网页版或客户端）返回的完整回复保存为 `response.md`，要求包含：

````text
```diff
--- a/src/invoicehub/service.py
+++ b/src/invoicehub/service.py
...
```
````

然后执行：

```bash
bash scripts/apply_web_response.sh evidence/minimax/response.md "MiniMax-M3.1-Flash"
```

脚本会：导入修改前代码 → 应用补丁 → 运行 7 个目标测试 / 17 个回归测试 / 24 个全量测试 →
写回 `demo_app/src` → 重新导入 seekdb → 生成 `docs/minimax-dev-record.md` →
重跑状态复用演示。

如果只想先检查补丁、不写回代码：

```bash
python -m sddctx.cli run --response evidence/minimax/response.md
```
