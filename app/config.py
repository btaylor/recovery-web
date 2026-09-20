import os
from dataclasses import dataclass

REQUIRED = ("NAVIDROME_URL", "NAVIDROME_USER", "NAVIDROME_PASSWORD")


class ConfigError(RuntimeError):
    pass


@dataclass(frozen=True)
class Config:
    navidrome_url: str
    navidrome_user: str
    navidrome_password: str
    state_dir: str

    @classmethod
    def from_env(cls, env=None) -> "Config":
        env = os.environ if env is None else env
        missing = [k for k in REQUIRED if not env.get(k)]
        if missing:
            raise ConfigError(
                "Missing required environment variables: " + ", ".join(missing)
            )
        return cls(
            navidrome_url=env["NAVIDROME_URL"].rstrip("/"),
            navidrome_user=env["NAVIDROME_USER"],
            navidrome_password=env["NAVIDROME_PASSWORD"],
            state_dir=env.get("STATE_DIR", "./data"),
        )
