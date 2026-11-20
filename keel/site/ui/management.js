// Keel management UI — connected to real backend APIs.
// Runs inside the desktop app (served by the Python bridge on 127.0.0.1).

(function () {
  "use strict";

  const API = "";  // same origin (bridge)

  async function apiGet(path) {
    const r = await fetch(API + path, { headers: { "Accept": "application/json" } });
    if (!r.ok) throw new Error(`GET ${path} -> ${r.status}`);
    return r.json();
  }

  async function apiPost(path, body) {
    const r = await fetch(API + path, {
      method: "POST",
      headers: { "Content-Type": "application/json", "Accept": "application/json" },
      body: JSON.stringify(body || {}),
    });
    if (!r.ok) throw new Error(`POST ${path} -> ${r.status}`);
    return r.json();
  }

  function el(tag, cls, text) {
    const n = document.createElement(tag);
    if (cls) n.className = cls;
    if (text !== undefined) n.textContent = text;
    return n;
  }

  function renderList(container, items, renderItem) {
    container.innerHTML = "";
    if (!items || items.length === 0) {
      container.appendChild(el("p", "hint", "No items found."));
      return;
    }
    for (const item of items) {
      container.appendChild(renderItem(item));
    }
  }

  // --- Skills management ---
  async function loadSkills() {
    const container = document.getElementById("skills-list");
    if (!container) return;
    container.innerHTML = '<p class="hint">Loading...</p>';
    try {
      const data = await apiGet("/api/fleet/skills/manage");
      const skills = (data && data.skills) || [];
      renderList(container, skills, (s) => {
        const card = el("div", "card");
        card.appendChild(el("h3", null, s.name));
        card.appendChild(el("p", "hint", s.description || ""));
        card.appendChild(el("p", "fine", `Scope: ${s.scope} | Trusted: ${s.trusted} | Enabled: ${s.enabled}`));
        if (s.injection_suspects && s.injection_suspects.length) {
          card.appendChild(el("p", "hint", `Warning: ${s.injection_suspects.length} injection suspects`));
        }
        const btns = el("div", "btn-row");
        const toggleBtn = el("button", "btn-secondary", s.enabled ? "Disable" : "Enable");
        toggleBtn.addEventListener("click", async () => {
          try {
            await apiPost("/api/fleet/skills/enable", { name: s.name, enabled: !s.enabled });
            loadSkills();
          } catch (e) { alert("Error: " + e.message); }
        });
        btns.appendChild(toggleBtn);
        const removeBtn = el("button", "btn-danger", "Remove");
        removeBtn.addEventListener("click", async () => {
          if (!confirm(`Remove skill ${s.name}?`)) return;
          try {
            await apiPost("/api/fleet/skills/remove", { name: s.name, scope: s.scope });
            loadSkills();
          } catch (e) { alert("Error: " + e.message); }
        });
        btns.appendChild(removeBtn);
        card.appendChild(btns);
        return card;
      });
    } catch (e) {
      container.innerHTML = `<p class="hint">Error: ${e.message}</p>`;
    }
  }

  // --- Commands management ---
  async function loadCommands() {
    const container = document.getElementById("commands-list");
    if (!container) return;
    container.innerHTML = '<p class="hint">Loading...</p>';
    try {
      const data = await apiGet("/api/fleet/commands?project_root=" + encodeURIComponent(window.__projectRoot || ""));
      const cmds = (data && data.commands) || [];
      renderList(container, cmds, (c) => {
        const card = el("div", "card");
        card.appendChild(el("h3", null, c.name));
        card.appendChild(el("p", "hint", c.description || ""));
        card.appendChild(el("p", "fine", `Source: ${c.source} ${c.argument_hint ? "| Args: " + c.argument_hint : ""}`));
        const execBtn = el("button", "btn-primary", "Execute");
        execBtn.addEventListener("click", async () => {
          const args = prompt("Arguments (optional):") || "";
          try {
            const res = await apiPost("/api/fleet/commands/execute", { name: c.name, args: args, project_root: window.__projectRoot });
            alert("Result: " + (res.result || JSON.stringify(res)));
          } catch (e) { alert("Error: " + e.message); }
        });
        card.appendChild(execBtn);
        return card;
      });
    } catch (e) {
      container.innerHTML = `<p class="hint">Error: ${e.message}</p>`;
    }
  }

  // --- Workflows management ---
  async function loadWorkflows() {
    const container = document.getElementById("workflows-list");
    if (!container) return;
    container.innerHTML = '<p class="hint">Loading...</p>';
    try {
      const data = await apiGet("/api/fleet/workflows?project_root=" + encodeURIComponent(window.__projectRoot || ""));
      const wfs = (data && data.workflows) || [];
      renderList(container, wfs, (w) => {
        const card = el("div", "card");
        card.appendChild(el("h3", null, w.name));
        card.appendChild(el("p", "hint", w.description || ""));
        card.appendChild(el("p", "fine", `Source: ${w.source} | Steps: ${w.steps}`));
        const execBtn = el("button", "btn-primary", "Execute");
        execBtn.addEventListener("click", async () => {
          try {
            const res = await apiPost("/api/fleet/workflows/execute", { name: w.name, project_root: window.__projectRoot });
            const results = res.results || [];
            const summary = results.map((r, i) => `Step ${i}: ${r.ok ? "OK" : "FAIL"} ${r.error || ""}`).join("\\n");
            alert(`Workflow ${w.name}: ${res.ok ? "SUCCESS" : "FAILED"}\\n${summary}`);
          } catch (e) { alert("Error: " + e.message); }
        });
        card.appendChild(execBtn);
        return card;
      });
    } catch (e) {
      container.innerHTML = `<p class="hint">Error: ${e.message}</p>`;
    }
  }

  // --- MCP management ---
  async function loadMcp() {
    const container = document.getElementById("mcp-list");
    if (!container) return;
    container.innerHTML = '<p class="hint">Loading...</p>';
    try {
      const data = await apiGet("/api/fleet/mcp/servers");
      const servers = (data && data.servers) || [];
      renderList(container, servers, (s) => {
        const card = el("div", "card");
        card.appendChild(el("h3", null, s.name));
        card.appendChild(el("p", "fine", `Transport: ${s.transport} | Scope: ${s.scope}`));
        if (s.url) card.appendChild(el("p", "fine", `URL: ${s.url}`));
        if (s.command) card.appendChild(el("p", "fine", `Command: ${s.command}`));
        const healthBtn = el("button", "btn-secondary", "Check Health");
        healthBtn.addEventListener("click", async () => {
          try {
            const res = await apiPost("/api/fleet/mcp/health", {});
            const h = res.health || {};
            alert(`Health: ${JSON.stringify(h)}`);
          } catch (e) { alert("Error: " + e.message); }
        });
        card.appendChild(healthBtn);
        return card;
      });
    } catch (e) {
      container.innerHTML = `<p class="hint">Error: ${e.message}</p>`;
    }
  }

  // --- Init: load management data when panes are shown ---
  function initManagement() {
    const observer = new MutationObserver(() => {
      const skillsPane = document.getElementById("pane-skills");
      if (skillsPane && skillsPane.classList.contains("on")) loadSkills();
      const connectorsPane = document.getElementById("pane-connectors");
      if (connectorsPane && connectorsPane.classList.contains("on")) { loadMcp(); loadCommands(); loadWorkflows(); }
    });
    const settingsEl = document.querySelector(".settings, .settings-panel, #settings");
    if (settingsEl) observer.observe(settingsEl, { attributes: true, subtree: true, attributeFilter: ["class"] });

    // Also try on DOMContentLoaded
    if (document.readyState === "loading") {
      document.addEventListener("DOMContentLoaded", () => { loadSkills(); loadCommands(); loadWorkflows(); loadMcp(); });
    } else {
      setTimeout(() => { loadSkills(); loadCommands(); loadWorkflows(); loadMcp(); }, 1000);
    }
  }

  initManagement();
})();
PY