from app.providers.base import BaseProvider
from app.providers.mock import MockProvider
from app.providers.generic_playwright import GenericPlaywrightProvider

_PROVIDERS: dict[str, type[BaseProvider]] = {
    "mock": MockProvider,
    "generic_playwright": GenericPlaywrightProvider,
}


def get_provider(name: str) -> BaseProvider:
    cls = _PROVIDERS.get(name)
    if cls is None:
        raise ValueError(f"Unknown provider: {name}. Available: {list(_PROVIDERS.keys())}")
    return cls()


def register_provider(name: str, cls: type[BaseProvider]) -> None:
    _PROVIDERS[name] = cls


def list_providers() -> list[str]:
    return list(_PROVIDERS.keys())
