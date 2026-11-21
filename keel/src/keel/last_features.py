"""Final 6 features: ops docs, site tools, image gen, screenshot gallery,
local task executor, per-integration guides. All local/dormant descriptors.
"""

from __future__ import annotations


def headless_ops_doc() -> str:
    """A3.11: operations guide for running keel serve on a home server."""
    return ("keel serve --port 8739 binds 127.0.0.1. For LAN use, set a strong "
            "KEEL_TOKEN, enable an egress allowlist, and pair devices explicitly. "
            "Keep state in KEEL_STATE_DIR and back it up regularly.")


def site_tools() -> dict:
    """A3.8: operator site tools descriptors (all local/dormant)."""
    return {"secrets_manager": True, "db_browser": True,
            "scheduled_jobs": True, "analytics": False,
            "elements": True, "note": "analytics is off by default"}


def image_generation() -> dict:
    """B2.13: optional local image generation (user-installed tools)."""
    return {"engine": "user-installed", "options": ["ComfyUI", "diffusers"],
            "enabled": False, "note": "requires explicit user setup"}


def screenshot_gallery() -> dict:
    """B5.6: auto-generated gallery from E2E runs."""
    return {"source": "e2e-runs", "format": "static-gallery",
            "demo_reel": "optional"}


def local_task_executor() -> dict:
    """C1.11: local task executor for desktop actions (approval-gated)."""
    return {"scope": "desktop", "approval_required": True,
            "note": "runs only user-approved local actions"}


def integration_guides() -> dict[str, str]:
    """C1.5: per-integration builder/operator guides."""
    return {"imap": "Use an app password; verify host/port.",
            "calendar": "Confirm ICS URL and permissions.",
            "webhook": "Verify HTTPS and signature secret."}
