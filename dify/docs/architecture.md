# 技术说明：Dify × seekdb × PowerContext

## 1. 一张图

```
玩家（Dify Chat / API）
        │  sys.query + start.player_id
        ▼
┌────────────────────────────────────────────────────────────┐
│ Dify Chatflow 0.15.3                                       │
│                                                            │
│  Start ──► HTTP prepare ──► LLM 说书人 ──► HTTP commit ──► Answer
│              │                                  │          │
│              │ 场景简报                          │ Markdown  │
└──────────────┼──────────────────────────────────┼──────────┘
               ▼                                  ▼
┌──────────────────────────────┐   ┌──────────────────────────┐
│ 客栈后端 127.0.0.1:8787      │   │ 客栈后端（同一进程）      │
│ - 读 PowerContext 状态/记忆   │   │ - 应用判定、落账          │
│ - seekdb 全文检索世界卡       │   │ - 写 PowerContext 记忆    │
│ - 生成“已判定事实”场景简报    │   │ - 返回最终 Markdown       │
└───────┬──────────────┬───────┘   └───────────┬──────────────┘
        │              │                       │
        ▼              ▼                       ▼
   PowerContext     seekdb                 PowerContext
   :8766            ~/.local/share/         （state + episode）
   Scope / entries   grudge-inn/seekdb
```

## 2. 为什么这样分工

### Dify：流程编排

Dify 承担“应用”的部分，而不是把逻辑全部塞进一个大 Prompt：

- `Start` 收集稳定的 `player_id`，这是跨会话记忆的锚点；
- `HTTP prepare` 调后端，取得本回合的**场景简报**（已经判定好的成败、数值、素材、前情）；
- `LLM` 节点把简报写成 120–220 字中文场景；模型只负责“叙述”，不负责“改规则”；
- `HTTP commit` 把叙述交回后端，后端落账、写 PowerContext，返回完整 Markdown；
- `Answer` 直接输出最终 Markdown。

这样做的好处：

- 模型输出不会破坏数值和成败，验收可复现；
- Dify 的画布能清楚看到输入、检索、模型、落账、输出五段；
- 换模型只改 LLM 节点，不需要改业务逻辑。

### seekdb：世界数据 + 检索

`inn_cards` 有 46 行，字段包括 `card_id / kind / title / body / tags / keywords / effect_json`。启动时创建：

```sql
CREATE FULLTEXT INDEX ft_inn_cards
ON inn_cards(title, body, keywords)
WITH PARSER ngram;
```

`/v1/turn/prepare` 会把玩家行动、意图、目标拼成查询，执行 `MATCH ... AGAINST`，再按目标标签、卡牌类型、行动关键词重排，取前 3 张进入场景简报。比如：

- “我把阿福的鞋藏到房梁上” → `阿福的破鞋`、`阿福的菜刀`、`后院那只不下蛋的芦花鸡`
- “偷偷翻开柜台的账本” → `柳三娘的油账本`、`柜台上的旧算盘`、`柳三娘的银簪`
- “给柳三娘送一碟桂花糕” → `柳三娘的桂花糕`、`灶王爷的供糖`、`帮工一天`

此外：

- `inn_plans` 保存“先判定、后叙述”的判定快照，保证 LLM 失败/重复提交时不会重复扣数值；
- `inn_ledger` 保存真实操作流水，`/v1/ledger` 和 `/v1/stats` 可核对。

### PowerContext：跨会话记忆

每个 `player_id` 对应一个 PowerContext Scope（`idempotency_key=grudge-inn-{player_id}`）。每回合写两类 entry：

```json
{
  "kind": "inn-state",
  "text": "GRUDGE_INN_STATE_V1\n{...回合、属性、NPC 态度、称号...}"
}
```

```json
{
  "kind": "inn-episode",
  "text": "GRUDGE_INN_EPISODE_V1\n{...行动、意图、目标、结果、数值、卡牌...}"
}
```

下一回合（以及新会话）通过 `/v1/memory/entries/list` 读出：

- generation 最大的 state；
- 同 generation 内 turn 最大的 state；
- 最近 6 条 episode，取最后 3 条写进场景简报的【前情记忆】。

`/reset` 不删除旧记忆，而是把 generation +1，从新的一代重新开始。这样既能保留审计痕迹，又不会让旧局污染新局。

## 3. 判定规则（节选）

| 意图 | 触发例 | 基础效果 |
| --- | --- | --- |
| `prank` | 藏、换、涂、吓、塞 | 混乱↑，目标记仇↑，可能被当场发现 |
| `theft` | 偷、顺、摸、翻账 | 银子↑，目标记仇↑，被抓住时名声↓ |
| `fight` | 砸、烧、踢、掀 | 混乱↑↑，记仇↑↑，名声↓ |
| `help` | 帮、修、打扫、请客 | 好感↑，目标好感↑，可能花银子 |
| `apologize` | 道歉、赔罪、认错 | 记仇↓，好感↑，名声↑ |
| `compliment` | 夸、赞、敬 | 好感↑，目标好感↑ |
| `probe` | 问、打听、观察 | 通常不改变数值，可能翻出传闻 |

判定使用 `sha256(player_id|generation|turn|action)` 生成固定骰子，因此同一玩家、同一回合、同一行动的结果可复现。严重度、目标、卡牌效果会修正成功率和数值。

## 4. 模型端点

`app/narrator.py` 实现了一个 OpenAI Chat Completions 兼容端点：

- `GET /v1/models` 返回 `grudge-narrator`；
- `POST /v1/chat/completions` 支持 `stream=false` 与 SSE `stream=true`；
- 从 Dify 发来的 system/user prompt 中解析【本回合场景简报】，生成 120–220 字中文场景。

它的定位是“零 Key 也能验收的叙事模型”，不是要替代大模型。要获得更好的文风，把 Dify LLM 节点改成 Ollama/Qwen 或任意 OpenAI-compatible 模型即可；Prompt 已按“只叙述、不改判定”设计。

## 5. 失败与边界

- PowerContext 不可用：`/v1/turn/prepare` 返回 503，Dify HTTP 节点会显示错误；不会静默丢记忆。
- seekdb 空闲连接被回收：`Store.ensure_alive()` 会重连，必要时重开内嵌实例。
- LLM 输出为空 / JSON / 代码块：`commit` 会清洗；若清洗后为空则报 400，不会写入空记忆。
- 重复提交：`inn_plans.committed` + 已保存的 `reply_markdown` 保证幂等。
- 回合错位：如果新回合已经推进，旧 plan 会被丢弃并提示重发，避免错账。
