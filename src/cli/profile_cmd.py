"""ykt profile — manage login profiles."""

import typer
from src.core import profile as prof
from src import ui

app = typer.Typer(help="管理登录账号")


@app.command("list")
def list_profiles():
    """列出所有账号"""
    index = prof.load_index()
    ui.profile_list(index["profiles"], index["default"])


@app.command()
def create(name: str):
    """创建新账号"""
    try:
        prof.validate_name(name)
    except ValueError as e:
        ui.error(str(e))
        raise typer.Exit(1)
    prof.create_profile(name)
    ui.success(f"已创建账号: {name}")


@app.command()
def delete(name: str):
    """删除指定账号"""
    if not prof.load_profile(name):
        ui.error(f"账号 '{name}' 不存在")
        raise typer.Exit(1)
    prof.delete_profile(name)
    ui.success(f"已删除账号: {name}")


@app.command()
def switch(name: str):
    """切换默认账号"""
    if not prof.load_profile(name):
        ui.error(f"账号 '{name}' 不存在")
        raise typer.Exit(1)
    prof.set_default(name)
    ui.success(f"已切换默认账号为: {name}")
