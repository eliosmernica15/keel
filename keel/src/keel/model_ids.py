"""Consistent provider/model identifier parsing."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ModelRef:
    provider: str | None
    model: str
    raw: str

    @property
    def qualified(self) -> str:
        return f"{self.provider}/{self.model}" if self.provider else self.model


class ModelIdError(ValueError):
    pass


def parse_model_ref(value: str) -> ModelRef:
    if not isinstance(value, str) or not value.strip():
        raise ModelIdError("model identifier must be a non-empty string")
    raw = value.strip()
    if "/" in raw:
        provider, model = raw.split("/", 1)
        provider, model = provider.strip().lower(), model.strip()
        if not provider or not model:
            raise ModelIdError(
                f"invalid provider/model identifier {raw!r}: both parts are required")
        return ModelRef(provider=provider, model=model, raw=raw)
    return ModelRef(provider=None, model=raw, raw=raw)
