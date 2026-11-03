# 运行证据

本目录来自本机实际运行（WSL2 Ubuntu 24.04 + Dify 0.15.3 + seekdb + PowerContext），不是手工编写的样例。

| 文件 | 说明 |
| --- | --- |
| `dify-run.md` | Dify 端连续三回合 + 跨会话同玩家 + 新玩家的完整回答（人读版） |
| `dify-run.json` | 同上，机器可读；含 `app_id`、`conversation_id`、PowerContext state、seekdb stats；**不含 API Key** |
| `dify-model.txt` | Dify 中已注册并验证的 `grudge-narrator` 自定义模型 |
| `dify-nodes.txt` | `workflow_node_executions` 中 Start / HTTP prepare / LLM / HTTP commit / Answer 的执行状态 |
| `play-ui.png` | 可选网页入口的实际截图（一次“藏鞋”回合后的界面） |
| `live-verification.json` | 后端验收：health、reset、三回合、PowerContext state、seekdb 卡片与流水 |

复核方式：

```bash
# 后端
python scripts/verify_live.py

# Dify 端（需要 Dify + 后端都在跑，且已执行 bootstrap）
python scripts/dify_scenario.py

# Dify 节点执行记录（需要 PostgreSQL 与 psql）
bash scripts/collect_dify_nodes.sh
```

说明：

- `dify-run.json` 里的 `app_id` 是本地 Dify 生成的 UUID，不是凭据。
- 所有 API Key、数据库密码都只在运行态文件/环境变量中，不写入本目录。
- 证据中的“第 N 回合”对应 PowerContext 的持久化状态；不同次运行因为 reset/时间不同会有差异，这是正常的。
