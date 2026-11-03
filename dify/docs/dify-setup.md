# Dify 部署与导入说明

本作品验证环境：**Dify 0.15.3**（源码自托管）+ PostgreSQL 16 + Redis 7 + Python 3.12。Docker 自托管同样可用，只需把后端地址从 `127.0.0.1` 换成容器可达地址。

---

## 1. 启动后端

先按 [`../README.md`](../README.md) 的第 5 节把后端跑起来：

```bash
cd dify
bash scripts/setup.sh
bash scripts/init.sh
curl -s http://127.0.0.1:8787/health
```

确认：

```json
{
  "ok": true,
  "powercontext": {"url": "http://127.0.0.1:8766", "ready": true},
  "seekdb": {"ready": true, "version": "5.7.25-OceanBase seekdb-v1.4.0.0", "cards": 46}
}
```

---

## 2. 启动 Dify 0.15.3

### 2.1 Docker（推荐给评审）

在 `dify/docker` 下使用官方 0.15.3 的 `docker-compose.yaml`：

```bash
git clone --depth 1 --branch 0.15.3 https://github.com/langgenius/dify.git
cd dify/docker
cp .env.example .env
docker compose up -d
```

默认入口：

- Web：`http://127.0.0.1:3000`
- Console API：`http://127.0.0.1:5001`

首次打开 Web 会要求创建管理员账号。

> **Docker 访问宿主机后端**：容器里的 `127.0.0.1` 指向容器自己。请使用 `dsl/grudge-inn.chatflow.docker.yml`（HTTP 节点已改为 `http://host.docker.internal:8787`），并把模型 endpoint 也设为 `http://host.docker.internal:8787/v1`。
>
> Linux 版 Docker 如果 `host.docker.internal` 不解析，在 Dify 的 compose 文件里给 `api` / `worker` 加：
>
> ```yaml
> extra_hosts:
>   - "host.docker.internal:host-gateway"
> ```
>
> 如果 Dify 配置了 `SSRF_PROXY_HTTP_URL`，需要让 `host.docker.internal` 走直连（在 `ssrf_proxy` 的 `NO_PROXY` 中加入 `host.docker.internal`），或把 `SSRF_PROXY_HTTP_URL` 留空后重启 API。

### 2.2 源码（本作品实际验证方式）

```bash
git clone --depth 1 --branch 0.15.3 https://github.com/langgenius/dify.git
cd dify/api
python3 -m venv .venv
source .venv/bin/activate
# 依赖以 Dify 0.15.3 的 poetry.lock 为准；本作品额外把 litellm 1.51.3
# 替换为仍可下载的 1.53.1（仅版本差异，接口兼容）
pip install poetry poetry-plugin-export
poetry export -f requirements.txt --without-hashes --only main -o /tmp/dify-requirements.txt
# 0.15.3 的 litellm 1.51.3 已从 PyPI 下架；1.53.1 接口兼容
sed -i 's/litellm==1.51.3/litellm==1.53.1/' /tmp/dify-requirements.txt
pip install -r /tmp/dify-requirements.txt
# 以下 tools/storage 组的包在启动时会被 import，但不在 main 组里
pip install cloudscraper duckduckgo-search 'matplotlib==3.8.2' 'contourpy==1.2.1' opendal
```

在 `api/.env` 中至少配置：

```dotenv
SECRET_KEY=replace-with-a-random-secret
CONSOLE_API_URL=http://127.0.0.1:5001
CONSOLE_WEB_URL=http://127.0.0.1:3000
SERVICE_API_URL=http://127.0.0.1:5001
APP_WEB_URL=http://127.0.0.1:3000
FILES_URL=http://127.0.0.1:5001

DB_USERNAME=dify
DB_PASSWORD=difypass
DB_HOST=127.0.0.1
DB_PORT=5432
DB_DATABASE=dify

REDIS_HOST=127.0.0.1
REDIS_PORT=6379
REDIS_PASSWORD=
CELERY_BROKER_URL=redis://127.0.0.1:6379/1

STORAGE_TYPE=local
STORAGE_LOCAL_PATH=storage
EDITION=SELF_HOSTED
DEPLOY_ENV=DEVELOPMENT
LOG_LEVEL=INFO
```

初始化数据库并启动 API：

```bash
flask db upgrade
flask run --host 0.0.0.0 --port 5001
```

健康检查：

```bash
curl -s http://127.0.0.1:5001/console/api/setup
# 未初始化时：{"step": "not_started"}
```

> 本作品未使用 Dify 的 Code 节点，因此不需要额外启动 `dify-sandbox`。HTTP Request、LLM、Answer 节点都是 Dify 内置能力。

---

## 3. 配置模型

### 3.1 默认：零 Key 的 `grudge-narrator`

1. 登录 Dify，进入 **设置 → 模型供应商**。
2. 选择 **OpenAI-API-compatible** → **添加模型**。
3. 填写：

| 字段 | 值 |
| --- | --- |
| Model Name | `grudge-narrator` |
| API Key | `grudge-local`（占位，后端不校验） |
| API endpoint URL | `http://127.0.0.1:8787/v1` |
| Completion mode | `chat` |
| Context size | `8192` |
| Max tokens | `500` |
| Function calling | Not Support |
| Stream function calling | Not Supported |

4. 保存。可以用 Dify 的“测试”按钮发一句，应该返回一段中文客栈场景。

### 3.2 换成真实大模型（推荐正式体验）

**Ollama**：

```bash
ollama pull qwen2.5:3b
ollama serve   # 默认 11434
```

Dify → 模型供应商 → **Ollama** → 添加模型：

- Model Name：`qwen2.5:3b`
- Base URL：`http://127.0.0.1:11434`（Docker 用 `http://host.docker.internal:11434`）
- Completion mode：`chat`
- Context size：`8192`
- Max tokens：`500`

然后打开 DSL 的 LLM 节点，把：

```yaml
provider: openai_api_compatible
name: grudge-narrator
```

改为：

```yaml
provider: ollama
name: qwen2.5:3b
```

**任意 OpenAI-compatible 模型**：同样在模型供应商里添加，endpoint 填服务地址，模型名填服务端模型 ID，再把 LLM 节点的 provider/name 改掉。

> Prompt 已经写好“只叙述、不改判定”的约束。换模型不需要改 Prompt，也不需要改后端。

---

## 4. 导入 DSL

### 4.1 Web 导入

1. Dify → **应用** → **导入 DSL**。
2. 选择 [`../dsl/grudge-inn.chatflow.yml`](../dsl/grudge-inn.chatflow.yml)（Docker 用 `grudge-inn.chatflow.docker.yml`）。
3. 应用模式应为 **Chatflow / Advanced Chat**；导入后检查 5 个节点：
   - 开始 · 报上名号
   - 1. 读记忆 + 检索江湖卡
   - 2. 说书人写场景
   - 3. 落账 + 写记忆
   - 4. 把这一页给你看
4. 点击 **发布**。
5. 在应用概览页确认开场白和 4 个建议问题已出现。

### 4.2 自动导入（本作品验证用）

后端启动、Dify 启动后：

```bash
python scripts/bootstrap_dify.py --dify http://127.0.0.1:5001
```

它会：

- 创建本地演示账号 `demo@grudge.local / GrudgeInn2026!`（仅本地，不是提交凭据）；
- 注册 `grudge-narrator` 自定义模型；
- 导入 DSL；
- 发布应用；
- 创建 API Key；
- 把 `app_id` 与 API Key 写入 `~/.local/share/grudge-inn/dify-app.json`。

如果 Dify 已经初始化过，脚本会直接登录，不会重复创建。

### 4.3 重新绑定地址

DSL 中默认后端地址是 `http://127.0.0.1:8787`。如果后端端口/主机变了：

- Web：打开两个 HTTP 节点，改 URL 与模型 endpoint；
- 或直接改 `scripts/build_dsl.py` 里的 URL，重新生成：

```bash
python scripts/build_dsl.py
```

---

## 5. 入口

### 5.1 Dify Web

应用发布后，在 Dify 应用页直接聊天。第一次会要求填写 **玩家名号（player_id）**：

- 同一个名号 = 同一个会被记仇的人；
- 换一个名号 = 全新玩家；
- 想演示“跨会话记忆”，开一个新会话，填同一个名号，然后说“我回来了”。

### 5.2 可选的沉浸式网页入口

```bash
# 需要已执行 bootstrap_dify.py
bash scripts/start_play.sh
# 打开 http://127.0.0.1:8790
```

这是本作品附带的一个小型页面，只通过 `POST /v1/chat-messages` 调 Dify，不直接访问 seekdb 或 PowerContext；API Key 保留在后端。它适合评审快速体验，也可以完全忽略，直接用 Dify 应用页或下面的 Service API。

### 5.3 Dify Service API

在应用页 **API 访问** 里创建 API Key，然后：

```bash
curl -s -X POST http://127.0.0.1:5001/v1/chat-messages \
  -H "Authorization: Bearer app-xxxxxxxx" \
  -H 'Content-Type: application/json' \
  -d '{
    "inputs": {"player_id": "demo-player"},
    "query": "我把阿福的鞋藏到房梁上",
    "response_mode": "blocking",
    "conversation_id": "",
    "user": "reviewer"
  }'
```

返回关键字段：

```json
{
  "event": "message",
  "conversation_id": "....",
  "answer": "……正文……\n\n---\n**第 1 回合 · 大堂** ..."
}
```

下一轮把 `conversation_id` 带上。新会话留空，但 `inputs.player_id` 保持 `demo-player`，即可看到跨会话记忆。

---

## 6. 常见问题

| 现象 | 原因 / 处理 |
| --- | --- |
| HTTP 节点 502 / connection refused | 后端没启动，或 Docker 里用了 `127.0.0.1`；改 `host.docker.internal` |
| LLM 节点报模型不存在 | 模型供应商里没添加 `grudge-narrator`，或名称写错 |
| 回答只有正文没有面板 | `commit` 节点失败，检查后端日志 `~/.local/share/grudge-inn/service.log` |
| 跨会话不记得 | `inputs.player_id` 不一致；PowerContext 的 scope 是按 name 隔离的 |
| 后端报 seekdb “Server has gone away” | 空闲连接被回收，服务会自动重连；若仍失败，`bash scripts/stop.sh && bash scripts/init.sh` |
| Dify Docker 里 `host.docker.internal` 不通 | Linux 给 api/worker 加 `extra_hosts: host-gateway` |
