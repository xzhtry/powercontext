# 示例文献库说明

## 来源

`papers.json` 是公开 **arXiv API** 的元数据快照，用于让研脉在没有外部模型、没有网络的情况下也能完整演示“检索 → 判断 → 综述”的闭环。

抓取时间：2026-11-05（Asia/Shanghai）。

查询分组：

| 分组 | arXiv 查询 | 可用条目 |
| --- | --- | ---: |
| RAG | `all:"retrieval augmented generation"` | 97 |
| LLM Agent | `all:"large language model" AND all:"agent"` | 100 |
| 幻觉与事实性 | `all:"hallucination" AND all:"language model"` | 97 |
| AI for Science | `all:"scientific discovery" AND all:"language model"` | 100 |
| 文献综述自动化 | `all:"literature review" AND all:"large language model"` | 100 |
| 经典与评测基准 | 按 arXiv ID 定向抓取（Lewis 2020、Self-RAG、Lost in the Middle、RGB、RAGTruth 等 14 篇） | 14 |

去重后共 **508 篇**。

每条记录包含：`arxiv_id`、`title`、`abstract`、`authors`、`pub_year`、`venue`、`topic`、`categories`、`url`、`doi`、`open_access`、`source`、`query_group`。

## 许可与使用

- arXiv API 返回的元数据用于检索演示；**论文标题与摘要的版权归原作者所有**。
- 本项目不存储 PDF 全文，不重新分发论文；UI 与综述参考列表都指向 `https://arxiv.org/abs/<id>`。
- 复用/再分发时请保留本说明，并遵守 [arXiv API 使用条款](https://info.arxiv.org/help/api/tou.html) 与各论文的许可。
- 示例 brief 与 9 条证据判断（`demo.json`）是为演示而写的中文研究笔记，不是论文原文；提交前请按摘要逐条核对。

## 重建

需要网络与已安装依赖：

```powershell
.\.venv\Scripts\python.exe scripts\fetch_arxiv.py
.\.venv\Scripts\python.exe scripts\build_dataset.py
```

`fetch_arxiv.py` 会以约 3 秒间隔请求 arXiv API，写入 `data/raw/*.xml`；`build_dataset.py` 解析、去重、按年份排序，生成 `papers.json`。`data/raw/` 默认不提交（见根目录 `.gitignore`），`papers.json` 随仓库提交以保证离线可运行。

## 已知偏差

- 只保留摘要长度 ≥ 250 字符的条目；非常短的摘要被丢弃。
- `pub_year` 取 arXiv `published` 的年份；`venue` 优先使用 `journal_ref`，否则显示“arXiv 预印本”。
- `topic` 由首个 arXiv 分类映射为中文主题，不等同于论文的完整学科分类。
- 引用次数未抓取，固定为 0，UI 不使用该字段排序。
- “经典与评测基准”是按 ID 定向抓取的 14 篇，不随查询热度变化；这是为了保证示例证据可复现。
