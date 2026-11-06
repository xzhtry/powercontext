/* 研脉 ResearchThread — vanilla SPA */
(() => {
  "use strict";

  const $ = (selector, root = document) => root.querySelector(selector);
  const $$ = (selector, root = document) => Array.from(root.querySelectorAll(selector));

  const ICONS = {
    search: '<svg viewBox="0 0 24 24" fill="none"><circle cx="10.5" cy="10.5" r="6.5" stroke="currentColor" stroke-width="1.8"/><path d="m16 16 4.5 4.5" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/></svg>',
    plus: '<svg viewBox="0 0 24 24" fill="none"><path d="M12 5v14M5 12h14" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/></svg>',
    arrow: '<svg viewBox="0 0 24 24" fill="none"><path d="M5 12h14M13 6l6 6-6 6" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/></svg>',
    external: '<svg viewBox="0 0 24 24" fill="none"><path d="M14 5h5v5M19 5l-8 8" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/><path d="M19 14v5H5V5h5" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/></svg>',
    edit: '<svg viewBox="0 0 24 24" fill="none"><path d="m4 20 4.5-1 10-10-3.5-3.5-10 10L4 20Z" stroke="currentColor" stroke-width="1.7" stroke-linejoin="round"/><path d="m13.5 6.5 3.5 3.5" stroke="currentColor" stroke-width="1.7"/></svg>',
    trash: '<svg viewBox="0 0 24 24" fill="none"><path d="M4 7h16M9 7V4.5h6V7M7 7l1 13h8l1-13" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"/></svg>',
    copy: '<svg viewBox="0 0 24 24" fill="none"><rect x="8" y="8" width="11" height="12" rx="1.5" stroke="currentColor" stroke-width="1.7"/><path d="M16 8V5.5A1.5 1.5 0 0 0 14.5 4H5.5A1.5 1.5 0 0 0 4 5.5v10A1.5 1.5 0 0 0 5.5 17H8" stroke="currentColor" stroke-width="1.7"/></svg>',
    download: '<svg viewBox="0 0 24 24" fill="none"><path d="M12 4v11M7.5 11 12 15.5 16.5 11M5 19h14" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/></svg>',
    refresh: '<svg viewBox="0 0 24 24" fill="none"><path d="M19 12a7 7 0 1 1-2.05-4.95M19 4v5h-5" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/></svg>',
    close: '<svg viewBox="0 0 24 24" fill="none"><path d="m6 6 12 12M18 6 6 18" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/></svg>',
    spark: '<svg viewBox="0 0 24 24" fill="none"><path d="M12 3.5 13.7 9l5.3 1.7-5.3 1.7L12 18l-1.7-5.6L5 10.7 10.3 9 12 3.5Z" stroke="currentColor" stroke-width="1.5" stroke-linejoin="round"/><path d="M18.5 15.5 19.2 18l2.3.7-2.3.7-.7 2.1-.7-2.1-2.3-.7 2.3-.7.7-2.5Z" fill="currentColor"/></svg>',
    book: '<svg viewBox="0 0 24 24" fill="none"><path d="M4.5 5.5A2.5 2.5 0 0 1 7 3h12.5v16H7a2.5 2.5 0 0 0-2.5 2.5v-16Z" stroke="currentColor" stroke-width="1.6" stroke-linejoin="round"/><path d="M4.5 18.5A2.5 2.5 0 0 1 7 16h12.5" stroke="currentColor" stroke-width="1.6"/></svg>',
    scale: '<svg viewBox="0 0 24 24" fill="none"><path d="M12 4v16M7 20h10M4 8h16M7 8l-3 6h6L7 8ZM17 8l-3 6h6l-3-6Z" stroke="currentColor" stroke-width="1.5" stroke-linejoin="round"/></svg>',
    memory: '<svg viewBox="0 0 24 24" fill="none"><path d="M12 4.5a4 4 0 0 0-4 4v.6A3.4 3.4 0 0 0 7 15.4V16a4 4 0 0 0 5 3.8 4 4 0 0 0 5-3.8v-.6a3.4 3.4 0 0 0-1-6.3v-.6a4 4 0 0 0-4-4Z" stroke="currentColor" stroke-width="1.6" stroke-linejoin="round"/></svg>',
    filter: '<svg viewBox="0 0 24 24" fill="none"><path d="M4 6h16M7 12h10M10 18h4" stroke="currentColor" stroke-width="1.7" stroke-linecap="round"/></svg>',
  };

  const STANCE = {
    support: { label: "支持", cls: "support", color: "#6f8f72" },
    challenge: { label: "挑战", cls: "challenge", color: "#b85f42" },
    mixed: { label: "混合", cls: "mixed", color: "#c39a58" },
  };

  const KIND = {
    "research-brief": "研究问题",
    "evidence-decision": "证据判断",
    "session-summary": "会话交接",
    synthesis: "综述草稿",
    "next-action": "下一步",
  };

  const VIEW_META = {
    today: { kicker: "研究工作台", title: "今日研究台" },
    library: { kicker: "证据检索", title: "文献库" },
    evidence: { kicker: "判断与取舍", title: "证据表" },
    synthesis: { kicker: "从证据到初稿", title: "综述台" },
    memory: { kicker: "跨会话上下文", title: "研究记忆" },
  };

  const state = {
    boot: null,
    view: "today",
    search: {
      q: "RAG hallucination",
      results: null,
      loading: false,
      traceOpen: false,
      filters: { year_from: "", year_to: "", topic: "", open_access: false },
    },
    evidence: { items: [], counts: {}, loaded: false, loading: false, filter: "all" },
    memory: { data: null, loading: false, filter: "all" },
    synthesis: { template: "review", selected: null, result: null, loading: false, loadedLatest: false },
    fatal: null,
  };

  // --------------------------------------------------------------- utilities
  const esc = (value) =>
    String(value ?? "").replace(/[&<>"']/g, (char) => ({
      "&": "&amp;",
      "<": "&lt;",
      ">": "&gt;",
      '"': "&quot;",
      "'": "&#39;",
    }[char]));

  const asArray = (value) => (Array.isArray(value) ? value : []);
  const number = (value) => Number(value || 0).toLocaleString("zh-CN");

  function formatDate(value) {
    if (!value) return "—";
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) return value;
    return date.toLocaleString("zh-CN", {
      month: "numeric",
      day: "numeric",
      hour: "2-digit",
      minute: "2-digit",
    });
  }

  function formatDay(value) {
    if (!value) return "—";
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) return value;
    return date.toLocaleDateString("zh-CN", { year: "numeric", month: "long", day: "numeric" });
  }

  function todayLabel() {
    return new Date().toLocaleDateString("zh-CN", {
      year: "numeric",
      month: "long",
      day: "numeric",
      weekday: "long",
    });
  }

  function greeting() {
    const hour = new Date().getHours();
    if (hour < 6) return "夜深了";
    if (hour < 12) return "早上好";
    if (hour < 18) return "下午好";
    return "晚上好";
  }

  function stanceOf(value) {
    return STANCE[value] || { label: value || "未标记", cls: "mixed", color: "#c39a58" };
  }

  function kindLabel(value) {
    return KIND[value] || value || "记忆";
  }

  function toast(message, type = "ok") {
    const root = $("#toast-root");
    if (!root) return;
    const node = document.createElement("div");
    node.className = `toast ${type === "error" ? "error" : ""}`;
    node.innerHTML = `<span class="toast-mark">${type === "error" ? "!" : "✓"}</span><span>${esc(message)}</span>`;
    root.appendChild(node);
    setTimeout(() => {
      node.classList.add("is-leaving");
      setTimeout(() => node.remove(), 260);
    }, 3600);
  }

  async function api(path, options = {}) {
    const response = await fetch(path, {
      headers: { "Content-Type": "application/json", ...(options.headers || {}) },
      ...options,
    });
    const text = await response.text();
    let data = null;
    try {
      data = text ? JSON.parse(text) : null;
    } catch {
      data = { detail: text };
    }
    if (!response.ok) {
      const message = data?.detail || data?.error || `请求失败（HTTP ${response.status}）`;
      throw new Error(message);
    }
    return data;
  }

  // ------------------------------------------------------------------ chrome
  function updateChrome() {
    const boot = state.boot;
    if (!boot) return;
    const evidenceCount = boot.stats?.evidence ?? 0;
    const memoryCount = boot.memory?.total ?? 0;
    const navEvidence = $("#nav-evidence-count");
    const navMemory = $("#nav-memory-count");
    if (navEvidence) navEvidence.textContent = evidenceCount;
    if (navMemory) navMemory.textContent = memoryCount;

    const seekdbOk = boot.health?.seekdb === "ok";
    const pcOk = boot.health?.powercontext === "ok";
    setStatus("#seekdb-dot", "#seekdb-state", seekdbOk, seekdbOk ? "已连接" : "异常");
    setStatus("#pc-dot", "#pc-state", pcOk, pcOk ? "已连接" : "降级");
    setStatus("#memory-dot", "#memory-state", pcOk, pcOk ? "已连接" : "降级");

    const dateChip = $("#date-chip");
    if (dateChip) dateChip.textContent = todayLabel();

    const meta = VIEW_META[state.view] || VIEW_META.today;
    const kicker = $("#topbar-kicker");
    const title = $("#topbar-title");
    if (kicker) kicker.textContent = meta.kicker;
    if (title) title.textContent = meta.title;

    $$("[data-view]").forEach((link) => {
      link.classList.toggle("is-active", link.dataset.view === state.view);
    });
  }

  function setStatus(dotSelector, labelSelector, ok, label) {
    const dot = $(dotSelector);
    const text = $(labelSelector);
    if (dot) dot.className = `status-dot ${ok ? "ok" : "warn"}`;
    if (text) text.textContent = label;
  }

  function setView(view) {
    if (!VIEW_META[view]) view = "today";
    state.view = view;
    updateChrome();
  }

  function navigate(view) {
    const target = `#/${view}`;
    if (location.hash === target) {
      state.view = view;
      updateChrome();
      renderCurrent();
    } else {
      location.hash = target;
    }
  }

  function renderCurrent() {
    const view = $("#view");
    if (!view) return;
    if (state.fatal) {
      renderFatal();
      return;
    }
    if (!state.boot) return;
    window.scrollTo({ top: 0, behavior: "instant" });
    if (state.view === "today") renderToday();
    else if (state.view === "library") renderLibrary();
    else if (state.view === "evidence") renderEvidence();
    else if (state.view === "synthesis") renderSynthesis();
    else if (state.view === "memory") renderMemory();
    else renderToday();
  }

  function renderFatal() {
    const view = $("#view");
    if (!view) return;
    view.innerHTML = `
      <div class="empty-state" style="margin-top:12vh">
        <span class="empty-mark">${ICONS.spark}</span>
        <h4>研究台没有打开</h4>
        <p>${esc(state.fatal)}</p>
        <button class="btn btn-primary" data-action="retry-bootstrap">${ICONS.refresh} 重试连接</button>
      </div>`;
  }

  // ------------------------------------------------------------------- today
  function renderToday() {
    const boot = state.boot;
    const stats = boot.stats || {};
    const memory = boot.memory || {};
    const brief = boot.brief || {};
    const stanceCounts = stats.stances || {};
    const totalStance = (stanceCounts.support || 0) + (stanceCounts.challenge || 0) + (stanceCounts.mixed || 0);
    const pct = (value) => (totalStance ? Math.round((value / totalStance) * 100) : 0);
    const lastSession = memory.last_session;
    const recovered = asArray(memory.recovered);
    const nextAction = brief.next_action || lastSession?.payload?.next_action || "补一条与当前结论相反的证据，并记录检索条件。";

    const briefCard = `
      <section class="brief-card">
        <div class="brief-top">
          <div>
            <div class="brief-label"><span class="pill dark">研究 brief</span><span>${esc(brief.stage || "证据筛选")}</span></div>
            <h2 class="brief-question">${esc(brief.question || "还没有研究问题")}</h2>
            <p class="brief-scope">${esc(brief.scope || "写下你正在回答的问题，后面的检索和证据判断都会围绕它展开。")}</p>
          </div>
          <button class="icon-btn" type="button" data-action="edit-brief" aria-label="编辑研究问题">${ICONS.edit}</button>
        </div>
        <div class="brief-bottom">
          <div class="brief-meta">
            <span>${ICONS.book} ${esc(brief.owner || "研究者")}</span>
            <span>${esc(stats.papers || 0)} 篇文献</span>
            <span>${esc(stats.evidence || 0)} 条判断</span>
            <span>更新于 ${formatDate(brief.updated_at || memory.last_session?.created_at)}</span>
          </div>
          <div class="chip-row">
            ${asArray(brief.criteria).slice(0, 3).map((item) => `<span class="chip">${esc(item)}</span>`).join("")}
          </div>
        </div>
      </section>`;

    const statsGrid = `
      <div class="stats-grid">
        <div class="stat-card">
          <div class="stat-value">${number(stats.papers)}<small>篇</small></div>
          <div class="stat-label">seekdb 文献库</div>
          <div class="stat-note">全文检索 · ngram 索引</div>
        </div>
        <div class="stat-card">
          <div class="stat-value">${number(stats.evidence)}<small>条</small></div>
          <div class="stat-label">已写下的证据判断</div>
          <div class="stat-note">支持 ${stanceCounts.support || 0} · 挑战 ${stanceCounts.challenge || 0}</div>
        </div>
        <div class="stat-card">
          <div class="stat-value">${number(stats.searches)}<small>次</small></div>
          <div class="stat-label">本库累计检索</div>
          <div class="stat-note">每次检索都留有 SQL 轨迹</div>
        </div>
        <div class="stat-card">
          <div class="stat-value">${number(memory.total)}<small>条</small></div>
          <div class="stat-label">PowerContext 记忆</div>
          <div class="stat-note">${memory.available ? "跨会话可恢复" : "当前降级"}</div>
        </div>
      </div>`;

    const recap = lastSession
      ? `<section class="recap-card">
          <p class="eyebrow">上次停在这里 · PowerContext</p>
          <p class="recap-quote">“${esc(lastSession.summary || "上次的研究进度已保存。")}”</p>
          <div class="recap-meta">
            <span>记忆 <b>${number(memory.total)}</b> 条</span>
            <span>本次已恢复 <b>${recovered.length}</b> 条</span>
            <span>${formatDate(lastSession.created_at)}</span>
          </div>
          <div class="recap-actions">
            <button class="btn btn-secondary" type="button" data-action="continue-last">继续上次 ${ICONS.arrow}</button>
            <button class="btn btn-text" type="button" data-action="open-memory" style="color:#d7a26f">查看记忆</button>
          </div>
        </section>`
      : `<section class="recap-card">
          <p class="eyebrow">第一次打开 · 先定一个问题</p>
          <p class="recap-quote">“研究不是把论文读完，而是知道下一篇文章为什么值得读。”</p>
          <div class="recap-meta"><span>从一个具体问题开始，<b>PowerContext</b> 会记住你的筛选标准与判断。</span></div>
          <div class="recap-actions"><button class="btn btn-secondary" type="button" data-action="edit-brief">写下研究问题 ${ICONS.arrow}</button></div>
        </section>`;

    const balance = `<section class="panel balance">
      <div class="balance-head"><h3>证据天平</h3><span>${totalStance ? `${totalStance} 条已判断` : "尚未开始"}</span></div>
      <div class="balance-bar">
        <span class="balance-seg support" style="width:${pct(stanceCounts.support || 0)}%"></span>
        <span class="balance-seg challenge" style="width:${pct(stanceCounts.challenge || 0)}%"></span>
        <span class="balance-seg mixed" style="width:${pct(stanceCounts.mixed || 0)}%"></span>
      </div>
      <div class="balance-legend">
        <span><i class="legend-dot" style="background:#6f8f72"></i>支持 ${stanceCounts.support || 0}</span>
        <span><i class="legend-dot" style="background:#b85f42"></i>挑战 ${stanceCounts.challenge || 0}</span>
        <span><i class="legend-dot" style="background:#c39a58"></i>混合 ${stanceCounts.mixed || 0}</span>
      </div>
    </section>`;

    const nextSteps = `<section class="panel">
      <div class="panel-head"><div><h3>下一步，不用重新想</h3><p>这些动作来自你的研究 brief 与证据分布。</p></div></div>
      <div class="panel-body next-list">
        <div class="next-item"><span class="next-index">1</span><div><b>${esc(nextAction)}</b><p>带着一个具体的检索词回到文献库，找到后立刻写一句判断。</p><button class="btn btn-text" type="button" data-action="quick-search" data-q="RAG failure">去检索 ${ICONS.arrow}</button></div></div>
        <div class="next-item"><span class="next-index">2</span><div><b>检查挑战证据是否适用于你的问题</b><p>${stanceCounts.challenge || 0} 条挑战证据已记录。先核对任务、指标与检索设置，再决定是否外推。</p><button class="btn btn-text" type="button" data-action="open-evidence">打开证据表 ${ICONS.arrow}</button></div></div>
        <div class="next-item"><span class="next-index">3</span><div><b>把当前判断写成可检验的条件句</b><p>用综述台生成一版提纲，重点看“矛盾点与研究空白”是否具体。</p><button class="btn btn-text" type="button" data-action="open-synthesis">生成提纲 ${ICONS.arrow}</button></div></div>
      </div>
    </section>`;

    const activity = `<section class="panel">
      <div class="panel-head"><div><h3>最近发生</h3><p>seekdb 中的操作记录，同时也是可核对的运行轨迹。</p></div></div>
      <div class="panel-body activity-list">
        ${asArray(boot.activity).length
          ? asArray(boot.activity).slice(0, 7).map((item) => `
            <div class="activity-item">
              <span class="activity-dot"></span>
              <div class="activity-copy"><b>${esc(item.summary)}</b><span>${formatDate(item.created_at)}</span></div>
            </div>`).join("")
          : `<div class="empty-state" style="padding:24px"><p>还没有活动记录。去文献库检索一次，这里就会开始生长。</p></div>`}
      </div>
    </section>`;

    const quick = `<section class="panel">
      <div class="panel-head"><div><h3>从一个检索开始</h3><p>试试这些与示例研究问题相关的查询。</p></div></div>
      <div class="panel-body" style="display:flex;flex-direction:column;gap:7px">
        ${["RAG hallucination", "retrieval evaluation", "long context", "RAG survey"].map((q) => `<button class="btn btn-secondary" type="button" data-action="quick-search" data-q="${esc(q)}" style="justify-content:space-between">${esc(q)} ${ICONS.search}</button>`).join("")}
      </div>
    </section>`;

    $("#view").innerHTML = `
      <section class="hero">
        <div class="hero-copy">
          <p class="eyebrow">${todayLabel()} · ${greeting()}，研究者</p>
          <h2>把读过的论文，<br>接成<em>可复用</em>的脉络。</h2>
          <p>文献在 <b>seekdb</b> 里被检索，判断在证据表里被写下，研究问题与进度交给 <b>PowerContext</b> 记住。关掉页面，下次从断点继续。</p>
        </div>
        <aside class="hero-aside">
          <span class="stamp">研究原则</span>
          <p>“先写下为什么读它，<br>再决定要不要引用它。”</p>
          <small>研脉 · 本地优先的研究上下文工作台</small>
        </aside>
      </section>
      ${briefCard}
      ${statsGrid}
      <div class="today-grid">
        <div class="today-col">${recap}${balance}${nextSteps}</div>
        <div class="today-col">${activity}${quick}</div>
      </div>`;
  }

  // ----------------------------------------------------------------- library
  function renderLibrary() {
    const results = state.search.results;
    const loading = state.search.loading;
    const filters = state.search.filters;
    const topics = state.boot?.stats?.topics || [];
    const years = yearRange();

    if (!results && !loading) {
      doSearch(state.search.q);
      return;
    }

    const resultList = loading
      ? `<div class="paper-list">${[1, 2, 3].map(() => `<div class="paper-card"><div class="skeleton" style="height:17px;width:68%"></div><div class="skeleton" style="height:11px;width:40%;margin-top:10px"></div><div class="skeleton" style="height:10px;width:90%;margin-top:14px"></div><div class="skeleton" style="height:10px;width:78%;margin-top:7px"></div></div>`).join("")}</div>`
      : results && results.results.length
        ? `<div class="paper-list">${results.results.map((paper) => paperCard(paper)).join("")}</div>`
        : emptyState("没有找到匹配的文献", "换一个关键词，或放宽年份与主题筛选。也可以试试 “RAG hallucination”。", `<button class="btn btn-secondary" type="button" data-action="quick-search" data-q="RAG survey">试试 RAG survey</button>`);

    $("#view").innerHTML = `
      <div class="view-head">
        <div><p class="eyebrow">seekdb · 全文检索</p><h2>先找到，再判断。</h2><p>在 ${number(state.boot?.stats?.papers)} 篇 arXiv 摘要中检索；每次查询都会留下 SQL 轨迹，方便核对结果不是“编”的。</p></div>
        <div class="view-head-actions">
          <button class="btn btn-secondary" type="button" data-action="open-evidence">查看证据表 ${ICONS.arrow}</button>
        </div>
      </div>
      <section class="search-panel">
        <form class="search-form" id="search-form">
          <div class="search-box">
            ${ICONS.search}
            <input class="search-input" id="search-input" name="q" value="${esc(state.search.q)}" placeholder="输入关键词，例如 RAG hallucination / long context" autocomplete="off" spellcheck="false">
            <span class="search-kbd">↵ 检索</span>
            <button class="btn btn-primary search-submit" type="submit">检索</button>
          </div>
        </form>
        <div class="filter-row">
          <span class="subtle small" style="display:inline-flex;gap:6px;align-items:center">${ICONS.filter} 筛选</span>
          <label>年份
            <select class="filter-select" id="filter-year-from">
              <option value="">不限</option>
              ${years.map((year) => `<option value="${year}" ${String(filters.year_from) === String(year) ? "selected" : ""}>${year}</option>`).join("")}
            </select>
          </label>
          <span class="subtle small">—</span>
          <select class="filter-select" id="filter-year-to" aria-label="截止年份">
            <option value="">不限</option>
            ${years.map((year) => `<option value="${year}" ${String(filters.year_to) === String(year) ? "selected" : ""}>${year}</option>`).join("")}
          </select>
          <label>主题
            <select class="filter-select" id="filter-topic">
              <option value="">全部</option>
              ${topics.map((item) => `<option value="${esc(item.topic)}" ${filters.topic === item.topic ? "selected" : ""}>${esc(item.topic)}</option>`).join("")}
            </select>
          </label>
          <label class="filter-check"><input type="checkbox" id="filter-oa" ${filters.open_access ? "checked" : ""}> 仅开放获取</label>
          <button class="btn btn-text" type="button" data-action="clear-filters">清空筛选</button>
        </div>
      </section>
      <div class="search-meta">
        <div class="meta-left">
          ${results ? `<span>找到 <b>${number(results.total)}</b> 条</span><span>用时 <b>${results.elapsed_ms} ms</b></span><span>${esc(results.mode)}</span>` : `<span>正在检索…</span>`}
        </div>
        <div class="meta-right">
          ${results ? `<button class="trace-toggle" type="button" data-action="toggle-trace">${ICONS.filter} ${state.search.traceOpen ? "收起" : "查看"} SQL 轨迹</button>` : ""}
        </div>
      </div>
      ${state.search.traceOpen && results ? traceBox(results) : ""}
      ${resultList}`;

    if (loading) {
      const input = $("#search-input");
      if (input) input.focus();
    }
  }

  function yearRange() {
    const min = Number(state.boot?.stats?.year_min || 2020);
    const max = Number(state.boot?.stats?.year_max || new Date().getFullYear());
    const years = [];
    for (let year = max; year >= min; year -= 1) years.push(year);
    return years;
  }

  function paperCard(paper) {
    const evidence = evidenceForPaper(paper.paper_id);
    const stance = evidence ? stanceOf(evidence.stance) : null;
    return `<article class="paper-card ${evidence ? "has-evidence" : ""}">
      <div class="paper-top">
        <div class="paper-main">
          <h3 class="paper-title"><a href="${esc(paper.url)}" target="_blank" rel="noopener">${esc(paper.title)}</a></h3>
          <div class="paper-meta">
            <span>${esc(paper.authors || "作者信息缺失")}</span><span class="dot"></span>
            <span>${esc(paper.year)}</span><span class="dot"></span>
            <span>${esc(paper.venue)}</span>
            <span class="topic">${esc(paper.topic)}</span>
            ${evidence ? `<span class="evidence-flag">${stance.label}已判断</span>` : ""}
          </div>
          <p class="paper-snippet">${paper.snippet_html || esc(paper.snippet || "")}</p>
          <div class="paper-actions">
            <button class="btn btn-secondary" type="button" data-action="open-paper" data-paper-id="${paper.paper_id}">${ICONS.book} 摘要</button>
            <button class="btn ${evidence ? "btn-secondary" : "btn-terra"}" type="button" data-action="add-evidence" data-paper-id="${paper.paper_id}">${evidence ? ICONS.edit + " 编辑判断" : ICONS.plus + " 加入证据表"}</button>
            <a class="btn btn-text" href="${esc(paper.url)}" target="_blank" rel="noopener">arXiv ${ICONS.external}</a>
          </div>
        </div>
        <div class="paper-side">
          <div class="score"><b>${Number(paper.score).toFixed(1)}</b><span>相关度</span></div>
          <span class="pill">${esc(paper.matched_terms?.slice(0, 2).join(" · ") || "关键词")}</span>
        </div>
      </div>
    </article>`;
  }

  function traceBox(result) {
    const trace = result.sql_trace || {};
    return `<div class="trace-box">
      <div class="trace-label">${ICONS.search} seekdb query trace</div>
      <code>${esc(trace.statement || "—")}</code>
      <div class="trace-stats"><span>候选 ${number(trace.candidates)}</span><span>词法核验 ${number(trace.verified)}</span><span>${esc(trace.engine)}</span></div>
    </div>`;
  }

  async function doSearch(query) {
    state.search.q = query.trim() || "RAG hallucination";
    state.search.loading = true;
    state.search.traceOpen = false;
    renderLibrary();
    const params = new URLSearchParams({ q: state.search.q, limit: "20" });
    const filters = state.search.filters;
    if (filters.year_from) params.set("year_from", filters.year_from);
    if (filters.year_to) params.set("year_to", filters.year_to);
    if (filters.topic) params.set("topic", filters.topic);
    if (filters.open_access) params.set("open_access", "true");
    try {
      state.search.results = await api(`/api/search?${params.toString()}`);
    } catch (error) {
      state.search.results = { results: [], total: 0, elapsed_ms: 0, mode: error.message, sql_trace: {} };
      toast(error.message, "error");
    } finally {
      state.search.loading = false;
      if (state.view === "library") renderLibrary();
    }
  }

  // ----------------------------------------------------------------- evidence
  async function ensureEvidence(force = false) {
    if (state.evidence.loading) return;
    if (state.evidence.loaded && !force) return;
    state.evidence.loading = true;
    try {
      const data = await api("/api/evidence");
      state.evidence.items = data.items || [];
      state.evidence.counts = data.counts || {};
      state.evidence.loaded = true;
    } catch (error) {
      toast(error.message, "error");
    } finally {
      state.evidence.loading = false;
      if (state.view === "evidence") renderEvidence();
      else if (state.view === "synthesis") renderSynthesis();
      else if (state.view === "library") renderLibrary();
    }
  }

  function evidenceForPaper(paperId) {
    return state.evidence.items.find((item) => Number(item.paper_id) === Number(paperId)) || null;
  }

  function renderEvidence() {
    if (!state.evidence.loaded && !state.evidence.loading) {
      ensureEvidence();
    }
    const items = state.evidence.items.filter((item) => state.evidence.filter === "all" || item.stance === state.evidence.filter);
    const counts = state.evidence.counts || {};
    const total = Object.values(counts).reduce((sum, value) => sum + Number(value || 0), 0);
    const years = {};
    for (const item of state.evidence.items) {
      const year = Number(item.year);
      if (year) years[year] = (years[year] || 0) + 1;
    }
    const maxYear = Math.max(1, ...Object.values(years));

    const cards = items.length
      ? `<div class="evidence-grid">${items.map((item) => evidenceCard(item)).join("")}</div>`
      : emptyState("这一栏还是空的", "回到文献库，对一篇论文写下“支持 / 挑战 / 混合”的判断。证据表会把它变成可复用的研究资产。", `<button class="btn btn-primary" type="button" data-action="open-library">去文献库 ${ICONS.arrow}</button>`);

    $("#view").innerHTML = `
      <div class="view-head">
        <div><p class="eyebrow">证据不是摘要，是判断</p><h2>你相信什么，为什么。</h2><p>每条判断都关联一篇 seekdb 中的论文；它是后面综述提纲的引用来源，也是 PowerContext 记住的研究决策。</p></div>
        <div class="view-head-actions">
          <a class="btn btn-secondary" href="/api/export/evidence.md">${ICONS.download} Markdown</a>
          <a class="btn btn-secondary" href="/api/export/evidence.csv">CSV</a>
          <button class="btn btn-primary" type="button" data-action="open-synthesis">生成综述 ${ICONS.arrow}</button>
        </div>
      </div>
      <div class="evidence-summary">
        <section class="panel evidence-chart">
          <div class="panel-head" style="padding:0"><div><h3>判断分布</h3><p>${total} 条证据 · 支持 ${counts.support || 0} · 挑战 ${counts.challenge || 0} · 混合 ${counts.mixed || 0}</p></div><span class="pill">${total ? `${Math.round(((counts.support || 0) / total) * 100)}% 支持` : "待开始"}</span></div>
          ${["support", "challenge", "mixed"].map((stance) => {
            const count = counts[stance] || 0;
            const width = total ? Math.round((count / total) * 100) : 0;
            return `<div class="chart-row"><span>${STANCE[stance].label}</span><div class="chart-bar"><span style="width:${width}%;background:${STANCE[stance].color}"></span></div><b>${count}</b></div>`;
          }).join("")}
        </section>
        <section class="panel evidence-chart">
          <div class="panel-head" style="padding:0"><div><h3>年份覆盖</h3><p>证据是否集中在某几年？时间分布本身也是判断的一部分。</p></div></div>
          <div class="coverage">
            ${[2020, 2021, 2022, 2023, 2024, 2025, 2026].map((year) => `<div class="coverage-col"><span style="height:${Math.max(3, Math.round(((years[year] || 0) / maxYear) * 78))}%"></span><small>${year}</small></div>`).join("")}
          </div>
        </section>
      </div>
      <div class="evidence-toolbar">
        <div class="filter-pills">
          ${[["all", "全部"], ["support", "支持"], ["challenge", "挑战"], ["mixed", "混合"]].map(([key, label]) => `<button class="filter-pill ${state.evidence.filter === key ? "is-active" : ""}" type="button" data-action="filter-evidence" data-filter="${key}">${label}</button>`).join("")}
        </div>
        <span class="subtle small">${items.length} / ${state.evidence.items.length} 条</span>
      </div>
      ${cards}`;
  }

  function evidenceCard(item) {
    const stance = stanceOf(item.stance);
    return `<article class="evidence-card" data-stance="${esc(item.stance)}">
      <div class="stance-rail"></div>
      <div class="evidence-body">
        <div class="evidence-top">
          <span class="stance-badge ${stance.cls}">${stance.label}</span>
          <span class="memory-time">${formatDate(item.updated_at || item.created_at)}</span>
        </div>
        <h3 class="evidence-title"><a href="${esc(item.url)}" target="_blank" rel="noopener">${esc(item.title)}</a></h3>
        <div class="evidence-meta"><span>${esc(item.authors || "")}</span><span>${esc(item.year)}</span><span>${esc(item.venue)}</span><span>${esc(item.topic)}</span></div>
        <p class="evidence-note">${esc(item.note || "（未填写判断）")}</p>
        <div class="evidence-actions">
          <button class="btn btn-secondary" type="button" data-action="edit-evidence" data-evidence-id="${item.evidence_id}">${ICONS.edit} 编辑</button>
          <button class="btn btn-danger" type="button" data-action="delete-evidence" data-evidence-id="${item.evidence_id}">${ICONS.trash} 移除</button>
          <a class="btn btn-text" href="${esc(item.url)}" target="_blank" rel="noopener">arXiv ${ICONS.external}</a>
        </div>
      </div>
    </article>`;
  }

  // ---------------------------------------------------------------- synthesis
  function renderSynthesis() {
    if (!state.evidence.loaded && !state.evidence.loading) {
      ensureEvidence();
    }
    if (!state.synthesis.loadedLatest) {
      state.synthesis.loadedLatest = true;
      api("/api/synthesis/latest")
        .then((item) => {
          if (!state.synthesis.result) {
            state.synthesis.result = {
              title: item.title,
              markdown: item.content,
              template: "review",
              template_label: "已保存的综述",
              created_at: item.created_at,
              saved: true,
            };
            if (state.view === "synthesis") renderSynthesis();
          }
        })
        .catch(() => {});
    }
    const evidence = state.evidence.items;
    const selected = state.synthesis.selected ?? evidence.map((item) => Number(item.evidence_id));
    const result = state.synthesis.result;

    const checks = evidence.length
      ? evidence.map((item) => `<label class="check-item"><input type="checkbox" data-evidence-check value="${item.evidence_id}" ${selected.includes(Number(item.evidence_id)) ? "checked" : ""}><span class="check-copy"><b>${esc(item.title)}</b><span>${stanceOf(item.stance).label} · ${esc(item.year)}</span></span></label>`).join("")
      : `<div class="empty-state" style="padding:24px 12px"><p>证据表为空。先写一条判断，再生成提纲。</p></div>`;

    const doc = result
      ? `<div class="doc-body markdown" id="synthesis-doc">${renderMarkdown(result.markdown || "")}</div>`
      : `<div class="doc-placeholder"><span class="empty-mark">${ICONS.spark}</span><h3>把证据接成一篇初稿</h3><p>左侧选择模板和证据，右侧会生成一份带引用编号的 Markdown。它不调用外部模型，评审可以逐条核对。</p><button class="btn btn-primary" type="button" data-action="generate-synthesis">${ICONS.spark} 生成第一版</button></div>`;

    $("#view").innerHTML = `
      <div class="view-head">
        <div><p class="eyebrow">规则生成 · 可逐条核对</p><h2>从证据，到可讨论的初稿。</h2><p>生成的是研究提纲，不是“最终答案”。每个引用编号都指向证据表里的一条判断和它的摘要出处。</p></div>
        <div class="view-head-actions"><button class="btn btn-secondary" type="button" data-action="open-evidence">回到证据表 ${ICONS.arrow}</button></div>
      </div>
      <div class="synthesis-layout">
        <div class="synthesis-side">
          <section class="panel synthesis-panel">
            <h3>生成设置</h3>
            <p>先选写作场景，再确认要引用哪些证据。</p>
            <div class="template-options">
              <label class="template-option ${state.synthesis.template === "review" ? "is-active" : ""}"><input type="radio" name="synthesis-template" value="review" ${state.synthesis.template === "review" ? "checked" : ""}><span><b>文献综述提纲</b><span>研究问题、证据分布、支持/挑战、空白与下一步</span></span></label>
              <label class="template-option ${state.synthesis.template === "weekly" ? "is-active" : ""}"><input type="radio" name="synthesis-template" value="weekly" ${state.synthesis.template === "weekly" ? "checked" : ""}><span><b>组会周报</b><span>本周判断、需要讨论的分歧、下周计划</span></span></label>
            </div>
            <div class="synthesis-actions" style="flex-direction:row;margin-top:10px">
              <button class="btn btn-secondary" type="button" data-action="select-all-evidence" style="flex:1">全选</button>
              <button class="btn btn-secondary" type="button" data-action="clear-evidence" style="flex:1">清空</button>
            </div>
          </section>
          <section class="panel synthesis-panel">
            <h3>引用证据 <span class="pill" style="margin-left:6px">${selected.length} / ${evidence.length}</span></h3>
            <p>只选你愿意在初稿里为之负责的判断。</p>
            <div class="check-list">${checks}</div>
            <div class="synthesis-actions"><button class="btn btn-primary" type="button" data-action="generate-synthesis" ${state.synthesis.loading ? "disabled" : ""}>${state.synthesis.loading ? "正在生成…" : ICONS.spark + " 生成" + (state.synthesis.template === "weekly" ? "周报" : "综述提纲")}</button></div>
          </section>
        </div>
        <section class="panel synthesis-main">
          <div class="synthesis-toolbar">
            <div class="doc-meta"><span class="doc-status"><span class="status-dot ok"></span>${result ? "已生成" : "等待生成"}</span><span>${result ? `${esc(result.template_label || "综述")} · ${formatDate(result.created_at)}` : "Markdown · 引用编号"}</span></div>
            <div class="tools">
              <button class="btn btn-secondary" type="button" data-action="copy-markdown" ${result ? "" : "disabled"}>${ICONS.copy} 复制</button>
              <button class="btn btn-secondary" type="button" data-action="download-markdown" ${result ? "" : "disabled"}>${ICONS.download} 下载</button>
            </div>
          </div>
          ${doc}
        </section>
      </div>`;
  }

  async function generateSynthesis() {
    const selected = state.synthesis.selected ?? state.evidence.items.map((item) => Number(item.evidence_id));
    if (!selected.length) {
      toast("先选择至少一条证据", "error");
      return;
    }
    state.synthesis.loading = true;
    renderSynthesis();
    try {
      const result = await api("/api/synthesis", {
        method: "POST",
        body: JSON.stringify({ template: state.synthesis.template, evidence_ids: selected }),
      });
      state.synthesis.result = result;
      state.synthesis.loadedLatest = true;
      toast("综述提纲已生成，并写入研究记忆");
      await refreshBootstrap(false);
    } catch (error) {
      toast(error.message, "error");
    } finally {
      state.synthesis.loading = false;
      if (state.view === "synthesis") renderSynthesis();
    }
  }

  function renderMarkdown(markdown) {
    const lines = String(markdown || "").replace(/\r\n/g, "\n").split("\n");
    const html = [];
    let list = null;
    let paragraph = [];
    let quote = [];

    const inline = (text) => {
      let value = esc(text);
      value = value.replace(/`([^`]+)`/g, "<code>$1</code>");
      value = value.replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>");
      value = value.replace(/\[([^\]]+)\]\((https?:\/\/[^)\s]+)\)/g, '<a href="$2" target="_blank" rel="noopener">$1</a>');
      if (!value.includes("<a ")) {
        value = value.replace(/(^|[\s（(])(https?:\/\/[^\s<]+)/g, '$1<a href="$2" target="_blank" rel="noopener">$2</a>');
      }
      return value;
    };
    const flushParagraph = () => {
      if (paragraph.length) {
        html.push(`<p>${paragraph.map(inline).join(" ")}</p>`);
        paragraph = [];
      }
    };
    const flushQuote = () => {
      if (quote.length) {
        html.push(`<blockquote>${quote.map(inline).map((line) => `<p>${line}</p>`).join("")}</blockquote>`);
        quote = [];
      }
    };
    const closeList = () => {
      if (list) {
        html.push(`</${list}>`);
        list = null;
      }
    };

    for (const raw of lines) {
      const line = raw.trimEnd();
      if (!line.trim()) {
        flushParagraph();
        flushQuote();
        closeList();
        continue;
      }
      if (line.startsWith("### ")) {
        flushParagraph(); flushQuote(); closeList();
        html.push(`<h3>${inline(line.slice(4))}</h3>`);
      } else if (line.startsWith("## ")) {
        flushParagraph(); flushQuote(); closeList();
        html.push(`<h2>${inline(line.slice(3))}</h2>`);
      } else if (line.startsWith("# ")) {
        flushParagraph(); flushQuote(); closeList();
        html.push(`<h1>${inline(line.slice(2))}</h1>`);
      } else if (line.startsWith("> ")) {
        flushParagraph(); closeList(); quote.push(line.slice(2));
      } else if (/^---+$/.test(line.trim())) {
        flushParagraph(); flushQuote(); closeList();
        html.push("<hr>");
      } else if (/^- /.test(line)) {
        flushParagraph(); flushQuote();
        if (list !== "ul") { closeList(); html.push("<ul>"); list = "ul"; }
        html.push(`<li>${inline(line.slice(2))}</li>`);
      } else if (/^\d+\.\s+/.test(line)) {
        flushParagraph(); flushQuote();
        if (list !== "ol") { closeList(); html.push("<ol>"); list = "ol"; }
        html.push(`<li>${inline(line.replace(/^\d+\.\s+/, ""))}</li>`);
      } else {
        flushQuote();
        if (list) closeList();
        paragraph.push(line);
      }
    }
    flushParagraph(); flushQuote(); closeList();
    return html.join("\n");
  }

  // ------------------------------------------------------------------- memory
  async function loadMemory(force = false) {
    if (state.memory.loading) return;
    if (state.memory.data && !force) return;
    state.memory.loading = true;
    try {
      state.memory.data = await api("/api/memory");
    } catch (error) {
      state.memory.data = { available: false, error: error.message, entries: [] };
      toast(error.message, "error");
    } finally {
      state.memory.loading = false;
      if (state.view === "memory") renderMemory();
    }
  }

  function renderMemory() {
    if (!state.memory.data) {
      if (!state.memory.loading) loadMemory();
      $("#view").innerHTML = `<div class="loading-state" style="min-height:44vh"><div class="loading-mark"></div><p>正在从 PowerContext 读取研究记忆…</p></div>`;
      return;
    }
    const data = state.memory.data || { available: false, entries: [] };
    if (!data.available) {
      $("#view").innerHTML = `
        <div class="view-head"><div><p class="eyebrow">PowerContext</p><h2>研究记忆暂时不可用。</h2><p>${esc(data.error || "PowerContext 没有连接上。")}</p></div></div>
        <div class="empty-state"><span class="empty-mark">${ICONS.memory}</span><h4>记忆连接断开</h4><p>启动 PowerContext 后点击重试；已写入 seekdb 的证据不会丢失。</p><button class="btn btn-primary" type="button" data-action="reconnect-memory">${ICONS.refresh} 重新连接</button></div>`;
      return;
    }
    const entries = asArray(data.entries);
    const filtered = entries.filter((entry) => state.memory.filter === "all" || entry.kind === state.memory.filter);
    const kinds = [["all", "全部"], ["research-brief", "研究问题"], ["evidence-decision", "证据判断"], ["session-summary", "会话交接"], ["synthesis", "综述草稿"]];
    const kindCounts = data.by_kind || {};
    const cards = filtered.length
      ? filtered.map((entry) => memoryCard(entry)).join("")
      : emptyState("这个类型还没有记忆", "在文献库写一条判断，或在研究台更新一次问题，记忆会从这里长出来。", "");

    $("#view").innerHTML = `
      <div class="memory-head-card">
        <div><p class="eyebrow" style="color:#d7a26f">PowerContext · 跨会话上下文</p><h2>研究记忆，不是聊天记录。</h2><p>它记住的是你的研究问题、筛选标准、每条证据的判断，以及一次会话停在哪里。新的会话从这些决策恢复，而不是从空白开始。</p><div class="scope">scope · ${esc(data.scope_id || "—")} · ${number(data.total || 0)} 条 active memory</div></div>
        <div class="memory-head-actions">
          <button class="btn btn-secondary" type="button" data-action="reconnect-memory">${ICONS.refresh} 重连</button>
          <button class="btn btn-terra" type="button" data-action="new-session">${ICONS.spark} 模拟新会话</button>
        </div>
      </div>
      <div class="memory-layout">
        <div>
          <div class="memory-filter">
            ${kinds.map(([key, label]) => `<button class="filter-pill ${state.memory.filter === key ? "is-active" : ""}" type="button" data-action="filter-memory" data-filter="${key}">${label}${key !== "all" && kindCounts[key] ? ` ${kindCounts[key]}` : ""}</button>`).join("")}
          </div>
          <div class="memory-timeline">${cards}</div>
        </div>
        <div class="memory-side">
          <section class="panel memory-how"><h3>它如何被使用</h3><p>三条路径，全部可在运行日志里核对。</p>
            <div class="how-step"><span class="how-num">1</span><div><b>会话开始</b><span>从 Scope 读取研究 brief 与上次交接，填满今日研究台。</span></div></div>
            <div class="how-step"><span class="how-num">2</span><div><b>写下判断</b><span>每次把论文标记为支持/挑战/混合，都会写入一条 evidence-decision。</span></div></div>
            <div class="how-step"><span class="how-num">3</span><div><b>开始新会话</b><span>生成交接摘要，下一次打开时从断点继续，而不是重读所有论文。</span></div></div>
          </section>
          <section class="panel memory-stats">
            <div class="memory-stat"><b>${number(data.total || 0)}</b><span>active entries</span></div>
            <div class="memory-stat"><b>${number(kindCounts["evidence-decision"] || 0)}</b><span>证据判断</span></div>
            <div class="memory-stat"><b>${number(kindCounts["session-summary"] || 0)}</b><span>会话交接</span></div>
            <div class="memory-stat"><b>${number(kindCounts.synthesis || 0)}</b><span>综述草稿</span></div>
          </section>
          <section class="panel memory-how"><h3>为什么不是 RAG 的替代品</h3><p>seekdb 负责“找到证据”，PowerContext 负责“记住为什么选它”。两者分工不重叠：论文与检索留在 seekdb，研究决策与交接留在 Memory。</p></section>
        </div>
      </div>`;
  }

  function memoryCard(entry) {
    const payload = entry.payload || {};
    let detail = "";
    if (entry.kind === "research-brief") detail = payload.scope || "";
    else if (entry.kind === "evidence-decision") detail = payload.note || "";
    else if (entry.kind === "session-summary") detail = payload.next_action ? `下一步：${payload.next_action}` : "";
    else if (entry.kind === "synthesis") detail = `${payload.evidence_count || 0} 条证据`;
    return `<article class="memory-card" data-kind="${esc(entry.kind)}">
      <div class="memory-card-head"><span class="memory-kind">${ICONS.memory} ${esc(kindLabel(entry.kind))}${entry.state && entry.state !== "active" ? ` · ${esc(entry.state)}` : ""}</span><span class="memory-time">${formatDate(entry.created_at)}</span></div>
      <p class="memory-summary">${esc(entry.summary || "（无摘要）")}</p>
      ${detail ? `<p class="memory-detail">${esc(detail)}</p>` : ""}
      <div class="memory-meta"><span>session ${esc(entry.session_id || "—")}</span><span>artifact ${esc((entry.artifact_id || "").slice(0, 16))}…</span><button class="memory-raw-toggle" type="button" data-action="toggle-raw" data-entry-id="${esc(entry.artifact_id)}">查看原始记录</button></div>
      <pre class="memory-raw" id="raw-${esc(entry.artifact_id)}" hidden>${esc(JSON.stringify(entry, null, 2))}</pre>
    </article>`;
  }

  // -------------------------------------------------------------------- modals
  function openModal(html, { wide = false } = {}) {
    const root = $("#modal-root");
    root.innerHTML = `<div class="modal-backdrop" data-action="modal-backdrop"><div class="modal ${wide ? "wide" : ""}" role="dialog" aria-modal="true">${html}</div></div>`;
    document.body.style.overflow = "hidden";
    setTimeout(() => {
      const first = root.querySelector("input, textarea, select, button");
      if (first) first.focus();
    }, 40);
  }

  function closeModal() {
    const root = $("#modal-root");
    root.innerHTML = "";
    document.body.style.overflow = "";
  }

  function modalHead(title, subtitle) {
    return `<div class="modal-head"><div><h3>${esc(title)}</h3>${subtitle ? `<p>${esc(subtitle)}</p>` : ""}</div><button class="modal-close" type="button" data-action="close-modal" aria-label="关闭">${ICONS.close}</button></div>`;
  }

  function openBriefModal() {
    const brief = state.boot?.brief || {};
    openModal(`${modalHead("编辑研究问题", "这段 brief 会写入 PowerContext；新的会话从这里恢复。")}
      <form id="brief-form">
        <div class="modal-body">
          <div class="form-grid">
            <div class="form-field full"><label>研究问题</label><input class="form-input" name="question" required maxlength="500" value="${esc(brief.question || "")}" placeholder="例如：RAG 真的能让大模型更可靠吗？"></div>
            <div class="form-field full"><label>范围与边界</label><textarea class="form-textarea" name="scope" maxlength="2000" placeholder="时间范围、领域、任务类型、排除什么">${esc(brief.scope || "")}</textarea></div>
            <div class="form-field full"><label>纳入标准（每行一条）</label><textarea class="form-textarea" name="criteria" maxlength="2000" placeholder="有可核对的实验或基准&#10;直接讨论事实性/幻觉">${esc(asArray(brief.criteria).join("\n"))}</textarea><span class="form-hint">这些标准会出现在综述提纲的“研究范围”一节。</span></div>
            <div class="form-field"><label>当前阶段</label><select class="form-select" name="stage">${["定题", "证据筛选", "证据整合", "写作", "组会汇报"].map((item) => `<option ${brief.stage === item ? "selected" : ""}>${item}</option>`).join("")}</select></div>
            <div class="form-field"><label>下一步</label><input class="form-input" name="next_action" maxlength="500" value="${esc(brief.next_action || "")}" placeholder="例如：补一条关于检索噪声的反方证据"></div>
          </div>
        </div>
        <div class="modal-foot"><span class="left">PowerContext 会保留每次修改，不覆盖历史。</span><button class="btn btn-secondary" type="button" data-action="close-modal">取消</button><button class="btn btn-primary" type="submit">保存 brief</button></div>
      </form>`, { wide: true });
  }

  function openPaperModal(paper, evidence = null) {
    const existing = evidence || evidenceForPaper(paper.paper_id);
    const stance = existing ? existing.stance : "support";
    openModal(`${modalHead(paper.title, `${paper.authors || ""} · ${paper.year} · ${paper.venue || ""}`)}
      <div class="modal-body">
        <div class="paper-detail-meta"><span class="topic">${esc(paper.topic)}</span><span>arXiv ${esc(paper.arxiv_id)}</span><a href="${esc(paper.url)}" target="_blank" rel="noopener">打开原文 ${ICONS.external}</a></div>
        <div class="abstract-box">${esc(paper.abstract || "")}</div>
        ${existing ? `<div class="evidence-existing"><b>已写入证据表：</b>${stanceOf(existing.stance).label} · ${esc(existing.note || "")}</div>` : ""}
        <form id="evidence-form">
          <input type="hidden" name="paper_id" value="${paper.paper_id}">
          <div class="form-field"><label>这条证据对你的研究问题意味着什么？</label>
            <div class="radio-row">
              ${["support", "challenge", "mixed"].map((key) => `<label class="radio-card ${key}"><input type="radio" name="stance" value="${key}" ${stance === key ? "checked" : ""}><span>${STANCE[key].label}</span></label>`).join("")}
            </div>
          </div>
          <div class="form-field" style="margin-top:12px"><label>我的判断（一句话，可核对）</label><textarea class="form-textarea" name="note" maxlength="4000" placeholder="例如：RAG 提升了开放域问答的事实性，但检索噪声仍是瓶颈。">${esc(existing?.note || "")}</textarea><span class="form-hint">写“为什么”，而不是复制摘要；综述提纲会引用这句话。</span></div>
          <div class="modal-foot" style="padding-left:0;padding-right:0;padding-bottom:0"><span class="left">写入 seekdb 证据表，同时写入 PowerContext 记忆。</span><button class="btn btn-secondary" type="button" data-action="close-modal">取消</button><button class="btn btn-primary" type="submit">${existing ? "更新判断" : "加入证据表"}</button></div>
        </form>
      </div>`, { wide: true });
  }

  function openEvidenceModal(item) {
    const paper = {
      paper_id: item.paper_id,
      arxiv_id: item.arxiv_id,
      title: item.title,
      authors: item.authors,
      year: item.year,
      venue: item.venue,
      topic: item.topic,
      url: item.url,
      abstract: item.abstract,
    };
    openPaperModal(paper, item);
  }

  async function saveEvidence(form) {
    const formData = new FormData(form);
    const paperId = Number(formData.get("paper_id"));
    const stance = String(formData.get("stance") || "support");
    const note = String(formData.get("note") || "").trim();
    if (!note) {
      toast("写一句你的判断，再保存", "error");
      return;
    }
    const button = form.querySelector('button[type="submit"]');
    if (button) { button.disabled = true; button.textContent = "保存中…"; }
    try {
      await api("/api/evidence", {
        method: "POST",
        body: JSON.stringify({ paper_id: paperId, stance, note }),
      });
      closeModal();
      toast("判断已写入 seekdb，并同步到 PowerContext");
      await ensureEvidence(true);
      await refreshBootstrap(false);
      if (state.view === "library") renderLibrary();
      if (state.view === "evidence") renderEvidence();
      if (state.view === "today") renderToday();
    } catch (error) {
      toast(error.message, "error");
      if (button) { button.disabled = false; button.textContent = "保存"; }
    }
  }

  async function saveBrief(form) {
    const formData = new FormData(form);
    const criteria = String(formData.get("criteria") || "")
      .split("\n")
      .map((line) => line.trim())
      .filter(Boolean);
    const payload = {
      question: String(formData.get("question") || "").trim(),
      scope: String(formData.get("scope") || "").trim(),
      criteria,
      stage: String(formData.get("stage") || "证据筛选"),
      owner: state.boot?.brief?.owner || "研究者",
      next_action: String(formData.get("next_action") || "").trim(),
    };
    if (!payload.question) {
      toast("研究问题不能为空", "error");
      return;
    }
    const button = form.querySelector('button[type="submit"]');
    if (button) { button.disabled = true; button.textContent = "保存中…"; }
    try {
      await api("/api/brief", { method: "POST", body: JSON.stringify(payload) });
      closeModal();
      toast("研究 brief 已更新");
      await refreshBootstrap(false);
      renderCurrent();
    } catch (error) {
      toast(error.message, "error");
      if (button) { button.disabled = false; button.textContent = "保存 brief"; }
    }
  }

  function openHandoffModal(handoff) {
    openModal(`${modalHead("新会话已就绪", "上一段工作已写成交接摘要，保存在 PowerContext。")}
      <div class="modal-body">
        <div class="handoff-box"><p class="eyebrow">handoff summary</p><p>${esc(handoff.summary || "本次会话摘要已保存。")}</p></div>
        <div class="handoff-list">
          <div class="handoff-item"><span class="how-num">1</span><div><b>恢复位置</b><span>研究 brief、证据判断与上次交接仍然可用。</span></div></div>
          <div class="handoff-item"><span class="how-num">2</span><div><b>下一步</b><span>${esc(handoff.next_action || "继续补证据。")}</span></div></div>
          <div class="handoff-item"><span class="how-num">3</span><div><b>没有丢的东西</b><span>seekdb 中的论文和证据表不变；记忆只是换了会话。</span></div></div>
        </div>
      </div>
      <div class="modal-foot"><button class="btn btn-secondary" type="button" data-action="open-memory">查看记忆</button><button class="btn btn-primary" type="button" data-action="close-modal">回到研究台</button></div>`, { wide: true });
  }

  function emptyState(title, text, actions) {
    return `<div class="empty-state"><span class="empty-mark">${ICONS.spark}</span><h4>${esc(title)}</h4><p>${esc(text)}</p>${actions || ""}</div>`;
  }

  // ------------------------------------------------------------------ actions
  async function refreshBootstrap(shouldRender = true) {
    try {
      state.boot = await api("/api/bootstrap");
      updateChrome();
      if (shouldRender) renderCurrent();
    } catch (error) {
      toast(error.message, "error");
    }
  }

  async function startNewSession() {
    if (!window.confirm("开始新会话？当前会话会先写入一条交接摘要，然后从 PowerContext 恢复。")) return;
    try {
      const data = await api("/api/session/new", { method: "POST", body: JSON.stringify({}) });
      state.boot = data;
      state.search.results = null;
      state.evidence.items = [];
      state.evidence.loaded = false;
      state.memory.data = null;
      state.synthesis.result = null;
      state.synthesis.loadedLatest = false;
      state.synthesis.selected = null;
      updateChrome();
      location.hash = "#/today";
      state.view = "today";
      renderToday();
      openHandoffModal(data.handoff || {});
      toast("新会话已开始，记忆已恢复");
      ensureEvidence(true);
    } catch (error) {
      toast(error.message, "error");
    }
  }

  async function deleteEvidence(evidenceId) {
    const item = state.evidence.items.find((entry) => Number(entry.evidence_id) === Number(evidenceId));
    if (!item) return;
    if (!window.confirm(`移除这条判断？\n\n${item.title}`)) return;
    try {
      await api(`/api/evidence/${evidenceId}`, { method: "DELETE" });
      toast("已移除；PowerContext 会保留这次移除记录");
      await ensureEvidence(true);
      await refreshBootstrap(false);
      if (state.view === "evidence") renderEvidence();
      if (state.view === "library") renderLibrary();
      if (state.view === "today") renderToday();
    } catch (error) {
      toast(error.message, "error");
    }
  }

  async function reconnectMemory() {
    try {
      state.memory.data = null;
      state.boot = await api("/api/memory/reconnect", { method: "POST" });
      state.memory.data = null;
      updateChrome();
      toast(state.boot.memory?.available ? "PowerContext 已重新连接" : "仍未连接，请检查服务");
      if (state.view === "memory") {
        state.memory.data = null;
        renderMemory();
      } else {
        renderCurrent();
      }
    } catch (error) {
      toast(error.message, "error");
    }
  }

  // ------------------------------------------------------------------- events
  function handleAction(action, target) {
    if (action === "close-modal" || action === "modal-backdrop") {
      if (action === "modal-backdrop" && target !== target.closest(".modal-backdrop")) return;
      closeModal();
      return;
    }
    if (action === "retry-bootstrap") {
      state.fatal = null;
      init();
      return;
    }
    if (action === "edit-brief") { openBriefModal(); return; }
    if (action === "new-session") { startNewSession(); return; }
    if (action === "reconnect-memory") { reconnectMemory(); return; }
    if (action === "open-memory") { navigate("memory"); return; }
    if (action === "open-evidence") { navigate("evidence"); return; }
    if (action === "open-library") { navigate("library"); return; }
    if (action === "open-synthesis") {
      state.synthesis.selected = state.evidence.items.map((item) => Number(item.evidence_id));
      navigate("synthesis");
      return;
    }
    if (action === "continue-last") {
      navigate(state.evidence.items.length ? "evidence" : "library");
      return;
    }
    if (action === "quick-search") {
      state.search.q = target.dataset.q || "RAG hallucination";
      state.search.results = null;
      navigate("library");
      doSearch(state.search.q);
      return;
    }
    if (action === "open-paper" || action === "add-evidence") {
      const paperId = Number(target.dataset.paperId);
      const paper = state.search.results?.results?.find((item) => Number(item.paper_id) === paperId);
      if (paper) openPaperModal(paper);
      return;
    }
    if (action === "edit-evidence") {
      const id = Number(target.dataset.evidenceId);
      const item = state.evidence.items.find((entry) => Number(entry.evidence_id) === id);
      if (item) openEvidenceModal(item);
      return;
    }
    if (action === "delete-evidence") {
      deleteEvidence(Number(target.dataset.evidenceId));
      return;
    }
    if (action === "toggle-trace") {
      state.search.traceOpen = !state.search.traceOpen;
      renderLibrary();
      return;
    }
    if (action === "clear-filters") {
      state.search.filters = { year_from: "", year_to: "", topic: "", open_access: false };
      doSearch(state.search.q);
      return;
    }
    if (action === "filter-evidence") {
      state.evidence.filter = target.dataset.filter || "all";
      renderEvidence();
      return;
    }
    if (action === "filter-memory") {
      state.memory.filter = target.dataset.filter || "all";
      renderMemory();
      return;
    }
    if (action === "generate-synthesis") {
      generateSynthesis();
      return;
    }
    if (action === "select-all-evidence" || action === "clear-evidence") {
      state.synthesis.selected = action === "select-all-evidence"
        ? state.evidence.items.map((item) => Number(item.evidence_id))
        : [];
      renderSynthesis();
      return;
    }
    if (action === "copy-markdown") {
      const markdown = state.synthesis.result?.markdown || "";
      copyText(markdown)
        .then(() => toast("Markdown 已复制"))
        .catch(() => toast("复制失败，请手动选择文本", "error"));
      return;
    }
    if (action === "download-markdown") {
      const result = state.synthesis.result;
      if (!result) return;
      const blob = new Blob([result.markdown || ""], { type: "text/markdown;charset=utf-8" });
      const link = document.createElement("a");
      link.href = URL.createObjectURL(blob);
      link.download = `researchthread-${state.synthesis.template}.md`;
      link.click();
      setTimeout(() => URL.revokeObjectURL(link.href), 1000);
      return;
    }
    if (action === "toggle-raw") {
      const id = target.dataset.entryId;
      const raw = document.getElementById(`raw-${id}`);
      if (raw) {
        raw.hidden = !raw.hidden;
        target.textContent = raw.hidden ? "查看原始记录" : "收起原始记录";
      }
    }
  }

  async function copyText(text) {
    if (navigator.clipboard?.writeText) {
      await navigator.clipboard.writeText(text);
      return;
    }
    const area = document.createElement("textarea");
    area.value = text;
    area.style.position = "fixed";
    area.style.opacity = "0";
    document.body.appendChild(area);
    area.select();
    document.execCommand("copy");
    area.remove();
  }

  function bindEvents() {
    document.addEventListener("click", (event) => {
      const actionTarget = event.target.closest("[data-action]");
      if (actionTarget) {
        const backdrop = actionTarget.classList.contains("modal-backdrop") ? actionTarget : null;
        if (!backdrop || event.target === backdrop) {
          handleAction(actionTarget.dataset.action, actionTarget);
        }
      }
      if (event.target.closest(".nav-item")) {
        document.getElementById("app-shell")?.classList.remove("nav-open");
      }
    });

    document.addEventListener("submit", (event) => {
      const form = event.target;
      if (form.id === "search-form") {
        event.preventDefault();
        state.search.filters = {
          year_from: $("#filter-year-from")?.value || "",
          year_to: $("#filter-year-to")?.value || "",
          topic: $("#filter-topic")?.value || "",
          open_access: Boolean($("#filter-oa")?.checked),
        };
        doSearch($("#search-input")?.value || "RAG hallucination");
      } else if (form.id === "brief-form") {
        event.preventDefault();
        saveBrief(form);
      } else if (form.id === "evidence-form") {
        event.preventDefault();
        saveEvidence(form);
      }
    });

    document.addEventListener("change", (event) => {
      const target = event.target;
      if (target.name === "synthesis-template") {
        state.synthesis.template = target.value;
        renderSynthesis();
      }
      if (target.matches("[data-evidence-check]")) {
        const id = Number(target.value);
        const selected = new Set(state.synthesis.selected ?? state.evidence.items.map((item) => Number(item.evidence_id)));
        if (target.checked) selected.add(id); else selected.delete(id);
        state.synthesis.selected = Array.from(selected);
        const counter = document.querySelector(".synthesis-panel h3 .pill");
        if (counter) counter.textContent = `${selected.size} / ${state.evidence.items.length}`;
      }
    });

    document.addEventListener("keydown", (event) => {
      if (event.key === "Escape") closeModal();
      if (event.key === "/" && !["INPUT", "TEXTAREA", "SELECT"].includes(document.activeElement?.tagName)) {
        event.preventDefault();
        if (state.view !== "library") navigate("library");
        setTimeout(() => document.getElementById("search-input")?.focus(), 80);
      }
    });

    document.getElementById("new-session-btn")?.addEventListener("click", startNewSession);
    document.getElementById("mobile-menu")?.addEventListener("click", () => {
      document.getElementById("app-shell")?.classList.toggle("nav-open");
    });
    document.getElementById("search-jump")?.addEventListener("click", () => {
      if (state.view !== "library") navigate("library");
      setTimeout(() => document.getElementById("search-input")?.focus(), 80);
    });

    window.addEventListener("hashchange", route);
  }

  function route() {
    const raw = (location.hash || "#/today").replace(/^#\/?/, "");
    const view = VIEW_META[raw] ? raw : "today";
    setView(view);
    if (!state.boot) return;
    renderCurrent();
  }

  async function init() {
    bindEvents();
    updateChrome();
    try {
      const [boot, evidence] = await Promise.all([
        api("/api/bootstrap"),
        api("/api/evidence").catch(() => null),
      ]);
      state.boot = boot;
      state.fatal = null;
      if (evidence) {
        state.evidence.items = evidence.items || [];
        state.evidence.counts = evidence.counts || {};
        state.evidence.loaded = true;
      }
      updateChrome();
      route();
    } catch (error) {
      state.fatal = error.message;
      updateChrome();
      renderFatal();
    }
  }

  document.addEventListener("DOMContentLoaded", init);
})();
