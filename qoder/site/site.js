(() => {
  "use strict";

  document.body.classList.add("js");

  const nav = document.getElementById("nav");
  const menuButton = document.getElementById("menu-btn");
  const navLinks = document.getElementById("nav-links");

  const closeMenu = () => {
    nav?.classList.remove("is-open");
    menuButton?.setAttribute("aria-expanded", "false");
  };

  menuButton?.addEventListener("click", () => {
    const open = nav?.classList.toggle("is-open");
    menuButton.setAttribute("aria-expanded", open ? "true" : "false");
  });

  navLinks?.querySelectorAll("a").forEach((link) => link.addEventListener("click", closeMenu));

  const onScroll = () => {
    if (!nav) return;
    nav.classList.toggle("is-scrolled", window.scrollY > 12);
  };
  onScroll();
  window.addEventListener("scroll", onScroll, { passive: true });

  // Product tour tabs
  const tabs = Array.from(document.querySelectorAll(".tour-tab"));
  const panels = Array.from(document.querySelectorAll(".tour-panel"));
  const activate = (name) => {
    tabs.forEach((tab) => {
      const active = tab.dataset.tab === name;
      tab.classList.toggle("is-active", active);
      tab.setAttribute("aria-selected", active ? "true" : "false");
    });
    panels.forEach((panel) => {
      const active = panel.dataset.panel === name;
      panel.hidden = !active;
      panel.classList.toggle("is-active", active);
    });
  };
  tabs.forEach((tab) => tab.addEventListener("click", () => activate(tab.dataset.tab)));
  const params = new URLSearchParams(window.location.search);
  const requestedTab = params.get("tab");
  if (requestedTab && tabs.some((tab) => tab.dataset.tab === requestedTab)) {
    activate(requestedTab);
  }
  const requestedSection = params.get("section");
  if (requestedSection) {
    setTimeout(() => {
      document.getElementById(requestedSection)?.scrollIntoView({ behavior: "instant", block: "start" });
    }, 500);
  }

  // Reveal on scroll
  const reveals = Array.from(document.querySelectorAll(".reveal"));
  if ("IntersectionObserver" in window && !window.matchMedia("(prefers-reduced-motion: reduce)").matches) {
    const observer = new IntersectionObserver(
      (entries) => {
        entries.forEach((entry) => {
          if (entry.isIntersecting) {
            entry.target.classList.add("is-visible");
            observer.unobserve(entry.target);
          }
        });
      },
      { rootMargin: "0px 0px -8% 0px", threshold: 0.08 }
    );
    reveals.forEach((element) => observer.observe(element));
  } else {
    reveals.forEach((element) => element.classList.add("is-visible"));
  }

  // Copy buttons
  const copy = async (text) => {
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
  };

  document.querySelectorAll(".copy-btn").forEach((button) => {
    button.addEventListener("click", async () => {
      const text = button.dataset.copy || "";
      const previous = button.textContent;
      try {
        await copy(text);
        button.textContent = "已复制";
      } catch {
        button.textContent = "复制失败";
      }
      setTimeout(() => { button.textContent = previous; }, 1800);
    });
  });
})();
