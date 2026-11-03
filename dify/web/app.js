(() => {
  const $ = (id) => document.getElementById(id);
  const playerInput = $("player");
  const log = $("log");
  const input = $("input");
  const form = $("form");
  const send = $("send");
  const statusDot = $("statusDot");
  const memory = $("memory");

  let conversationId = "";
  let busy = false;
  const openingHTML = log.innerHTML;

  const params = new URLSearchParams(location.search);
  const stored = localStorage.getItem("grudge-inn-player");
  if (stored) playerInput.value = stored;
  if (params.get("player")) playerInput.value = params.get("player");

  function player() {
    return (playerInput.value || "demo-player").trim().slice(0, 64) || "demo-player";
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
      memory.textContent = data.powercontext
        ? `PowerContext：${data.powercontext.state_entries} 页状态 · ${data.powercontext.episode_entries} 段回忆`
        : "账本还是空的。";
      statusDot.textContent = "已连上账本";
    } catch (error) {
      statusDot.textContent = "账本没翻开";
      memory.textContent = String(error.message || error);
    }
  }

  async function say(query) {
    const text = String(query || "").trim();
    if (!text || busy) return;
    setBusy(true);
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
    localStorage.setItem("grudge-inn-player", player());
    newSession();
  });

  refreshState();

  if (params.has("demo")) {
    setTimeout(() => say("我把阿福的鞋藏到房梁上"), 500);
  }
})();
