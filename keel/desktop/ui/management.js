// Keel management screens: Skills, Commands, Workflows and MCP servers.
// Loaded by the real desktop app shell (desktop/ui/index.html) and by the
// mirror app shell (site/app.html). Every request goes to the local bridge
// with the same X-Keel-Token credential the rest of the desktop app uses.

(function () {
  "use strict";

  window.__keelManagementActive = true;

  const API = ""; // same origin: the Python bridge on 127.0.0.1

  function bridgeToken() {
    const params = new URLSearchParams(window.location.search);
    return params.get("t") || sessionStorage.getItem("keel_token") || "";
  }

  function authHeaders(extra) {
    const headers = Object.assign({ Accept: "application/json" }, extra || {});
    const token = bridgeToken();
    if (token) headers["X-Keel-Token"] = token;
    return headers;
  }

  async function apiGet(path) {
    const response = await fetch(API + path, { headers: authHeaders() });
    if (!response.ok) throw new Error("GET " + path + " -> " + response.status);
    return response.json();
  }

  async function apiPost(path, body) {
    const response = await fetch(API + path, {
      method: "POST",
      headers: authHeaders({ "Content-Type": "application/json" }),
      body: JSON.stringify(body || {}),
    });
    if (!response.ok) throw new Error("POST " + path + " -> " + response.status);
    return response.json();
  }

  function el(tag, cls, text) {
    const node = document.createElement(tag);
    if (cls) node.className = cls;
    if (text !== undefined) node.textContent = text;
    return node;
  }

  function loading(container) {
    container.textContent = "";
    container.appendChild(el("p", "hint", "Loading..."));
  }

  function renderError(container, error, retry) {
    container.textContent = "";
    container.appendChild(el("p", "hint err", "Could not load: " + error.message));
    const row = el("div", "btn-row");
    const button = el("button", "btn-ghost small", "Retry");
    button.type = "button";
    button.addEventListener("click", retry);
    row.appendChild(button);
    container.appendChild(row);
  }

  function renderList(container, items, renderItem, emptyText) {
    container.textContent = "";
    if (!Array.isArray(items) || items.length === 0) {
      container.appendChild(el("p", "hint", emptyText || "No items found."));
      return;
    }
    for (const item of items) container.appendChild(renderItem(item));
  }

  function actionRow() {
    const row = el("div", "btn-row");
    return row;
  }

  function actionButton(label, cls, handler) {
    const button = el("button", cls, label);
    button.type = "button";
    button.addEventListener("click", handler);
    return button;
  }

  async function projectRoot() {
    if (window.__projectRoot) return window.__projectRoot;
    try {
      const doc = await apiGet("/api/workdir");
      return doc && typeof doc.path === "string" ? doc.path : "";
    } catch (error) {
      return "";
    }
  }

  // ---- Skills -----------------------------------------------------------

  async function loadSkills() {
    const container = document.getElementById("skills-list");
    if (!container) return;
    loading(container);
    try {
      const data = await apiGet("/api/fleet/skills/manage");
      renderList(container, (data && data.skills) || [], (skill) => {
        const card = el("div", "card");
        card.appendChild(el("h3", null, skill.name || "unnamed"));
        if (skill.description) card.appendChild(el("p", "hint", skill.description));
        const flags = [
          "Scope: " + (skill.scope || "?"),
          "Trusted: " + (skill.trusted ? "yes" : "no"),
          "Enabled: " + (skill.enabled ? "yes" : "no"),
        ].join(" | ");
        card.appendChild(el("p", "fine", flags));
        if (skill.injection_suspects && skill.injection_suspects.length) {
          card.appendChild(el("p", "hint err",
            "Warning: " + skill.injection_suspects.length + " injection suspect(s)"));
        }
        const row = actionRow();
        row.appendChild(actionButton(skill.enabled ? "Disable" : "Enable",
          "btn-ghost small", async () => {
            try {
              await apiPost("/api/fleet/skills/enable",
                { name: skill.name, enabled: !skill.enabled });
              loadSkills();
            } catch (error) {
              alert("Could not update skill: " + error.message);
            }
          }));
        row.appendChild(actionButton("Remove", "btn-ghost small danger", async () => {
          if (!confirm("Remove skill " + skill.name + "?")) return;
          try {
            await apiPost("/api/fleet/skills/remove",
              { name: skill.name, scope: skill.scope });
            loadSkills();
          } catch (error) {
            alert("Could not remove skill: " + error.message);
          }
        }));
        card.appendChild(row);
        return card;
      }, "No skills found on this machine.");
    } catch (error) {
      renderError(container, error, loadSkills);
    }
  }

  // ---- Commands ---------------------------------------------------------

  async function loadCommands() {
    const container = document.getElementById("commands-list");
    if (!container) return;
    loading(container);
    try {
      const root = await projectRoot();
      const data = await apiGet("/api/fleet/commands?project_root=" +
        encodeURIComponent(root));
      renderList(container, (data && data.commands) || [], (command) => {
        const card = el("div", "card");
        card.appendChild(el("h3", null, command.name || "unnamed"));
        if (command.description) card.appendChild(el("p", "hint", command.description));
        const meta = "Source: " + (command.source || "?") +
          (command.argument_hint ? " | Args: " + command.argument_hint : "");
        card.appendChild(el("p", "fine", meta));
        const row = actionRow();
        row.appendChild(actionButton("Execute", "btn-primary", async () => {
          const args = prompt("Arguments (optional):") || "";
          try {
            const result = await apiPost("/api/fleet/commands/execute",
              { name: command.name, args: args, project_root: root });
            alert("Result:\n" + (result.result || JSON.stringify(result)));
          } catch (error) {
            alert("Could not run command: " + error.message);
          }
        }));
        card.appendChild(row);
        return card;
      }, "No commands found for this folder.");
    } catch (error) {
      renderError(container, error, loadCommands);
    }
  }

  // ---- Workflows --------------------------------------------------------

  async function loadWorkflows() {
    const container = document.getElementById("workflows-list");
    if (!container) return;
    loading(container);
    try {
      const root = await projectRoot();
      const data = await apiGet("/api/fleet/workflows?project_root=" +
        encodeURIComponent(root));
      renderList(container, (data && data.workflows) || [], (workflow) => {
        const card = el("div", "card");
        card.appendChild(el("h3", null, workflow.name || "unnamed"));
        if (workflow.description) card.appendChild(el("p", "hint", workflow.description));
        card.appendChild(el("p", "fine",
          "Source: " + (workflow.source || "?") + " | Steps: " + (workflow.steps || 0)));
        const row = actionRow();
        row.appendChild(actionButton("Execute", "btn-primary", async () => {
          try {
            const result = await apiPost("/api/fleet/workflows/execute",
              { name: workflow.name, project_root: root });
            const steps = (result.results || []).map((step, index) => {
              return "Step " + index + ": " + (step.ok ? "OK" : "FAIL") +
                (step.error ? " " + step.error : "");
            }).join("\n");
            alert("Workflow " + workflow.name + ": " +
              (result.ok ? "SUCCESS" : "FAILED") + "\n" + steps);
          } catch (error) {
            alert("Could not run workflow: " + error.message);
          }
        }));
        card.appendChild(row);
        return card;
      }, "No workflows found. Add JSON workflows under .keel/workflows.");
    } catch (error) {
      renderError(container, error, loadWorkflows);
    }
  }

  // ---- MCP servers ------------------------------------------------------

  async function loadMcp() {
    const container = document.getElementById("mcp-list");
    if (!container) return;
    loading(container);
    try {
      const data = await apiGet("/api/fleet/mcp/servers");
      renderList(container, (data && data.servers) || [], (server) => {
        const card = el("div", "card");
        card.appendChild(el("h3", null, server.name || "unnamed"));
        card.appendChild(el("p", "fine",
          "Transport: " + (server.transport || "?") +
          " | Scope: " + (server.scope || "?")));
        if (server.url) card.appendChild(el("p", "fine", "URL: " + server.url));
        if (server.command) card.appendChild(el("p", "fine", "Command: " + server.command));
        const row = actionRow();
        row.appendChild(actionButton("Check health", "btn-ghost small", async () => {
          try {
            const result = await apiPost("/api/fleet/mcp/health", {});
            alert("Health: " + JSON.stringify(result.health || {}, null, 2));
          } catch (error) {
            alert("Could not check MCP health: " + error.message);
          }
        }));
        card.appendChild(row);
        return card;
      }, "No MCP servers configured. Add them in the fleet console.");
    } catch (error) {
      renderError(container, error, loadMcp);
    }
  }

  const loaders = {
    skills: loadSkills,
    commands: loadCommands,
    workflows: loadWorkflows,
    connectors: loadMcp,
  };

  let activeSection = "";

  function activate(section) {
    if (!section || section === activeSection) return;
    activeSection = section;
    if (loaders[section]) loaders[section]();
  }

  function syncActivePane() {
    const body = document.getElementById("settings-body");
    if (!body) return;
    const pane = body.querySelector(".pane.on");
    if (!pane) return;
    activate(pane.id.replace(/^pane-/, ""));
  }

  function initManagement() {
    const body = document.getElementById("settings-body");
    if (body && typeof MutationObserver === "function") {
      const observer = new MutationObserver(syncActivePane);
      observer.observe(body, {
        subtree: true,
        attributes: true,
        attributeFilter: ["class"],
      });
    }
    syncActivePane();
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", initManagement);
  } else {
    initManagement();
  }
})();
