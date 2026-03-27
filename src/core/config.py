"""YAML configuration loading with secret resolution and env var overrides."""

import os
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from src.core.secrets import resolve_secret

BASE_DIR = Path.home() / ".ykt-cli"
DEFAULT_CONFIG_PATH = BASE_DIR / "config.yaml"

DEFAULT_VIDEO = {"speed": 2}

VALID_LOG_LEVELS = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}

CONFIG_TEMPLATE = """\
# ykt-cli 配置文件
# 支持 op:// 引用（需要 1Password 桌面应用）

onepassword:
  account_name: ""  # 你的 1Password 账户，或设置环境变量 OP_ACCOUNT_NAME

openai:
  api_key: ""       # 支持 op:// 引用，如 "op://Personal/DeepSeek/credential"
  base_url: "https://api.deepseek.com/v1"
  model: "deepseek-chat"

video:
  speed: 2          # 视频倍速 1-16

logging:
  level: INFO       # 日志级别：DEBUG / INFO / WARNING / ERROR
  retention_days: 7 # 日志保留天数
"""


def _env_var_name(section: str, field_name: str) -> str:
    return f"YKT_{section.upper()}_{field_name.upper()}"


@dataclass
class YktConfig:
    openai: dict = field(default_factory=dict)
    video: dict = field(default_factory=lambda: dict(DEFAULT_VIDEO))
    account_name: str = ""
    log_level: str = "INFO"
    retention_days: int = 7


async def load_config(config_path: Path | None = None) -> YktConfig:
    path = config_path or DEFAULT_CONFIG_PATH

    if path.exists():
        raw = yaml.safe_load(path.read_text()) or {}
    else:
        raw = {}

    op_section = raw.get("onepassword", {})
    account_name = os.environ.get(
        "OP_ACCOUNT_NAME", op_section.get("account_name", "")
    )

    # Parse logging section (YKT_LOG_LEVEL env var overrides yaml)
    logging_section = raw.get("logging", {})
    log_level = os.environ.get("YKT_LOG_LEVEL", str(logging_section.get("level", "INFO")))
    normalized = log_level.upper()
    if normalized in VALID_LOG_LEVELS:
        log_level = normalized
    else:
        import sys
        print(f"[ykt-cli] 警告: 无效的日志级别 '{log_level}'，回退到 INFO", file=sys.stderr)
        log_level = "INFO"
    try:
        retention_days = max(1, int(logging_section.get("retention_days", 7)))
    except (ValueError, TypeError):
        retention_days = 7

    cfg = YktConfig(
        openai=raw.get("openai", {}),
        video={**DEFAULT_VIDEO, **raw.get("video", {})},
        account_name=account_name,
        log_level=log_level,
        retention_days=retention_days,
    )

    # Resolve secrets in openai section
    for key, value in list(cfg.openai.items()):
        env_key = _env_var_name("openai", key)
        env_val = os.environ.get(env_key)
        if env_val is not None:
            cfg.openai[key] = env_val
        elif isinstance(value, str):
            cfg.openai[key] = await resolve_secret(value, account_name=account_name)

    # Clamp video speed
    speed = cfg.video.get("speed", 2)
    try:
        cfg.video["speed"] = max(1, min(int(speed), 16))
    except (ValueError, TypeError):
        cfg.video["speed"] = 2

    return cfg
