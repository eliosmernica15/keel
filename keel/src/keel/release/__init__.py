"""Python-controlled release automation for Keel installers.

Public commands:

    python -m keel.release build
    python -m keel.release publish
    python -m keel.release verify

Distribution uses GitHub Releases attached to the existing repository. No
third-party storage provider is introduced; the Vercel site is unchanged and
only links to release assets.
"""

from __future__ import annotations

__all__ = ["__version__"]

__version__ = "0.1.0"
