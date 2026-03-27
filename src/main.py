"""ykt-cli: 雨课堂平台 CLI 工具"""

import os

import typer

from src.cli.init_cmd import init
from src.cli.login import login
from src.cli.profile_cmd import app as profile_app
from src.cli.run import run
from src.cli.slide import slide
from src import ui

app = typer.Typer(
    name="ykt",
    help="雨课堂平台 CLI 工具",
    no_args_is_help=False,
    invoke_without_command=True,
)

app.command()(init)
app.command()(login)
app.add_typer(profile_app, name="profile")
app.command()(run)
app.command()(slide)


def _invoke_command(ctx: typer.Context, name: str, **kwargs) -> None:
    """Invoke a registered Typer command by name with proper parameter resolution."""
    click_cmd = typer.main.get_command(app).get_command(ctx, name)
    ctx.invoke(click_cmd, **kwargs)


@app.callback(invoke_without_command=True)
def main(
    ctx: typer.Context,
    debug: bool = typer.Option(False, "--debug", help="启用调试模式"),
):
    """雨课堂平台 CLI 工具"""
    debug = debug or os.environ.get("YKT_DEBUG", "").lower() in ("1", "true")
    ctx.ensure_object(dict)
    ctx.obj["debug"] = debug

    if ctx.invoked_subcommand is not None:
        return

    # Interactive mode
    ui.banner()
    action = ui.main_menu()

    if action == "run":
        _invoke_command(ctx, "run")
    elif action == "slide":
        _invoke_command(ctx, "slide")
    elif action == "profile":
        from src.cli.profile_cmd import list_profiles
        ctx.invoke(list_profiles)
    elif action == "exit":
        ui.info("再见！")


if __name__ == "__main__":
    app()
