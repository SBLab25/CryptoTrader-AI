"""Minimal Vault client wrapper for optional secret loading."""

from functools import lru_cache
from typing import Optional


class VaultClient:
    def __init__(self, addr: str, token: str, path: str = "cryptotrader"):
        try:
            import hvac
        except ImportError as exc:
            raise ImportError("hvac is required when Vault is enabled") from exc

        self._client = hvac.Client(url=addr, token=token)
        if not self._client.is_authenticated():
            raise RuntimeError("Vault authentication failed")

        self._path = path
        self._cache: dict[str, str] = {}
        self.reload()

    def reload(self) -> None:
        response = self._client.secrets.kv.v2.read_secret_version(path=self._path)
        self._cache = response["data"]["data"]

    def get(self, key: str) -> str:
        value = self._cache.get(key)
        if value is None:
            raise KeyError(f"Vault secret not found: {key}")
        return value

    def get_optional(self, key: str, default: str = "") -> str:
        return self._cache.get(key, default)


@lru_cache(maxsize=1)
def get_vault_client(addr: str, token: str) -> Optional[VaultClient]:
    if not addr:
        return None
    return VaultClient(addr=addr, token=token)
