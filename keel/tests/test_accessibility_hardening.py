"""Static accessibility hardening checks for the Keel browser mirror.

Local self-check only.  These tests parse ``site/app.html`` and
``site/ui/style.css`` with the standard library (no browser, no axe, no
external dependencies).  They guard a small set of concrete,
regression-prone defects found during a manual review:

  * every button / form control has an accessible name;
  * landmarks, language and a keyboard skip link are present;
  * focus indicators exist and are not suppressed;
  * streaming/status text is exposed through aria-live regions;
  * div-as-controls are actually keyboard operable;
  * the known colour tokens meet a 4.5:1 spot check and no raw
    dark-theme-only hex survives on controls that render in light theme;
  * reduced-motion support is present;
  * no duplicate ids or duplicate HTML attributes.

This is NOT a formal WCAG conformance audit.  It does not exercise a real
screen reader, compute computed styles for nested translucent layers, or
verify focus management inside JavaScript-opened modal dialogs.
"""

from __future__ import annotations

import re
from collections import Counter
from html.parser import HTMLParser
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HTML_PATH = ROOT / "site" / "app.html"
CSS_PATH = ROOT / "site" / "ui" / "style.css"

HTML_TEXT = HTML_PATH.read_text(encoding="utf-8")
CSS_TEXT = CSS_PATH.read_text(encoding="utf-8")

VOID_TAGS = {
    "area", "base", "br", "col", "embed", "hr", "img", "input", "link",
    "meta", "param", "source", "track", "wbr",
}


class Element:
    """A very small DOM-like node: tag, raw attrs and descendant text."""

    def __init__(self, tag: str, attrs: list[tuple[str, str | None]], parent: "Element | None"):
        self.tag = tag
        self.raw_attrs = attrs
        self.attrs = {key: (value or "") for key, value in attrs}
        self.parent = parent
        self.text: list[str] = []

    def attr(self, name: str) -> str:
        return self.attrs.get(name, "").strip()


class MarkupParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.elements: list[Element] = []
        self._stack: list[Element] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        parent = self._stack[-1] if self._stack else None
        node = Element(tag, attrs, parent)
        self.elements.append(node)
        if tag not in VOID_TAGS:
            self._stack.append(node)

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        parent = self._stack[-1] if self._stack else None
        self.elements.append(Element(tag, attrs, parent))

    def handle_endtag(self, tag: str) -> None:
        for index in range(len(self._stack) - 1, -1, -1):
            if self._stack[index].tag == tag:
                del self._stack[index:]
                return

    def handle_data(self, data: str) -> None:
        # Attribute text to every open ancestor so a button "contains" the
        # text of its nested <span>/<svg> children, as accname does.
        for node in self._stack:
            node.text.append(data)


PARSER = MarkupParser()
PARSER.feed(HTML_TEXT)
BY_ID = {node.attr("id"): node for node in PARSER.elements if node.attr("id")}


def accessible_name(node: Element) -> str:
    """Simplified accname: aria-label -> aria-labelledby -> text -> title -> alt."""
    if node.attr("aria-label"):
        return node.attr("aria-label")
    refs = node.attr("aria-labelledby").split()
    if refs:
        names = [accessible_name(BY_ID[ref]) for ref in refs if ref in BY_ID]
        if any(names):
            return " ".join(names)
    text = " ".join(" ".join(node.text).split())
    if text:
        return text
    return node.attr("title") or node.attr("alt")


# A naive but sufficient CSS rule scanner (the stylesheet has no nested
# braces inside declaration blocks).  Strip comments first: several rules are
# immediately preceded by a /* section heading */, which would otherwise be
# captured as part of the selector.
CSS_CLEAN = re.sub(r"/\*.*?\*/", "", CSS_TEXT, flags=re.S)
RULES = re.findall(r"([^{}]+)\{([^{}]*)\}", CSS_CLEAN)


def rule_body(selector: str) -> str | None:
    for sel, body in RULES:
        if sel.strip() == selector:
            return body
    return None


# ---------------------------------------------------------------------------
# accessible names
# ---------------------------------------------------------------------------


def test_every_button_has_an_accessible_name() -> None:
    buttons = [node for node in PARSER.elements if node.tag == "button"]
    assert buttons, "expected buttons in app.html"
    unnamed = [node.attr("id") or node.attr("class") or "?" for node in buttons
               if not accessible_name(node)]
    assert not unnamed, f"buttons without accessible name: {unnamed}"


def test_form_controls_have_labels_or_aria_names() -> None:
    controls = [
        node for node in PARSER.elements
        if node.tag in {"input", "select", "textarea"}
        and node.attr("type") != "hidden"
        and "hidden" not in node.attrs
        and node.attr("aria-hidden") != "true"
    ]
    assert controls

    def labelled(node: Element) -> bool:
        if accessible_name(node):
            return True
        ancestor = node.parent
        while ancestor is not None:
            if ancestor.tag == "label":
                return True
            ancestor = ancestor.parent
        return any(label.attr("for") == node.attr("id")
                   for label in PARSER.elements if label.tag == "label")

    unnamed = [(node.tag, node.attr("id")) for node in controls if not labelled(node)]
    assert not unnamed, f"form controls without a label: {unnamed}"


# ---------------------------------------------------------------------------
# landmarks / document structure
# ---------------------------------------------------------------------------


def test_landmarks_language_and_skip_link() -> None:
    assert '<html lang="en">' in HTML_TEXT
    assert "<title>" in HTML_TEXT
    for tag in ("main", "nav", "aside", "footer", "h1"):
        assert any(node.tag == tag for node in PARSER.elements), f"missing <{tag}>"

    main = next(node for node in PARSER.elements if node.tag == "main")
    assert main.attr("id") == "main-content"
    skip = [node for node in PARSER.elements
            if node.tag == "a" and "skip-link" in node.attr("class")]
    assert len(skip) == 1
    assert skip[0].attr("href") == "#main-content"
    assert skip[0].attr("aria-label") or accessible_name(skip[0])

    assert 'role="tablist"' in HTML_TEXT
    assert HTML_TEXT.count('role="tabpanel"') >= 2
    # named tabpanels (settings panes) — unnamed panels are confusing to SRs
    panes = [node for node in PARSER.elements if node.attr("role") == "tabpanel"]
    assert panes and all(accessible_name(node) for node in panes)


def test_no_duplicate_ids_or_attributes() -> None:
    ids = [node.attr("id") for node in PARSER.elements if node.attr("id")]
    duplicates = sorted(key for key, count in Counter(ids).items() if count > 1)
    assert not duplicates, f"duplicate ids: {duplicates}"
    for node in PARSER.elements:
        keys = [key for key, _ in node.raw_attrs]
        bad = sorted(key for key, count in Counter(keys).items() if count > 1)
        assert not bad, f"<{node.tag}> has duplicate attributes: {bad}"


# ---------------------------------------------------------------------------
# focus visibility
# ---------------------------------------------------------------------------


def test_focus_indicators_are_defined_and_not_suppressed() -> None:
    focus_rules = [(sel.strip(), body) for sel, body in RULES if ":focus-visible" in sel]
    assert any(sel == ":focus-visible" for sel, _ in focus_rules), "no global :focus-visible rule"
    for sel, body in focus_rules:
        assert not re.search(r"outline\s*:\s*(none|0\b)", body), f"{sel} suppresses outline"
        has_outline = re.search(r"outline\s*:\s*(?!none\b|0\b)", body)
        assert has_outline or "box-shadow" in body, f"{sel} has no visible focus indicator"
    # skip link must actually appear when focused
    assert rule_body(".skip-link:focus") is not None
    assert "top: 8px" in (rule_body(".skip-link:focus") or "")
    # inputs that used to zero their outline now inherit the global ring
    for selector in ("#prompt-chat", ".comp input", ".rail-search input",
                     "#instructions", ".pop-search", ".model-filter"):
        body = rule_body(selector)
        assert body is not None, selector
        assert not re.search(r"outline\s*:\s*(none|0\b)", body), selector


# ---------------------------------------------------------------------------
# live regions
# ---------------------------------------------------------------------------


def test_streaming_and_status_live_regions_present() -> None:
    for thread_id in ("thread-chat", "thread-code"):
        assert BY_ID[thread_id].attr("aria-live") == "polite"
    live = BY_ID["a11y-live-region"]
    assert live.attr("role") == "status"
    assert live.attr("aria-live") == "polite"
    assert live.attr("aria-atomic") == "true"
    assert rule_body(".a11y-live") is not None, "live region must be visually hidden in CSS"


# ---------------------------------------------------------------------------
# keyboard operability
# ---------------------------------------------------------------------------


def test_controls_are_keyboard_operable() -> None:
    # sidebar commands were href-less <a> elements: Enter never fired click.
    for command in ("nav-new", "nav-customize", "nav-tutorial"):
        assert BY_ID[command].tag == "button", command
        assert BY_ID[command].attr("type") == "button", command

    # submenu triggers used to be hover-only <div>s; focus-within needs a
    # focusable element to reveal their flyouts from the keyboard.
    for submenu in ("ctx-sub-open", "ctx-sub-section", "ctx-sub-project", "ctx-sub-group"):
        node = BY_ID[submenu]
        assert node.attr("tabindex") == "0", submenu
        assert node.attr("role") == "menuitem", submenu
        assert node.attr("aria-haspopup") == "menu", submenu

    # permission modes were clickable <div>s with no tab stop.
    perms = [node for node in PARSER.elements
             if "pop-item" in node.attr("class")
             and node.parent is not None and node.parent.attr("id") == "pop-perm"]
    assert len(perms) == 3
    assert all(node.tag == "button" and node.attr("type") == "button" for node in perms)

    assert not re.search(r"\son(?:click|keydown|keyup|mouseover)\s*=", HTML_TEXT, re.I)
    for node in PARSER.elements:
        if node.attr("role") == "button":
            assert node.attr("tabindex") == "0" or node.tag in {"button", "a"}


def test_dialogs_and_popups_have_accessible_names() -> None:
    dialogs = [node for node in PARSER.elements if node.attr("role") == "dialog"]
    assert len(dialogs) >= 5, "expected settings/picker/tour/modal dialogs"
    assert all(accessible_name(node) for node in dialogs)
    for chip in ("chip-env", "chip-folder", "chip-perm"):
        assert BY_ID[chip].attr("aria-haspopup") == "dialog", chip


# ---------------------------------------------------------------------------
# colour / motion
# ---------------------------------------------------------------------------


def _luminance(hex_colour: str) -> float:
    value = hex_colour.lstrip("#")
    channels = [int(value[i:i + 2], 16) / 255 for i in (0, 2, 4)]

    def linearise(channel: float) -> float:
        return channel / 12.92 if channel <= 0.03928 else ((channel + 0.055) / 1.055) ** 2.4

    r, g, b = map(linearise, channels)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def _contrast(foreground: str, background: str) -> float:
    a, b = _luminance(foreground), _luminance(background)
    return (max(a, b) + 0.05) / (min(a, b) + 0.05)


def test_known_colour_tokens_meet_spot_check() -> None:
    pairs = [
        ("dark body text", "#f2f0ea", "#0a0605"),
        ("dark muted text", "#8a8279", "#0a0605"),
        ("light body text", "#241f1a", "#f7f4ef"),
        ("light muted text", "#6f685f", "#f7f4ef"),
        ("dark on-accent", "#171310", "#e6d54c"),
        ("light on-accent", "#f7f2e6", "#8a5a07"),
        ("light danger", "#c2432c", "#f7f4ef"),
    ]
    for name, foreground, background in pairs:
        ratio = _contrast(foreground, background)
        assert ratio >= 4.5, f"{name}: {ratio:.2f}:1 is below 4.5:1"


def test_no_dark_theme_only_hex_on_shared_controls() -> None:
    guards = [
        r"\.send\s*\{[^}]*color:\s*var\(--text\)",
        r"\.foot button\s*\{[^}]*color:\s*var\(--text\)",
        r"\.tag\s*\{[^}]*color:\s*var\(--text\)",
        r"\.caps-actions button\s*\{[^}]*color:\s*var\(--on-accent\)",
        r"\.approval-actions \.btn-approve\s*\{[^}]*color:\s*var\(--on-accent\)",
        r"\.ctx-item\.danger\s*\{[^}]*color:\s*var\(--danger\)",
        r"\.tour-status\s*\{color:\s*var\(--danger\)",
        r"\.btn-stop\s*\{[^}]*color:\s*var\(--danger\)",
    ]
    for pattern in guards:
        assert re.search(pattern, CSS_TEXT), f"missing themed colour: {pattern}"
    for raw in ("#f7f3e8", "#f0b9a8", "#f7cdbf", "#ddd8c4", "#cfc9bd"):
        assert raw not in CSS_TEXT, f"dark-only colour survived: {raw}"
    assert not re.search(r"color\s*:\s*#000\b", CSS_TEXT)


def test_reduced_motion_is_supported() -> None:
    assert "@media (prefers-reduced-motion: reduce)" in CSS_TEXT
    assert "body.reduce-motion" in CSS_TEXT
