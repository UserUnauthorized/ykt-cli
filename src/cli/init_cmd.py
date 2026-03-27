"""ykt init — generate config template."""

import typer
from src.core.config import DEFAULT_CONFIG_PATH, CONFIG_TEMPLATE
from src import ui


def init():
    """生成配置文件模板到 ~/.ykt-cli/config.yaml"""
    if DEFAULT_CONFIG_PATH.exists():
        ui.warn(f"配置文件已存在: {DEFAULT_CONFIG_PATH}")
        overwrite = typer.confirm("是否覆盖?", default=False)
        if not overwrite:
            return

    DEFAULT_CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    DEFAULT_CONFIG_PATH.write_text(CONFIG_TEMPLATE)
    ui.success(f"配置文件已生成: {DEFAULT_CONFIG_PATH}")
    ui.info("请编辑配置文件填入你的 API Key 等信息")
