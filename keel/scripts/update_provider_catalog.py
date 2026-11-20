"""Rebuild Keel's compact offline provider/model catalog from models.dev.

Usage (maintainer, with network):
    python scripts/update_provider_catalog.py
    python scripts/update_provider_catalog.py --source /path/to/api.json

The source data is MIT-licensed (Copyright (c) 2025 models.dev). Only provider
metadata and model identifiers are retained; no upstream code is copied. The
generated catalog states its source and attribution. Runtime executability is
NOT implied by a catalog entry.
"""

from __future__ import annotations

import argparse
import json
import urllib.request
from datetime import date
from pathlib import Path

SOURCE_URL = "https://models.dev/api.json"
LICENSE_URL = "https://github.com/anomalyco/models.dev/blob/master/LICENSE"
PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUT = PROJECT_ROOT / "resources" / "catalog" / "providers.json"


def _load(source: str) -> dict:
    if source.startswith(("http://", "https://")):
        with urllib.request.urlopen(source, timeout=60) as response:
            return json.loads(response.read().decode("utf-8"))
    return json.loads(Path(source).read_text(encoding="utf-8"))


def build(source: str, fetched_at: str) -> dict:
    raw = _load(source)
    providers = {}
    model_count = 0
    for key in sorted(raw):
        entry = raw[key]
        models = sorted(str(m) for m in (entry.get("models") or {}))
        model_count += len(models)
        providers[str(key)] = {
            "id": str(entry.get("id") or key),
            "name": str(entry.get("name") or key),
            "doc": str(entry.get("doc") or ""),
            "env": [str(e) for e in (entry.get("env") or [])],
            "api": str(entry.get("api") or ""),
            "models": models,
        }
    return {
        "schema_version": 1,
        "catalog_version": fetched_at,
        "generated_by": "keel.scripts.update_provider_catalog",
        "source": {
            "name": "models.dev",
            "url": SOURCE_URL,
            "license": "MIT",
            "license_url": LICENSE_URL,
            "attribution": "Provider/model data from models.dev, Copyright (c) 2025 models.dev. "
                           "Licensed under MIT. See LICENSE.models-dev.txt.",
        },
        "notice": "Catalog entries are informational only. A listed provider is not "
                  "necessarily executable by Keel; see runtime_adapters in the resolver.",
        "provider_count": len(providers),
        "model_count": model_count,
        "providers": providers,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", default=SOURCE_URL)
    parser.add_argument("--out", default=str(DEFAULT_OUT))
    parser.add_argument("--fetched-at", default=date.today().isoformat())
    args = parser.parse_args()
    doc = build(args.source, args.fetched_at)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(doc, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
                   encoding="utf-8")
    print(f"wrote {out}: {doc['provider_count']} providers, "
          f"{doc['model_count']} model identifiers")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
