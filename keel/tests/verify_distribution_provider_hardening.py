"""Distribution round — provider/permission/browser-surface hardening (static).

The native packaging, PWA service worker and browser mirrors are inspected as
shipped source. No provider credential is used and no network call is made.
These checks guard the distribution change itself: it must not add a provider,
bake in a key, auto-trust a workspace, weaken permissions, or let the public
mirror reach desktop-only bridge routes.

Run with:  $env:PYTHONPATH='src'; python -m pytest tests/verify_distribution_provider_hardening.py -q
"""

from __future__ import annotations

import re
from pathlib import Path

from keel import settings_store
from keel.providers import registry as provider_registry

ROOT = Path(__file__).resolve().parents[1]


def _read(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


# --------------------------------------------------------------------------
# 1. Provider set is unchanged; nothing is baked in or silently provisioned
# --------------------------------------------------------------------------

def test_provider_registry_is_unchanged_and_has_no_baked_credentials():
    expected = {"openrouter", "google", "nvidia", "anthropic",
                "openai-compatible"}
    assert set(provider_registry._PROVIDERS) == expected
    assert provider_registry._AUTO_CHAIN == (
        "openrouter", "google", "nvidia", "openai-compatible")
    for name, cap in provider_registry._PROVIDERS.items():
        assert cap.env_var.startswith("KEEL_") and cap.env_var.endswith("_KEY")
        assert cap.base_url.startswith("https://") or not cap.base_url
    # Anthropic stays opt-in (never auto-selected).
    assert "anthropic" not in provider_registry._AUTO_CHAIN
    source = _read("src/keel/providers/registry.py")
    assert "opt_in" in source and 'name == "anthropic"' in source
    assert "sk-" not in source
    assert not re.search(r"os\.environ\[[^]]+\]\s*=\s*['\"]", source)


def test_export_and_public_view_never_include_secret_values(monkeypatch):
    doc = {"providerKeys": {"openrouter": {"key": "sk-fixture-secret-1234",
                                           "hint": "1234",
                                           "enc": "aes256gcm-v1"}},
           "ui": {"theme": "dark"},
           "providerConfig": {"preferred": "openrouter"}}
    monkeypatch.setattr(settings_store, "load", lambda: doc)
    assert "providerKeys" not in settings_store.export_view()
    view = settings_store.public_view(doc)
    assert "key" not in view["providerKeys"]["openrouter"]
    assert view["providerKeys"]["openrouter"]["hint"] == "1234"
    assert "sk-fixture" not in str(view)


# --------------------------------------------------------------------------
# 2. Native packaging does not inject providers, keys, trust or permissions
# --------------------------------------------------------------------------

def test_electron_shell_has_no_provider_or_trust_side_effects():
    main = _read("desktop-app/main.js")
    for forbidden in ("API_KEY", "providerKeys", "settings.json",
                      "/trust", "trusted", "autopilot", "acceptEdits",
                      "providers/credential", "providers/save"):
        assert forbidden not in main, forbidden
    # The only environment reads that affect startup are the UI override and
    # the update-signing key path; neither creates a provider or a key.
    assert "KEEL_UI_PROFILE" in main
    assert "KEEL_UI_DIR" in main
    assert 'join(res, "desktop", "ui")' in main
    # Loopback is validated; non-loopback links leave the renderer.
    assert 'parsed.hostname === "127.0.0.1"' in main
    assert 'url.protocol !== "http:" || url.hostname !== "127.0.0.1"' in main
    assert "shell.openExternal(url)" in main


def test_packaged_ui_prefers_full_local_ui_and_mirror_is_explicit_only():
    main = _read("desktop-app/main.js")
    mirror_branch = main.split('KEEL_UI_PROFILE', 1)[1].split('candidates', 1)[0]
    assert '=== "mirror"' in mirror_branch
    assert 'join(res, "site")' in mirror_branch  # diagnostic rollback only
    pkg = _read("desktop-app/package.json")
    assert '"from": "../desktop/ui"' in pkg
    assert '"to": "desktop/ui"' in pkg


def test_service_worker_caches_shell_only_not_binaries_or_manifests():
    sw = _read("desktop/sw.js")
    assert 'const VERSION = "keel-shell-v6"' in sw
    assert 'url.pathname.startsWith("/api/")' in sw  # API is network-only
    assert 'url.origin !== location.origin' in sw
    shell = sw.split("const SHELL = [", 1)[1].split("];", 1)[0]
    for entry in ("/", "/ui/index.html", "/ui/style.css", "/ui/app.js",
                  "/ui/management.js", "/manifest.webmanifest"):
        assert f'"{entry}"' in shell
    for forbidden in (".exe", ".msi", ".dmg", ".deb", ".rpm", "RELEASE-",
                      "download", "api/"):
        assert forbidden not in shell, forbidden


# --------------------------------------------------------------------------
# 3. Browser storage never holds privileged provider credentials
# --------------------------------------------------------------------------

def test_full_app_browser_storage_has_no_provider_or_token_keys():
    forbidden = re.compile(r"(?i)(api[_-]?key|secret|credential|token|provider)")
    for path in sorted((ROOT / "fleet-next").rglob("*")):
        if (path.suffix not in (".ts", ".tsx")
                or "tests" in path.parts
                or "node_modules" in path.parts
                or ".next" in path.parts):
            continue
        for lineno, line in enumerate(
                path.read_text(encoding="utf-8", errors="ignore").splitlines(), 1):
            if "localStorage.setItem" in line:
                assert not forbidden.search(line), (
                    f"{path.relative_to(ROOT)}:{lineno}: {line.strip()}")

    desktop_ui = _read("desktop/ui/app.js")
    for line in desktop_ui.splitlines():
        if "localStorage.setItem" in line:
            assert not forbidden.search(line), line.strip()
    # Provider keys go to the bridge; only the local bridge token is ephemeral.
    assert 'fetchJson("/api/fleet/providers/save"' in desktop_ui
    assert 'sessionStorage.setItem("keel_token", token)' in desktop_ui


def test_public_mirror_has_no_desktop_only_api_calls_or_bridge_keys():
    ui = _read("site/ui/app.js")
    html = _read("site/app.html")
    assert "PUBLIC MIRROR" in html.upper()
    for forbidden in ("/api/fleet/", "providers/credential", "providers/save",
                      "providers/remove", "projects/", "bots/", "terminal/exec"):
        assert forbidden not in ui, forbidden
    # The mirror's own (browser-only, user-entered) keys live in one named
    # store; it never reads the bridge's privileged settings file or token
    # from localStorage. Its bridge token, when locally served, is session-only.
    assert 'MIRROR_SETTINGS_KEY = "keel_mirror_settings_v1"' in ui
    assert 'sessionStorage.getItem("keel_token")' in ui
    assert "keel_mirror_settings_v1" not in _read("desktop/ui/app.js")
    assert "keel_mirror_settings_v1" not in _read(
        "fleet-next/features/onboarding/Onboarding.tsx")


def test_bff_never_forwards_browser_cookies_or_invents_credentials():
    bff = _read("fleet-next/app/api/bridge/[...path]/route.ts")
    for header in ("host", "connection", "cookie", "origin", "referer"):
        assert f'headers.delete("{header}")' in bff
    assert 'headers.set("x-keel-token", BRIDGE_TOKEN)' in bff
    assert "process.env.KEEL_BRIDGE_TOKEN" in bff
    assert 'error: "bridge_unavailable"' in bff
    assert "sk-" not in bff
