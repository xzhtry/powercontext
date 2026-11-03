# 验收样例与运行证据

本文件对应 `evidence/` 下的实际运行结果。评审可以按“初始状态 → 输入 → 预期 → 实际证据”顺序复现。

---

## 0. 初始状态

```bash
cd dify
bash scripts/setup.sh
bash scripts/init.sh
# 另开一个终端启动 Dify 0.15.3，并按 docs/dify-setup.md 导入 DSL、配置 grudge-narrator
```

健康检查应满足：

- `GET http://127.0.0.1:8787/health` → `powercontext.ready=true`、`seekdb.ready=true`、`cards=46`
- Dify 应用可打开，开场白显示“欢迎来到记仇客栈”
- Dify 的 LLM 节点模型为 `openai_api_compatible / grudge-narrator`（或你替换的 Ollama/OpenAI 模型）

---

## 1. 样例 A：连续三回合（同一会话）

**玩家 ID**：`dify-review`
**入口**：Dify 应用聊天框，或 `POST /v1/chat-messages`

| 顺序 | 输入 | 预期 |
| --- | --- | --- |
| 1 | `我把阿福的鞋藏到房梁上` | 意图=恶作剧，目标=阿福；正文出现“阿福的鞋/房梁/阿福”；seekdb 命中 `阿福的破鞋`；面板显示第 1 回合 |
| 2 | `给柳三娘送一碟桂花糕，顺便夸她年轻` | 意图=说好话/帮忙；正文出现桂花糕或柳三娘；必须回扣第 1 回合的鞋（前情记忆） |
| 3 | `我道歉，对不起，我不该整阿福` | 意图=道歉；记仇下降、好感上升；正文出现阿福或道歉；面板显示第 3 回合 |

实际回答见 [`../evidence/dify-run.md`](../evidence/dify-run.md) 的“连续三回合”。关键验证点：

- 第 1 回合正文包含“阿福的鞋”“房梁”“阿福”；
- 第 2 回合正文包含“他还记得，第1回合你把阿福的鞋藏到房梁上”；
- 第 3 回合面板中 `记仇` 从 18 降到 11，`好感` 从 26 升到 30；
- 每回合末尾都有 `本回合已写入 PowerContext`，并带 `inn-state` + `inn-episode` 与流水号。

---

## 2. 样例 B：跨会话记忆（核心验收）

### 2.1 同一玩家，新会话

1. 结束或离开样例 A 的会话。
2. 新建一个 Dify 会话（或 API 中 `conversation_id` 传空）。
3. **仍然填写 `player_id = dify-review`**。
4. 输入：`我回来了，柳三娘还记不记得我`

**预期**：回答里出现对第 1 回合“藏鞋”的回扣，而不是把玩家当陌生人。

**实际**（节选）：

> 他还记得，第1回合你把阿福的鞋藏到房梁上。

对应 `evidence/dify-run.md` 的“跨会话：同一玩家”。

### 2.2 新玩家，新会话

1. 新建会话。
2. 填写 `player_id = dify-fresh`。
3. 输入同样一句：`我回来了，柳三娘还记不记得我`

**预期**：不出现“藏鞋”等旧事；回答是初次见面的态度。

**实际**：`dify-fresh` 的回答中没有“鞋/第1回合”的旧事回扣，只有新一回合的客栈场景。

这组对照说明：记忆不是 Dify 单次会话的上下文，而是按 `player_id` 存在 PowerContext 里。

---

## 3. 技术作用核对

### 3.1 Dify 节点执行

Dify 的 `workflow_node_executions` 表可以核对 5 个节点都执行成功：

```bash
APP_ID=$(python3 -c 'import json,os;print(json.load(open(os.path.expanduser("~/.local/share/grudge-inn/dify-app.json")))["app_id"])')
PGPASSWORD=difypass psql -h 127.0.0.1 -U dify -d dify \
  -v app_id="$APP_ID" -f scripts/dify_nodes.sql
```

实际输出（节选）：

```
node_id |  node_type   |         title          |  status   | seconds
answer  | answer       | 4. 把这一页给你看      | succeeded | 0.014
commit  | http-request | 3. 落账 + 写记忆       | succeeded | 0.203
narrate | llm          | 2. 说书人写场景        | succeeded | 0.040
prepare | http-request | 1. 读记忆 + 检索江湖卡 | succeeded | 0.095
start   | start        | 开始 · 报上名号        | succeeded | 0.077
```

`prepare` 的输出是本回合的场景简报，`commit` 的输出是最终 Markdown，说明 Dify 确实在编排“读记忆/检索 → 模型 → 落账”。

### 3.2 seekdb

```bash
curl -s http://127.0.0.1:8787/v1/stats
```

关键字段：

```json
{
  "seekdb": {
    "engine": "seekdb (OceanBase embedded)",
    "version": "5.7.25-OceanBase seekdb-v1.4.0.0",
    "cards": 46,
    "card_kinds": {"event": 6, "npc": 6, "prop": 21, "remedy": 8, "rumor": 5},
    "plans": 17,
    "ledger": 13
  }
}
```

每次 `prepare` 的场景简报中“【可用素材】”就是 seekdb 全文检索的结果。例如藏鞋回合会列出 `阿福的破鞋`、`后院那只不下蛋的芦花鸡`、`阿福的菜刀`；道歉回合会列出 `一封没送出的道歉信`、`阿福的跌打酒` 等。

### 3.3 PowerContext

```bash
curl -s -X POST http://127.0.0.1:8787/v1/state \
  -H 'Content-Type: application/json' \
  -d '{"player_id":"dify-review"}'
```

关键字段：

```json
{
  "scope_id": "scp_...",
  "state": {
    "generation": 3,
    "turn": 4,
    "stats": {"favor": 39, "grudge": 11, "chaos": 3, "silver": 30, "reputation": 12}
  },
  "episodes": [ ... 4 条 ... ],
  "powercontext": {"entries": 10, "state_entries": 5, "episode_entries": 5}
}
```

`entries` 包含 `inn-state` 与 `inn-episode`，新会话通过 `entries/list` 读回；这就是“跨会话记忆”的实际来源。

---

## 4. 证据文件

| 文件 | 内容 |
| --- | --- |
| [`../evidence/dify-run.md`](../evidence/dify-run.md) | Dify 端三回合 + 跨会话同玩家/新玩家的完整回答 |
| [`../evidence/dify-run.json`](../evidence/dify-run.json) | 同上，机器可读；含 app_id、conversation_id、PowerContext 状态、seekdb 统计（不含 API Key） |
| [`../evidence/live-verification.json`](../evidence/live-verification.json) | 后端验收：health / reset / 三回合 / state / cards |
| `evidence/dify-model.txt` | Dify 中注册并验证的 `grudge-narrator` 模型 |
| `scripts/dify_nodes.sql` / `scripts/dify_model.sql` | 查询 Dify 节点/模型记录的 SQL |

---

## 5. 恢复初始状态

```bash
# 只重置演示玩家（旧记忆保留为上一代，不会污染新局）
bash scripts/reset.sh dify-review
bash scripts/reset.sh dify-fresh

# 或彻底清空本作品运行态
bash scripts/stop.sh
bash scripts/reset.sh --hard
bash scripts/init.sh
```

Dify 的会话可以在应用里新建；API 侧把 `conversation_id` 留空即可。

---

## 6. 已知现象与解释

- 第一回合可能成功，也可能被当场发现。这是 `sha256(player_id|generation|turn|action)` 固定骰子的结果，同一玩家/回合/行动可复现；失败同样是有效玩法，正文会写“露馅/被逮住”。
- 默认 `grudge-narrator` 是模板叙事，句子会重复使用少量开场意象；换成 Ollama/Qwen 或真实模型后文风会明显更自然。
- 面板里的“第 N 回合”来自持久化状态；状态命令（输入“看看状态”）不会推进回合，也不会写入新记忆。
- 阶段结局（江湖通缉 / 客栈自己人）是阶段提示，不强制结束对话；`/reset` 才会开启新的一代。
