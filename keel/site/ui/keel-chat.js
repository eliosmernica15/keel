"use strict";

/* Keel — shared client-side chat/provider engine for light pages (/new).
 *
 * This is the browser-side BYOK backend already used by ui/app.js:
 *   - keys/models live in localStorage  keel_mirror_settings_v1
 *   - counters live in sessionStorage   keel_mirror_usage_v1
 *   - chat streams directly to OpenRouter or Google AI Studio (SSE)
 *   - files are inlined as read-only context, images go to the vision model
 *
 * No dependencies, no DOM access, no logging. Keys are used only for requests
 * to the provider the caller chose and are never written anywhere except the
 * shared localStorage settings object. The optional same-origin
 * /api/model-catalog/* bridge is only used for model names (never for keys).
 */
(function (global) {
  var SETTINGS_KEY = "keel_mirror_settings_v1";
  var USAGE_KEY = "keel_mirror_usage_v1";
  var TOKEN_KEY = "keel_token";
  var MAX_FILES = 8;
  var MAX_BYTES = 4 * 1024 * 1024;
  var MAX_TOTAL = 12 * 1024 * 1024;
  var TEXT_MIME = /^(text\/|application\/(json|xml|javascript|x-yaml|yaml|toml|x-sh|x-sql|sql|csv|x-python|x-rust)|image\/svg\+xml)/i;

  /* OpenRouter attribution headers — identifies Keel to the gateway. */
  var OPENROUTER_ATTRIBUTION = {
    "HTTP-Referer": "https://keel-desktop.vercel.app",
    "X-OpenRouter-Title": "Keel",
    "X-OpenRouter-Categories": "general-chat"
  };

  function assign() {
    var out = {};
    for (var i = 0; i < arguments.length; i++) {
      var src = arguments[i];
      if (src && typeof src === "object") {
        for (var k in src) {
          if (Object.prototype.hasOwnProperty.call(src, k)) out[k] = src[k];
        }
      }
    }
    return out;
  }

  function isObject(v) {
    return !!v && typeof v === "object" && !Array.isArray(v);
  }

  function store(kind) {
    try { return global[kind] || null; } catch (e) { return null; }
  }

  function readJSON(kind, key, fallback) {
    try {
      var s = store(kind);
      if (!s) return fallback;
      var raw = s.getItem(key);
      if (!raw) return fallback;
      var value = JSON.parse(raw);
      return isObject(value) ? value : fallback;
    } catch (e) { return fallback; }
  }

  function writeJSON(kind, key, value) {
    try {
      var s = store(kind);
      if (s) s.setItem(key, JSON.stringify(value));
    } catch (e) { /* private mode / quota */ }
  }

  function fsHeaders() {
    var token = "";
    try {
      var s = store("sessionStorage");
      token = (s && s.getItem(TOKEN_KEY)) || "";
      var loc = global.location;
      if (!token && loc && typeof loc.search === "string" && typeof URLSearchParams === "function") {
        token = new URLSearchParams(loc.search).get("t") || "";
      }
    } catch (e) { /* no token available */ }
    return token ? { "X-Keel-Token": token } : {};
  }

  /* ------------------------------------------------------------------ providers */
  function googleParts(content) {
    var parts = [];
    if (typeof content === "string") {
      return content.trim() ? [{ text: content }] : parts;
    }
    if (!Array.isArray(content)) return parts;
    for (var i = 0; i < content.length; i++) {
      var p = content[i];
      if (!p) continue;
      if (p.type === "text" && p.text) parts.push({ text: p.text });
      else if (p.type === "image_url" && p.image_url && p.image_url.url) {
        var m = /^data:([^;]+);base64,(.*)$/.exec(p.image_url.url);
        if (m) parts.push({ inlineData: { mimeType: m[1], data: m[2] } });
      }
    }
    return parts;
  }

  var PROVIDERS = {
    openrouter: {
      name: "openrouter",
      label: "OpenRouter",
      tag: "unified gateway · browser → openrouter.ai",
      hint: "sk-or-.",
      defaultModel: "openrouter/auto",
      verifyUrl: function (key) { return "https://openrouter.ai/api/v1/auth/key"; },
      verifyHeaders: function (key) {
        return assign({ Authorization: "Bearer " + key }, OPENROUTER_ATTRIBUTION);
      },
      catalogUrl: function (key) { return "https://openrouter.ai/api/v1/models"; },
      catalogHeaders: function (key) { return assign({}, OPENROUTER_ATTRIBUTION); },
      parseCatalog: function (doc) {
        return isObject(doc) && Array.isArray(doc.data)
          ? doc.data.map(function (m) { return m && m.id; }) : [];
      },
      chat: function (key, model, messages) {
        return {
          url: "https://openrouter.ai/api/v1/chat/completions",
          init: {
            method: "POST",
            headers: assign({
              Authorization: "Bearer " + key,
              "Content-Type": "application/json"
            }, OPENROUTER_ATTRIBUTION),
            body: JSON.stringify({
              model: model,
              stream: true,
              usage: { include: true },
              messages: messages
            })
          },
          extractDelta: function (evt) {
            return (evt && evt.choices && evt.choices[0] && evt.choices[0].delta &&
              evt.choices[0].delta.content) || "";
          },
          extractUsage: function (evt) {
            if (!evt || !evt.usage) return null;
            return {
              prompt_tokens: evt.usage.prompt_tokens || 0,
              completion_tokens: evt.usage.completion_tokens || 0
            };
          }
        };
      }
    },
    google: {
      name: "google",
      label: "Google AI Studio",
      tag: "gemini · browser → googleapis.com",
      hint: "AIza.",
      defaultModel: "gemini-2.0-flash",
      verifyUrl: function (key) {
        return "https://generativelanguage.googleapis.com/v1beta/models?key=" + encodeURIComponent(key);
      },
      verifyHeaders: function (key) { return {}; },
      catalogUrl: function (key) {
        return "https://generativelanguage.googleapis.com/v1beta/models?key=" + encodeURIComponent(key);
      },
      catalogHeaders: function (key) { return {}; },
      parseCatalog: function (doc) {
        return isObject(doc) && Array.isArray(doc.models)
          ? doc.models.map(function (m) {
              return String((m && m.name) || "").replace(/^models\//, "");
            }) : [];
      },
      chat: function (key, model, messages) {
        var sys = null;
        var convo = [];
        for (var i = 0; i < messages.length; i++) {
          if (messages[i] && messages[i].role === "system") sys = messages[i];
          else convo.push(messages[i]);
        }
        return {
          url: "https://generativelanguage.googleapis.com/v1beta/models/" +
            encodeURIComponent(model) + ":streamGenerateContent?alt=sse&key=" + encodeURIComponent(key),
          init: {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(assign(
              sys ? { systemInstruction: { parts: googleParts(sys.content) } } : {},
              {
                contents: convo.map(function (m) {
                  return {
                    role: m && m.role === "assistant" ? "model" : "user",
                    parts: googleParts(m && m.content)
                  };
                })
              }
            ))
          },
          extractDelta: function (evt) {
            var cand = evt && evt.candidates && evt.candidates[0];
            var parts = (cand && cand.content && cand.content.parts) || [];
            var text = "";
            for (var i = 0; i < parts.length; i++) text += (parts[i] && parts[i].text) || "";
            return text;
          },
          extractUsage: function (evt) {
            if (!evt || !evt.usageMetadata) return null;
            return {
              prompt_tokens: evt.usageMetadata.promptTokenCount || 0,
              completion_tokens: evt.usageMetadata.candidatesTokenCount || 0
            };
          }
        };
      }
    }
  };

  /* ------------------------------------------------------------------ settings */
  function getSettings() {
    return readJSON("localStorage", SETTINGS_KEY, {});
  }

  function getProviders() {
    var s = getSettings();
    return isObject(s.providers) ? s.providers : {};
  }

  function configuredProvider() {
    var p = getProviders();
    if (p.openrouter && p.openrouter.key) return "openrouter";
    if (p.google && p.google.key) return "google";
    return null;
  }

  function providerModel(name) {
    var def = PROVIDERS[name];
    if (!def) return "";
    var s = getSettings();
    var pinned = isObject(s.providerConfig) && isObject(s.providerConfig.models)
      ? s.providerConfig.models[name] : "";
    if (pinned) return String(pinned);
    var p = getProviders()[name];
    if (p && p.model) return String(p.model);
    return def.defaultModel;
  }

  function saveSettings(patch) {
    var current = getSettings();
    patch = isObject(patch) ? patch : {};
    var next = assign({}, current, patch);

    /* deep-merge the nested buckets so a partial patch never discards
       sibling preferences (same shape as app.js saveMirrorSettings). */
    next.ui = assign(isObject(current.ui) ? current.ui : {}, isObject(patch.ui) ? patch.ui : {});

    var curCfg = isObject(current.providerConfig) ? current.providerConfig : {};
    var newCfg = isObject(patch.providerConfig) ? patch.providerConfig : {};
    next.providerConfig = assign({}, curCfg, newCfg);
    next.providerConfig.models = assign(
      isObject(curCfg.models) ? curCfg.models : {},
      isObject(newCfg.models) ? newCfg.models : {}
    );

    var curProviders = isObject(current.providers) ? current.providers : {};
    var newProviders = isObject(patch.providers) ? patch.providers : {};
    var mergedProviders = assign({}, curProviders);
    for (var name in newProviders) {
      if (!Object.prototype.hasOwnProperty.call(newProviders, name)) continue;
      var a = isObject(curProviders[name]) ? curProviders[name] : {};
      var b = isObject(newProviders[name]) ? newProviders[name] : {};
      mergedProviders[name] = assign({}, a, b);
    }
    next.providers = mergedProviders;

    writeJSON("localStorage", SETTINGS_KEY, next);
    return next;
  }

  /* --------------------------------------------------------------------- usage */
  function num(v) {
    var n = Number(v);
    return isFinite(n) && n > 0 ? n : 0;
  }

  function usage() {
    var u = readJSON("sessionStorage", USAGE_KEY, null) || {};
    return { prompts: num(u.prompts), replies: num(u.replies), tokens: num(u.tokens) };
  }

  function bump(kind, amount) {
    try {
      var u = usage();
      u[kind] = (u[kind] || 0) + (amount || 1);
      writeJSON("sessionStorage", USAGE_KEY, u);
    } catch (e) { /* counters are best-effort */ }
  }

  /* --------------------------------------------------------------- key / models */
  async function verifyKey(name, key) {
    var def = PROVIDERS[name];
    if (!def || typeof key !== "string" || !key.trim()) return false;
    var k = key.trim();
    try {
      var resp = await fetch(def.verifyUrl(k), { headers: def.verifyHeaders(k) });
      return !!resp.ok;
    } catch (e) { return false; }
  }

  function bridgeCatalogIds(doc) {
    if (!isObject(doc)) return [];
    if (Array.isArray(doc.models)) return doc.models;
    if (Array.isArray(doc.data)) {
      return doc.data.map(function (m) { return m && (m.id || m.name); });
    }
    return [];
  }

  async function fetchModels(name) {
    var def = PROVIDERS[name];
    if (!def) return [];
    var key = (getProviders()[name] || {}).key || "";
    key = typeof key === "string" ? key : "";

    /* The local Keel bridge ships an offline catalog. The public mirror
       ignores the 404 and falls back to the provider's live catalog. */
    try {
      var res = await fetch("/api/model-catalog/" + encodeURIComponent(name),
        { headers: fsHeaders() });
      if (res.ok) {
        var doc = await res.json();
        var ids = bridgeCatalogIds(doc).filter(Boolean).slice(0, 300);
        if (ids.length) return ids.map(function (id) { return String(id); });
      }
    } catch (e) { /* no bridge — expected on the static mirror */ }

    try {
      var live = await fetch(def.catalogUrl(key), { headers: def.catalogHeaders(key) });
      if (!live.ok) return [];
      var liveDoc = await live.json();
      return def.parseCatalog(liveDoc).filter(Boolean).slice(0, 300)
        .map(function (id) { return String(id); });
    } catch (e) { return []; }
  }

  /* ---------------------------------------------------------------- attachments */
  function fmtBytes(n) {
    n = Number(n) || 0;
    if (n >= 1024 * 1024) return (n / 1048576).toFixed(1) + " MB";
    if (n >= 1024) return Math.round(n / 1024) + " KB";
    return n + " B";
  }

  function toArray(list) {
    var out = [];
    if (!list) return out;
    if (Array.isArray(list)) return list.slice();
    try {
      for (var i = 0; i < list.length; i++) out.push(list[i]);
    } catch (e) { /* not list-like */ }
    return out;
  }

  async function blobToBase64(blob) {
    var bytes = new Uint8Array(await blob.arrayBuffer());
    var bin = "";
    var CHUNK = 0x8000;
    for (var i = 0; i < bytes.length; i += CHUNK) {
      bin += String.fromCharCode.apply(null, bytes.subarray(i, i + CHUNK));
    }
    return global.btoa(bin);
  }

  async function inflateRaw(compressed) {
    var DS = global.DecompressionStream;
    if (typeof DS === "undefined") throw new Error("DecompressionStream unavailable");
    var stream = new Blob([compressed]).stream().pipeThrough(new DS("deflate-raw"));
    return new Uint8Array(await new Response(stream).arrayBuffer());
  }

  /* Minimal ZIP central-directory reader: stored (0) and deflate (8) entries.
     Entries with NUL bytes are treated as binary and reported as skipped. */
  async function unzipEntries(file) {
    var buf = await file.arrayBuffer();
    var b = new Uint8Array(buf);
    var dv = new DataView(buf);
    var eocd = -1;
    for (var i = b.length - 22; i >= Math.max(0, b.length - 22 - 65557); i--) {
      if (i >= 0 && dv.getUint32(i, true) === 0x06054b50) { eocd = i; break; }
    }
    if (eocd < 0) throw new Error("not a zip (no end-of-central-directory record)");

    var total = dv.getUint16(eocd + 10, true);
    var offset = dv.getUint32(eocd + 16, true);
    var out = [];
    var td = typeof TextDecoder === "function" ? new TextDecoder() : null;
    if (!td) throw new Error("TextDecoder unavailable");

    for (var n = 0; n < total && out.length < MAX_FILES; n++) {
      if (offset + 46 > b.length || dv.getUint32(offset, true) !== 0x02014b50) break;
      var method = dv.getUint16(offset + 10, true);
      var compSize = dv.getUint32(offset + 20, true);
      var nameLen = dv.getUint16(offset + 28, true);
      var extraLen = dv.getUint16(offset + 30, true);
      var commentLen = dv.getUint16(offset + 32, true);
      var localOffset = dv.getUint32(offset + 42, true);
      var name = td.decode(b.subarray(offset + 46, offset + 46 + nameLen));
      offset += 46 + nameLen + extraLen + commentLen;
      if (name.charAt(name.length - 1) === "/") continue;

      if (localOffset + 30 > b.length || dv.getUint32(localOffset, true) !== 0x04034b50) {
        out.push({ skip: name + " (bad local header)" });
        continue;
      }
      var lNameLen = dv.getUint16(localOffset + 26, true);
      var lExtraLen = dv.getUint16(localOffset + 28, true);
      var dataStart = localOffset + 30 + lNameLen + lExtraLen;
      var dataEnd = Math.min(b.length, dataStart + compSize);
      try {
        var slice = b.subarray(dataStart, dataEnd);
        var raw = method === 0 ? slice : method === 8 ? await inflateRaw(slice) : null;
        if (!raw) {
          out.push({ skip: name + " (unsupported compression)" });
          continue;
        }
        if (raw.indexOf(0) !== -1) {
          out.push({ skip: name + " (binary entry)" });
          continue;
        }
        var fullName = file.name + "/" + name;
        var text = td.decode(raw);
        if (!TEXT_MIME.test(name) && /[\x00-\x08\x0E-\x1F]/.test(text.slice(0, 512))) {
          out.push({ skip: name + " (binary entry)" });
          continue;
        }
        out.push({ name: fullName, bytes: raw.length, kind: "text", content: text });
      } catch (e) {
        out.push({ skip: name + " (unreadable entry)" });
      }
    }
    return out;
  }

  async function readText(file) {
    if (typeof file.text === "function") return await file.text();
    var FR = global.FileReader;
    if (typeof FR === "undefined") throw new Error("no text reader");
    return await new Promise(function (resolve, reject) {
      try {
        var reader = new FR();
        reader.onload = function () { resolve(String(reader.result || "")); };
        reader.onerror = function () { reject(new Error("read failed")); };
        reader.readAsText(file);
      } catch (e) { reject(e); }
    });
  }

  async function attachFiles(fileList) {
    var files = [];
    var skipped = [];
    var total = 0;
    var list = toArray(fileList);

    for (var i = 0; i < list.length; i++) {
      var f = list[i];
      if (!f || typeof f !== "object") continue;
      var name = String(f.name || "file");
      var size = Number(f.size) || 0;
      try {
        if (size > MAX_BYTES) { skipped.push(name + " (4 MB cap)"); continue; }
        if (total + size > MAX_TOTAL) { skipped.push(name + " (12 MB per-send cap)"); continue; }

        var type = String(f.type || "");
        if (/^image\//i.test(type)) {
          if (files.length >= MAX_FILES) { skipped.push(name + " (8-file cap)"); continue; }
          var data = await blobToBase64(f);
          files.push({ name: name, bytes: size, kind: "image", mime: type, data: data });
          total += size;
          continue;
        }

        var isZip = /\.zip$/i.test(name) || type === "application/zip" ||
          type === "application/x-zip-compressed";
        if (isZip) {
          var entries = await unzipEntries(f);
          if (!entries.length) skipped.push(name + " (zip contained no readable text files)");
          for (var j = 0; j < entries.length; j++) {
            var e = entries[j];
            if (e.skip) { skipped.push(e.skip); continue; }
            if (files.length >= MAX_FILES) { skipped.push(e.name + " (8-file cap)"); continue; }
            if (e.bytes > MAX_BYTES) { skipped.push(e.name + " (4 MB cap)"); continue; }
            if (total + e.bytes > MAX_TOTAL) {
              skipped.push(e.name + " (12 MB per-send cap)");
              continue;
            }
            files.push({ name: e.name, bytes: e.bytes, kind: "text", content: e.content });
            total += e.bytes;
          }
          continue;
        }

        if (files.length >= MAX_FILES) { skipped.push(name + " (8-file cap)"); continue; }
        var text = await readText(f);
        if (text.indexOf("\u0000") !== -1) { skipped.push(name + " (binary file)"); continue; }
        if (!TEXT_MIME.test(type) && /[\x00-\x08\x0E-\x1F]/.test(text.slice(0, 512))) {
          skipped.push(name + " (binary file)");
          continue;
        }
        files.push({ name: name, bytes: size, kind: "text", content: text });
        total += size;
      } catch (e) {
        skipped.push(name + " (unreadable)");
      }
    }
    return { files: files, skipped: skipped };
  }

  function buildPrompt(text, files) {
    var out = text == null ? "" : String(text);
    var textFiles = [];
    var list = toArray(files);
    for (var i = 0; i < list.length; i++) {
      var f = list[i];
      if (f && f.kind !== "image") textFiles.push(f);
    }
    if (!textFiles.length) return out;
    var lines = [];
    for (var j = 0; j < textFiles.length; j++) {
      var item = textFiles[j];
      lines.push("### " + (item && item.name ? String(item.name) : "file") +
        " (" + fmtBytes(item && item.bytes) + ")\n" +
        (item && item.content != null ? String(item.content) : ""));
    }
    return out + "\n\n[Attached files — read-only context]\n" +
      textFiles.length + " file(s)\n" + lines.join("\n\n");
  }

  /* ------------------------------------------------------------------- sending */
  function safeFn(fn) {
    return typeof fn === "function" ? fn : function () {};
  }

  function normalizeMessages(list) {
    var out = [];
    var raw = toArray(list);
    for (var i = 0; i < raw.length; i++) {
      var m = raw[i];
      if (!m || (m.role !== "user" && m.role !== "assistant" && m.role !== "system")) continue;
      if (typeof m.content !== "string" && !Array.isArray(m.content)) continue;
      out.push({ role: m.role, content: m.content });
    }
    return out;
  }

  function normalizeImages(list) {
    var out = [];
    var raw = toArray(list);
    for (var i = 0; i < raw.length; i++) {
      var img = raw[i];
      if (!img) continue;
      if (typeof img === "string") {
        if (/^data:[^;]+;base64,/.test(img)) {
          out.push({ type: "image_url", image_url: { url: img } });
        }
        continue;
      }
      if (img.type === "image_url" && img.image_url && img.image_url.url) {
        out.push({ type: "image_url", image_url: { url: String(img.image_url.url) } });
        continue;
      }
      if (img.data) {
        var data = String(img.data);
        var url = /^data:[^;]+;base64,/.test(data)
          ? data : "data:" + (img.mime || "image/png") + ";base64," + data;
        out.push({ type: "image_url", image_url: { url: url } });
        continue;
      }
      if (img.url) out.push({ type: "image_url", image_url: { url: String(img.url) } });
    }
    return out;
  }

  function foldImages(messages, images) {
    var out = messages.slice();
    var idx = -1;
    for (var i = out.length - 1; i >= 0; i--) {
      if (out[i] && out[i].role === "user") { idx = i; break; }
    }
    var target = idx >= 0 ? out[idx] : { role: "user", content: "" };
    var base = target.content;
    var parts = [];
    if (typeof base === "string" && base.trim()) parts.push({ type: "text", text: base });
    else if (Array.isArray(base)) parts = base.slice();
    for (var j = 0; j < images.length; j++) parts.push(images[j]);
    var updated = { role: "user", content: parts };
    if (idx >= 0) out[idx] = updated;
    else out.push(updated);
    return out;
  }

  function feedSSE(buffer, onEvent) {
    var lines = buffer.value.split("\n");
    buffer.value = lines.pop() || "";
    for (var i = 0; i < lines.length; i++) {
      var line = lines[i].replace(/\r$/, "").trim();
      if (line.indexOf("data:") !== 0) continue;
      var data = line.slice(5).trim();
      if (!data || data === "[DONE]") continue;
      var evt;
      try { evt = JSON.parse(data); } catch (e) { continue; }
      onEvent(evt);
    }
  }

  async function send(opts) {
    opts = isObject(opts) ? opts : {};
    var onDelta = safeFn(opts.onDelta);
    var onDone = safeFn(opts.onDone);
    var onError = safeFn(opts.onError);

    bump("prompts", 1);

    try {
      var providers = getProviders();
      var wanted = typeof opts.provider === "string" && opts.provider !== "auto" &&
        PROVIDERS[opts.provider] ? opts.provider : null;
      var named = wanted && providers[wanted] && providers[wanted].key ? wanted : null;
      var picked = named || configuredProvider();
      if (!picked) {
        bump("replies", 1);
        onError(new Error("no-provider"));
        return;
      }

      var def = PROVIDERS[picked];
      var key = String((providers[picked] || {}).key || "");
      var model = typeof opts.model === "string" && opts.model.trim()
        ? opts.model.trim() : providerModel(picked);
      var messages = normalizeMessages(opts.messages);

      var instructions = opts.instructions;
      if (typeof instructions !== "string") {
        var ui = getSettings().ui;
        instructions = (isObject(ui) && ui.instructions) ? ui.instructions : "";
      }
      instructions = String(instructions).trim();
      if (instructions) {
        messages = [{ role: "system", content: instructions }].concat(messages);
      }

      var images = normalizeImages(opts.images);
      if (images.length) messages = foldImages(messages, images);

      var wire = def.chat(key, model, messages);
      if (!wire || !wire.url || !wire.init) throw new Error("provider-unavailable");

      var full = "";
      var usageInfo = null;
      var handleEvent = function (evt) {
        var delta = "";
        try { delta = wire.extractDelta(evt) || ""; } catch (e) { delta = ""; }
        if (delta) {
          delta = String(delta);
          full += delta;
          onDelta(delta, full);
        }
        var u = null;
        try { u = wire.extractUsage(evt); } catch (e) { u = null; }
        if (u) usageInfo = u;
      };

      var resp = await fetch(wire.url, wire.init);
      if (!resp.ok || !resp.body) {
        var errorText = "";
        try { errorText = await resp.text(); } catch (e) { errorText = ""; }
        throw new Error("http " + resp.status + (errorText ? " - " + errorText.slice(0, 200) : ""));
      }

      if (typeof resp.body.getReader === "function") {
        var reader = resp.body.getReader();
        var decoder = new TextDecoder();
        var buffer = { value: "" };
        for (;;) {
          var chunk = await reader.read();
          if (chunk.done) break;
          buffer.value += decoder.decode(chunk.value, { stream: true });
          feedSSE(buffer, handleEvent);
        }
        buffer.value += decoder.decode();
        if (buffer.value.trim()) feedSSE({ value: buffer.value + "\n" }, handleEvent);
      } else {
        var raw = await resp.text();
        feedSSE({ value: raw.replace(/\r/g, "") + "\n" }, handleEvent);
      }

      if (usageInfo) {
        bump("tokens", (usageInfo.prompt_tokens || 0) + (usageInfo.completion_tokens || 0));
      }
      bump("replies", 1);
      onDone({ provider: picked, model: model, usage: usageInfo || null });
    } catch (err) {
      bump("replies", 1);
      onError(err instanceof Error ? err : new Error(String((err && err.message) || err)));
    }
  }

  if (global) {
    global.KeelChat = {
      PROVIDERS: PROVIDERS,
      getSettings: getSettings,
      saveSettings: saveSettings,
      getProviders: getProviders,
      configuredProvider: configuredProvider,
      providerModel: providerModel,
      verifyKey: verifyKey,
      fetchModels: fetchModels,
      attachFiles: attachFiles,
      buildPrompt: buildPrompt,
      send: send,
      usage: usage
    };
  }
})(typeof window !== "undefined" ? window : this);
