"""Secret resolution: 1Password SDK (DesktopAuth) for op:// references."""

from __future__ import annotations

from onepassword.client import Client, DesktopAuth


class SecretResolutionError(Exception):
    pass


_client: Client | None = None


async def _get_client(account_name: str) -> Client:
    global _client
    if _client is None:
        try:
            _client = await Client.authenticate(
                auth=DesktopAuth(account_name=account_name),
                integration_name="ykt-cli",
                integration_version="0.1.0",
            )
        except Exception as exc:
            raise SecretResolutionError(
                f"1Password authentication failed: {exc}\n"
                "Check: 1Password desktop app > Settings > Developer > "
                "'Integrate with other apps' is enabled."
            ) from exc
    return _client


async def resolve_secret(value: str, account_name: str = "") -> str:
    if not value.startswith("op://"):
        return value

    if not account_name:
        raise SecretResolutionError(
            "op:// reference found but no account_name configured. "
            "Set 'onepassword.account_name' in config or OP_ACCOUNT_NAME env var."
        )

    client = await _get_client(account_name)
    try:
        return await client.secrets.resolve(value)
    except Exception as exc:
        raise SecretResolutionError(f"Failed to resolve {value}: {exc}") from exc
