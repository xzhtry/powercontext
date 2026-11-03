(() => {
  const $ = (id) => document.getElementById(id);
  const playerInput = $("player");
  const log = $("log");
  const input = $("input");
  const form = $("form");
  const send = $("send");
  const statusDot = $("statusDot");
  const chips = $("chips");

  let conversationId = "";
  let busy = false;
  const openingHTML = log.innerHTML;

  const params = new URLSearchParams(location.search);
  const stored = localStorage.getItem("grudge-inn-player");
  if (stored) playerInput.value = stored;
  if (params.get("player")) playerInput.value = params.get("player");

  function player() {
    return (
      (playerInput.value || "demo-player")
        .trim()
        .replace(/[^\w\u4e00-\u9fff-]/g, "-")
        .slice(0, 64) || "demo-player"
    );
  }

  function escapeHTML(text) {
    return text
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;");
  }

  function formatAnswer(text) {
    let html = escapeHTML(text || "");
    html = html.replace(/`([^`]+)`/g, "<code>$1</code>");
    html = html.replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>");
    html = html.replace(/^&gt;\s?(.*)$/gm, "<span class=\"quote\">$1</span>");
    html = html.replace(/^---$/gm, "<hr />");
    html = html.replace(/\n{2,}/g, "</p><p>");
    html = html.replace(/\n/g, "<br />");
    return `<p>${html}</p>`;
  }

  function bubble(role, content, extra = "") {
    const article = document.createElement("article");
    article.className = `bubble ${role} ${extra}`;
    const who = role === "player" ? "你" : "说书人";
    article.innerHTML = `<div class="who">${who}</div>${content}`;
    log.appendChild(article);
    log.scrollTop = log.scrollHeight;
    return article;
  }

  function setBusy(value) {
    busy = value;
    send.disabled = value;
    input.disabled = value;
  }

  function renderChips(state) {
    const stats = state.stats || {};
    const turn = Number(state.turn || 0);
    const grudge = Number(stats.grudge || 0);
    const favor = Number(stats.favor || 0);
    const silver = Number(stats.silver || 0);
    let items;
    if (silver < 5) {
      items = ["帮阿福干一天活", "去后厨帮工", "看看状态", "我道歉，对不起"];
    } else if (grudge >= 60) {
      items = ["买一碟桂花糕赔罪", "给阿福赏点银子", "帮阿福干一天活", "看看状态"];
    } else if (favor >= 60) {
      items = ["请柳三娘喝一杯", "买包鱼干喂乌云", "打听后山的宝藏", "看看状态"];
    } else if (turn >= 4) {
      items = ["买一碟桂花糕送柳三娘", "给阿福赏点银子", "打听后山的宝藏", "看看状态"];
    } else {
      items = ["把阿福的鞋藏到房梁上", "买一碟桂花糕送柳三娘", "偷看账本", "看看状态"];
    }
    chips.replaceChildren(
      ...items.map((text) => {
        const button = document.createElement("button");
        button.type = "button";
        button.dataset.q = text;
        button.textContent = text;
        return button;
      })
    );
  }

  async function refreshState() {
    const current = player();
    localStorage.setItem("grudge-inn-player", current);
    try {
      const response = await fetch(`/api/state?player_id=${encodeURIComponent(current)}`);
      const data = await response.json();
      if (!data.ok) throw new Error(data.error || "state failed");
      const state = data.state || {};
      const stats = state.stats || {};
      $("favor").textContent = stats.favor ?? "-";
      $("grudge").textContent = stats.grudge ?? "-";
      $("chaos").textContent = stats.chaos ?? "-";
      $("silver").textContent = stats.silver ?? "-";
      $("reputation").textContent = stats.reputation ?? "-";
      $("turn").textContent = `第 ${state.turn ?? 0} 回合`;
      $("title").textContent = state.title || "初入江湖";
      renderChips(state);
      statusDot.textContent = "已连上账本";
    } catch (error) {
      statusDot.textContent = "账本没翻开";
      // 出错时保留静态快捷项，不要显示技术错误打扰玩家
    }
  }

  async function say(query) {
    const text = String(query || "").trim();
    if (!text || busy) return;
    setBusy(true);
    // 第一次行动后收起快捷选项，避免旧建议一直占着地方
    chips.hidden = true;
    bubble("player", `<p>${escapeHTML(text)}</p>`);
    const loading = bubble("narrator", `<p class="loading">柳三娘翻着账本，阿福伸长了脖子……</p>`);
    try {
      const response = await fetch("/api/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ player_id: player(), query: text, conversation_id: conversationId }),
      });
      const data = await response.json();
      if (!data.ok) throw new Error(data.error || "Dify 没有回话");
      conversationId = data.conversation_id || conversationId;
      loading.remove();
      bubble("narrator", formatAnswer(data.answer));
      refreshState();
    } catch (error) {
      loading.remove();
      bubble("narrator", `<p class="error">客栈突然安静了：${escapeHTML(String(error.message || error))}</p>`);
    } finally {
      setBusy(false);
      input.focus();
    }
  }

  function newSession() {
    conversationId = "";
    log.innerHTML = openingHTML;
    chips.hidden = false;
    refreshState();
    input.focus();
  }

  form.addEventListener("submit", (event) => {
    event.preventDefault();
    const text = input.value;
    input.value = "";
    say(text);
  });

  input.addEventListener("keydown", (event) => {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      form.requestSubmit();
    }
  });

  $("chips").addEventListener("click", (event) => {
    const button = event.target.closest("button[data-q]");
    if (button) say(button.dataset.q);
  });

  $("newSession").addEventListener("click", newSession);

  $("reset").addEventListener("click", async () => {
    if (!confirm(`把「${player()}」的账本合上，重新开一代？`)) return;
    try {
      await fetch("/api/reset", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ player_id: player() }),
      });
    } catch (_) {}
    newSession();
  });

  playerInput.addEventListener("change", () => {
    playerInput.value = player();
    localStorage.setItem("grudge-inn-player", player());
    newSession();
  });

  refreshState();

  if (params.has("demo")) {
    setTimeout(() => say("我把阿福的鞋藏到房梁上"), 500);
  }
})();
