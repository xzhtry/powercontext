"""Deterministic evidence synthesis.

The first version deliberately does not call an external model: the outline is
built from the user's evidence table and notes, so every sentence can be traced
to a paper and the demo runs offline.  An LLM can be added later as an optional
polishing step without changing the citation contract.
"""

from __future__ import annotations

from collections import Counter
from typing import Any

STANCE_LABELS = {"support": "支持", "challenge": "挑战", "mixed": "混合"}
TEMPLATE_LABELS = {
    "review": "文献综述提纲",
    "weekly": "组会周报",
    "review_v2": "综述 v2（背景-方法-结果-局限-空白）",
}


def _cite(evidence: list[dict[str, Any]]) -> dict[int, int]:
    return {int(item["evidence_id"]): index + 1 for index, item in enumerate(evidence)}


def _paper_line(item: dict[str, Any]) -> str:
    authors = item.get("authors") or "作者信息缺失"
    if len(authors) > 90:
        authors = authors[:90] + "…"
    return f"{authors} ({item.get('year', 'n.d.')}). {item['title']}. {item.get('venue', 'arXiv')}."


def _one_sentence(brief: dict[str, Any], counts: Counter) -> str:
    support = counts.get("support", 0)
    challenge = counts.get("challenge", 0)
    mixed = counts.get("mixed", 0)
    question = brief.get("question", "这个研究问题")
    if support == 0 and challenge == 0:
        return f"还没有足够的证据判断「{question}」；先建立证据表，再下结论。"
    if support > challenge:
        return (
            f"现有证据总体支持「{question}」的温和版本：RAG 能提升知识密集型任务的表现，"
            "但支持与挑战证据使用的是不同任务和指标，不能简单相加。"
        )
    if challenge > support:
        return (
            f"现有证据不支持「{question}」的强版本。更准确的结论是：RAG 能改善部分任务，"
            "但检索质量、证据位置与模型自检能力会显著限制收益，幻觉不能被消除。"
        )
    return (
        f"证据在「{question}」上呈分歧：支持与挑战各 {support} 条，"
        f"另有 {mixed} 条框架性/混合证据。结论应写成带条件的判断，而不是二选一。"
    )


def _gaps(evidence: list[dict[str, Any]], counts: Counter) -> list[str]:
    gaps = [
        "支持与挑战证据使用的任务、数据集和指标不同，当前证据表适合做方向判断，不适合做效应量合并。",
        "多数评测集中在英文问答/对话；跨领域长文档、真实科研工作流和中文场景仍缺少统一基准。",
        "检索质量与证据位置是反复出现的失效点：需要单独记录检索策略、top-k、上下文位置和拒答设置。",
    ]
    if counts.get("challenge", 0) >= 3:
        gaps.append("挑战证据已经形成一组，但还缺少能解释“在什么条件下 RAG 更可靠”的调节变量研究。")
    if not any("survey" in (item.get("title", "").lower()) for item in evidence):
        gaps.append("框架性综述不足，建议补一篇 RAG 架构/评测综述来固定术语与分类。")
    return gaps


def _review(brief: dict[str, Any], evidence: list[dict[str, Any]]) -> tuple[str, str]:
    counts = Counter(item["stance"] for item in evidence)
    citations = _cite(evidence)
    question = brief.get("question", "未命名研究问题")
    title = f"证据综述：{question}"
    lines = [
        f"# {title}",
        "",
        f"> 研究问题：{question}",
        f"> 证据规模：{len(evidence)} 条（支持 {counts.get('support', 0)} · 挑战 {counts.get('challenge', 0)} · 混合 {counts.get('mixed', 0)}）",
        f"> 研究阶段：{brief.get('stage', '证据筛选')} · 生成方式：规则模板（未调用外部模型）",
        "",
        "## 0. 一句话结论",
        "",
        _one_sentence(brief, counts),
        "",
        "## 1. 研究范围与筛选标准",
        "",
        brief.get("scope", "尚未填写研究范围。"),
        "",
        "纳入标准：",
    ]
    for criterion in brief.get("criteria", []) or ["尚未填写"]:
        lines.append(f"- {criterion}")
    lines.extend(["", "## 2. 证据分布", ""])
    if evidence:
        years = [item.get("year") for item in evidence if item.get("year")]
        year_text = f"{min(years)}–{max(years)}" if years else "年份缺失"
        lines.append(f"- 时间跨度：{year_text}")
        topics = Counter(item.get("topic", "未分类") for item in evidence)
        lines.append("- 主题分布：" + "；".join(f"{topic} {count}" for topic, count in topics.most_common()))
        lines.append(f"- 判断分布：支持 {counts.get('support', 0)} / 挑战 {counts.get('challenge', 0)} / 混合 {counts.get('mixed', 0)}")
    else:
        lines.append("证据表为空。")
    lines.extend(["", "## 3. 支持证据", ""])
    support_items = [item for item in evidence if item["stance"] == "support"]
    if support_items:
        for item in support_items:
            number = citations[int(item["evidence_id"])]
            lines.extend(
                [
                    f"### [{number}] {item['title']}",
                    "",
                    f"- 出处：{_paper_line(item)}",
                    f"- 我的判断：{item.get('note', '（未填写判断）')}",
                    f"- 链接：{item.get('url', '')}",
                    "",
                ]
            )
    else:
        lines.extend(["当前没有标记为“支持”的证据。", ""])
    lines.extend(["## 4. 挑战与限定", ""])
    challenge_items = [item for item in evidence if item["stance"] == "challenge"]
    if challenge_items:
        for item in challenge_items:
            number = citations[int(item["evidence_id"])]
            lines.extend(
                [
                    f"### [{number}] {item['title']}",
                    "",
                    f"- 出处：{_paper_line(item)}",
                    f"- 我的判断：{item.get('note', '（未填写判断）')}",
                    f"- 它限制了结论的哪一部分：见上方判断；引用时不要把单篇结论外推到所有 RAG 系统。",
                    f"- 链接：{item.get('url', '')}",
                    "",
                ]
            )
    else:
        lines.extend(["当前没有标记为“挑战”的证据；这通常意味着证据表还没筛完。", ""])
    mixed_items = [item for item in evidence if item["stance"] == "mixed"]
    if mixed_items:
        lines.extend(["## 5. 框架性与混合证据", ""])
        for item in mixed_items:
            number = citations[int(item["evidence_id"])]
            lines.append(
                f"- [{number}] {item['title']}（{item.get('year', 'n.d.')}）：{item.get('note', '')}"
            )
        lines.append("")
    lines.extend(["## 6. 矛盾点与研究空白", ""])
    for gap in _gaps(evidence, counts):
        lines.append(f"- {gap}")
    lines.extend(["", "## 7. 下一步行动", ""])
    next_action = brief.get("next_action") or "补一条与当前结论相反的证据，并记录检索条件。"
    lines.extend(
        [
            f"1. {next_action}",
            "2. 为每条证据补齐检索条件：查询词、top-k、语料版本、上下文位置。",
            "3. 把结论改写成可检验的条件句（在什么任务、什么检索质量下成立）。",
            "",
            "## 参考",
            "",
        ]
    )
    for item in evidence:
        number = citations[int(item["evidence_id"])]
        lines.append(f"[{number}] {_paper_line(item)} {item.get('url', '')}")
    lines.extend(
        [
            "",
            "---",
            "生成说明：本稿由研脉的规则模板根据证据表生成，未调用外部大模型；"
            "引用编号与参考列表一一对应，请在提交前逐条核对摘要原文。",
        ]
    )
    return title, "\n".join(lines)


def _review_v2(brief: dict[str, Any], evidence: list[dict[str, Any]]) -> tuple[str, str]:
    """Structured review: 背景 / 方法 / 结果 / 局限 / 研究空白.

    Every citation number [n] maps to exactly one reference-list entry.
    When the evidence table is empty, the function returns a clear notice
    instead of producing empty sections with dangling citation markers.
    """
    counts = Counter(item["stance"] for item in evidence)
    citations = _cite(evidence)
    question = brief.get("question", "未命名研究问题")
    title = f"结构化综述：{question}"

    if not evidence:
        markdown = "\n".join(
            [
                f"# {title}",
                "",
                f"> 研究问题：{question}",
                "> 证据规模：0 条",
                "",
                "## 1. 背景",
                "",
                f"当前研究问题为「{question}」，但证据表尚为空，无法生成有引用的综述。",
                "",
                "## 2. 方法",
                "",
                "请先在证据表中纳入论文判断，再重新生成。",
                "",
                "## 3. 结果",
                "",
                "（无证据，暂无结果可报告。）",
                "",
                "## 4. 局限",
                "",
                "- 没有证据支撑，任何结论都只是假设。",
                "",
                "## 5. 研究空白",
                "",
                "- 证据表为空——首先需要建立基础文献覆盖。",
                "",
                "## 参考",
                "",
                "（无引用条目。）",
                "",
                "---",
                "生成说明：本稿由研脉的规则模板根据证据表生成，未调用外部大模型。",
            ]
        )
        return title, markdown

    support_items = [item for item in evidence if item["stance"] == "support"]
    challenge_items = [item for item in evidence if item["stance"] == "challenge"]
    mixed_items = [item for item in evidence if item["stance"] == "mixed"]

    years = [item.get("year") for item in evidence if item.get("year")]
    year_text = f"{min(years)}–{max(years)}" if years else "年份缺失"
    topics = Counter(item.get("topic", "未分类") for item in evidence)

    lines: list[str] = [
        f"# {title}",
        "",
        f"> 研究问题：{question}",
        f"> 证据规模：{len(evidence)} 条（支持 {counts.get('support', 0)} · "
        f"挑战 {counts.get('challenge', 0)} · 混合 {counts.get('mixed', 0)}）",
        f"> 时间跨度：{year_text} · 生成方式：规则模板（未调用外部模型）",
        "",
        "## 1. 背景",
        "",
        f"本综述围绕「{question}」展开。",
        "",
    ]
    scope = brief.get("scope", "")
    if scope:
        lines.append(f"研究范围：{scope}")
        lines.append("")
    lines.extend(["纳入标准："])
    for criterion in brief.get("criteria", []) or ["尚未填写"]:
        lines.append(f"- {criterion}")
    lines.extend(
        [
            "",
            f"时间跨度 {year_text}，主题覆盖："
            + "、".join(f"{t}({c})" for t, c in topics.most_common()),
            "",
            "## 2. 方法",
            "",
            "证据来源为 seekdb 文献库中经人工判断后纳入的论文。",
            "每条证据记录 stance（支持 / 挑战 / 混合）与一句话判断（note），",
            "引用编号按「支持→挑战→混合→年份倒序」排列，与参考列表一一对应。",
            "",
            "判断分布：",
            f"- 支持 {counts.get('support', 0)} 条",
            f"- 挑战 {counts.get('challenge', 0)} 条",
            f"- 混合 {counts.get('mixed', 0)} 条",
            "",
            "## 3. 结果",
            "",
        ]
    )

    if support_items:
        lines.append("### 3.1 支持证据")
        lines.append("")
        for item in support_items:
            number = citations[int(item["evidence_id"])]
            lines.append(
                f"- [{number}] {item['title']}（{item.get('year', 'n.d.')}）："
                f"{item.get('note', '（未填写判断）')}"
            )
        lines.append("")

    if challenge_items:
        lines.append("### 3.2 挑战证据")
        lines.append("")
        for item in challenge_items:
            number = citations[int(item["evidence_id"])]
            lines.append(
                f"- [{number}] {item['title']}（{item.get('year', 'n.d.')}）："
                f"{item.get('note', '（未填写判断）')}"
            )
        lines.append("")

    if mixed_items:
        lines.append("### 3.3 混合 / 框架性证据")
        lines.append("")
        for item in mixed_items:
            number = citations[int(item["evidence_id"])]
            lines.append(
                f"- [{number}] {item['title']}（{item.get('year', 'n.d.')}）："
                f"{item.get('note', '（未填写判断）')}"
            )
        lines.append("")

    if not support_items and not challenge_items and not mixed_items:
        lines.append("（证据表有记录但无有效 stance 条目。）")
        lines.append("")

    lines.extend(
        [
            "## 4. 局限",
            "",
        ]
    )
    if counts.get("support", 0) > 0 and counts.get("challenge", 0) > 0:
        lines.append(
            "- 支持与挑战证据使用的任务、数据集和指标可能不同，"
            "当前证据表适合做方向判断，不适合做效应量合并。"
        )
    if len(evidence) < 5:
        lines.append(f"- 证据仅 {len(evidence)} 条，样本量偏小，结论稳定性待验证。")
    topics_list = list(topics.keys())
    if len(topics_list) <= 1:
        lines.append("- 主题覆盖单一，跨领域泛化性尚未得到证据支撑。")
    lines.append(
        "- 所有判断来自人工标注的 note，未使用外部模型润色，"
        "表述可能受研究者主观视角影响。"
    )
    lines.append("")

    lines.extend(["## 5. 研究空白", ""])
    for gap in _gaps(evidence, counts):
        lines.append(f"- {gap}")
    next_action = brief.get("next_action")
    if next_action:
        lines.append(f"- 下一步计划：{next_action}")
    lines.append("")

    lines.extend(["## 参考", ""])
    for item in evidence:
        number = citations[int(item["evidence_id"])]
        lines.append(f"[{number}] {_paper_line(item)} {item.get('url', '')}")
    lines.extend(
        [
            "",
            "---",
            "生成说明：本稿由研脉的规则模板根据证据表生成，未调用外部大模型；"
            "引用编号与参考列表一一对应，请在提交前逐条核对摘要原文。",
        ]
    )
    return title, "\n".join(lines)


def _weekly(brief: dict[str, Any], evidence: list[dict[str, Any]]) -> tuple[str, str]:
    counts = Counter(item["stance"] for item in evidence)
    citations = _cite(evidence)
    question = brief.get("question", "未命名研究问题")
    title = f"组会周报：{question}"
    lines = [
        f"# {title}",
        "",
        f"> 研究阶段：{brief.get('stage', '证据筛选')} · 证据 {len(evidence)} 条",
        "",
        "## 1. 本周在研究什么",
        "",
        question,
        "",
        brief.get("scope", ""),
        "",
        "## 2. 本周新增的判断",
        "",
    ]
    if evidence:
        for item in evidence:
            number = citations[int(item["evidence_id"])]
            label = STANCE_LABELS.get(item["stance"], item["stance"])
            lines.append(
                f"- [{number}]（{label}）{item['title']}：{item.get('note', '')}"
            )
    else:
        lines.append("- 本周还没有写入证据判断。")
    lines.extend(
        [
            "",
            "## 3. 需要组会讨论的分歧",
            "",
            f"- 支持 {counts.get('support', 0)} 条，挑战 {counts.get('challenge', 0)} 条，混合 {counts.get('mixed', 0)} 条。",
            "- 这些证据是否在回答同一个问题？任务、数据、指标是否可比？",
            "- 如果结论只在特定检索质量下成立，下一次实验应控制哪个变量？",
            "",
            "## 4. 下周计划",
            "",
            f"1. {brief.get('next_action') or '补一条反方证据，并记录检索条件。'}",
            "2. 选择 2 篇挑战证据，核对它们的实验设置是否适用于我们的研究问题。",
            "3. 把当前结论改写成条件句，作为下一轮检索的假设。",
            "",
            "## 参考",
            "",
        ]
    )
    for item in evidence:
        number = citations[int(item["evidence_id"])]
        lines.append(f"[{number}] {_paper_line(item)} {item.get('url', '')}")
    lines.append("")
    lines.append("---")
    lines.append("生成说明：规则模板根据证据表生成，未调用外部大模型；引用需逐条核对。")
    return title, "\n".join(lines)


def generate(
    brief: dict[str, Any],
    evidence: list[dict[str, Any]],
    template: str = "review",
) -> dict[str, Any]:
    stance_order = {"support": 0, "challenge": 1, "mixed": 2}
    evidence = sorted(
        list(evidence),
        key=lambda item: (
            stance_order.get(item.get("stance", ""), 9),
            -int(item.get("year") or 0),
        ),
    )
    if template == "weekly":
        title, markdown = _weekly(brief, evidence)
    elif template == "review_v2":
        title, markdown = _review_v2(brief, evidence)
    else:
        title, markdown = _review(brief, evidence)
    return {
        "template": template,
        "template_label": TEMPLATE_LABELS.get(template, template),
        "title": title,
        "markdown": markdown,
        "evidence_count": len(evidence),
        "counts": dict(Counter(item["stance"] for item in evidence)),
    }
