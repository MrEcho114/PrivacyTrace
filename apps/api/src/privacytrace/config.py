"""Server configuration supporting local and remote modes."""

import os
from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True)
class ServerConfig:
    mode: str = "local"  # "local" | "remote"
    allowed_hosts: list[str] = field(
        default_factory=lambda: ["127.0.0.1", "localhost", "[::1]", "testserver"]
    )
    trusted_proxies: list[str] = field(default_factory=lambda: ["127.0.0.1", "::1"])
    max_json_body_bytes: int = 512 * 1024
    max_draft_body_bytes: int = 8 * 1024 * 1024
    max_apk_body_bytes: int = 150 * 1024 * 1024
    rate_limit_per_minute: int = 60
    max_queue_depth: int = 20

    @classmethod
    def from_env(
        cls,
        store_root: Path | None = None,
        mode: str | None = None,
        allowed_hosts: list[str] | None = None,
        trusted_proxies: list[str] | None = None,
    ) -> "ServerConfig":
        raw_mode = mode if mode is not None else os.environ.get("PRIVACYTRACE_MODE")
        if raw_mode is None or not raw_mode.strip():
            env_mode = "local"
        else:
            env_mode = raw_mode.strip().lower()
            if env_mode not in ("local", "remote"):
                raise ValueError(
                    f"Invalid PRIVACYTRACE_MODE '{raw_mode}': "
                    "allowed values are 'local' or 'remote'"
                )

        if allowed_hosts is not None:
            hosts = list(allowed_hosts)
        else:
            raw_hosts = os.environ.get("PRIVACYTRACE_ALLOWED_HOSTS")
            if raw_hosts is not None:
                hosts = [h.strip() for h in raw_hosts.split(",") if h.strip()]
            else:
                hosts = ["127.0.0.1", "localhost", "[::1]", "testserver"]

        if trusted_proxies is not None:
            proxies = list(trusted_proxies)
        else:
            raw_proxies = os.environ.get("PRIVACYTRACE_TRUSTED_PROXIES")
            if raw_proxies is not None:
                proxies = [p.strip() for p in raw_proxies.split(",") if p.strip()]
            else:
                proxies = ["127.0.0.1", "::1"]

        raw_rate_limit = os.environ.get("PRIVACYTRACE_RATE_LIMIT")
        rate_limit = (
            int(raw_rate_limit)
            if raw_rate_limit and raw_rate_limit.isdigit()
            else 60
        )

        return cls(
            mode=env_mode,
            allowed_hosts=hosts,
            trusted_proxies=proxies,
            rate_limit_per_minute=rate_limit,
        )
