"""Rich terminal UI components — banner, messages, menus, progress bars."""

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from rich import box

console = Console()

BRAND = "[bold cyan]⚡ YKT-CLI[/bold cyan]"


def banner():
    console.print(Panel(BRAND, border_style="cyan", expand=False, padding=(0, 4)))


def info(msg: str):
    console.print(f"  [cyan]▸[/cyan] {msg}")


def success(msg: str):
    console.print(f"  [green]✓[/green] {msg}")


def warn(msg: str):
    console.print(f"  [yellow]⚠[/yellow] {msg}")


def error(msg: str):
    console.print(f"  [red]✗[/red] {msg}")


def section(title: str):
    console.rule(f"[bold]{title}[/bold]", style="dim")


# --- Unit table ---

def unit_table(units, show_all=False):
    from src.run.navigator import is_completed

    table = Table(box=box.ROUNDED, border_style="dim", show_header=False, padding=(0, 1))
    table.add_column("状态", width=2)
    table.add_column("名称")
    table.add_column("进度", justify="right", style="dim")

    for u in units:
        done = is_completed(u)
        if done:
            icon = "[green]✓[/green]"
            style = "dim"
        elif u.status in ("未开始", "未读"):
            icon = "[dim]○[/dim]"
            style = "dim"
        else:
            icon = "[yellow]▸[/yellow]"
            style = ""

        if not show_all and done:
            continue
        table.add_row(icon, Text(u.name, style=style), u.status)

    if table.row_count > 0:
        console.print(table)


# --- Video progress ---

_live = None
_live_started = False


def _render_video_bar(current: float, duration: float, speed: int, completion: str, paused: bool) -> Text:
    bar_width = 30
    pct = current / duration if duration > 0 else 0
    filled = int(pct * bar_width)
    bar = '█' * filled + '░' * (bar_width - filled)
    icon = '⏸' if paused else '▶'
    line = f"  {icon} {bar} {pct*100:.0f}% │ {speed}x │ {current:.0f}s/{duration:.0f}s  {completion}"
    text = Text(line)
    text.stylize("yellow" if paused else "green", 2, 3)
    text.stylize("cyan", 4, 4 + filled)
    text.stylize("dim", 4 + filled, 4 + bar_width)
    return text


def video_progress(current: float, duration: float, speed: int, completion: str, paused: bool):
    global _live, _live_started
    from rich.live import Live

    renderable = _render_video_bar(current, duration, speed, completion, paused)
    if _live is None:
        _live = Live(renderable, console=console, refresh_per_second=4, transient=True)
    else:
        _live.update(renderable)

    if not _live_started:
        _live.start()
        _live_started = True


def video_progress_stop():
    global _live, _live_started
    if _live and _live_started:
        _live.stop()
        _live = None
        _live_started = False


# --- Quiz UI ---

def quiz_detected():
    console.print(f"\n  [bold magenta]🧠 检测到题目![/bold magenta]")


def quiz_info(q_type: str, question: str, options: list[dict]):
    console.print(f"    [dim]类型:[/dim] {q_type}")
    console.print(f"    [dim]题干:[/dim] {question}")
    for opt in options:
        console.print(f"    [dim]{opt['key']}.[/dim] {opt['text']}")


def quiz_answer(keys: list[str], is_retry=False):
    label = "重试" if is_retry else "AI"
    console.print(f"    [cyan]→ {label}答案: [bold]{','.join(keys)}[/bold][/cyan]")


def quiz_result(correct: bool):
    if correct:
        console.print(f"    [green]✓ 回答正确[/green]")
    else:
        console.print(f"    [yellow]⚠ 回答错误[/yellow]")


def quiz_skip():
    console.print(f"    [dim]已用完重试次数，继续播放[/dim]")


# --- Profile menus ---

def profile_menu(profiles: list[str], default: str | None) -> str | None:
    console.print()
    console.print(f"  [bold]请选择账号:[/bold]")
    for i, name in enumerate(profiles):
        label = " (默认)" if name == default else ""
        console.print(f"    [cyan]{i + 1}.[/cyan] {name}{label}")
    new_idx = len(profiles) + 1
    console.print(f"    [cyan]{new_idx}.[/cyan] [dim]+ 创建新账号[/dim]")

    console.print()
    while True:
        choice = console.input("  输入序号或名称: ").strip()
        if not choice:
            continue
        try:
            idx = int(choice) - 1
            if idx == len(profiles):
                return None
            if 0 <= idx < len(profiles):
                return profiles[idx]
        except ValueError:
            pass
        if choice in profiles:
            return choice
        console.print("  [red]无效输入，请重试[/red]")


def prompt_new_profile() -> str:
    console.print()
    name = console.input("  输入账号名称: ").strip()
    while not name:
        name = console.input("  名称不能为空，请重新输入: ").strip()
    return name


def profile_info(name: str):
    console.print(f"  [cyan]▸[/cyan] 账号: [bold]{name}[/bold]")


def profile_list(profiles: list[str], default: str | None):
    if not profiles:
        console.print("  [dim]暂无已保存的账号[/dim]")
        return
    for name in profiles:
        label = " [green](默认)[/green]" if name == default else ""
        console.print(f"  [cyan]•[/cyan] {name}{label}")


# --- Course menus ---

def term_menu(grouped: dict) -> int:
    from src.run.course import term_label

    terms = list(grouped.keys())
    console.print()
    console.print("  [bold]请选择学期:[/bold]")
    for i, term in enumerate(terms):
        count = len(grouped[term])
        console.print(f"    [cyan]{i + 1}.[/cyan] {term_label(term)} ({count}门课)")

    console.print()
    while True:
        choice = console.input("  输入序号: ").strip()
        try:
            idx = int(choice) - 1
            if 0 <= idx < len(terms):
                return terms[idx]
        except ValueError:
            pass
        console.print("  [red]无效输入，请重试[/red]")


def course_menu(courses: list[dict]) -> dict:
    table = Table(box=box.ROUNDED, border_style="dim", padding=(0, 1))
    table.add_column("#", style="cyan", width=3)
    table.add_column("课程名")
    table.add_column("教师")
    table.add_column("班级编号", style="dim")

    for i, c in enumerate(courses):
        table.add_row(str(i + 1), c["course"]["name"], c["teacher"]["name"], c["name"])

    console.print()
    console.print(table)
    console.print()
    while True:
        choice = console.input("  输入序号: ").strip()
        try:
            idx = int(choice) - 1
            if 0 <= idx < len(courses):
                return courses[idx]
        except ValueError:
            pass
        console.print("  [red]无效输入，请重试[/red]")


# --- Interactive main menu ---

def main_menu() -> str:
    console.print()
    console.print("  [bold]请选择操作:[/bold]")
    console.print("    [cyan]1.[/cyan] 自动刷课")
    console.print("    [cyan]2.[/cyan] 下载课件")
    console.print("    [cyan]3.[/cyan] 管理账号")
    console.print("    [cyan]4.[/cyan] 退出")

    console.print()
    actions = {"1": "run", "2": "slide", "3": "profile", "4": "exit"}
    while True:
        choice = console.input("  输入序号: ").strip()
        if choice in actions:
            return actions[choice]
        console.print("  [red]无效输入，请重试[/red]")


# --- Checkbox multi-select ---


def _parse_selection(text: str, total: int) -> list[int]:
    """Parse user selection like '1,3-5,7' or 'a' into sorted index list."""
    text = text.strip()
    if text.lower() == "a":
        return list(range(total))
    indices: set[int] = set()
    for part in text.split(","):
        part = part.strip()
        if not part:
            continue
        if "-" in part:
            bounds = part.split("-", 1)
            try:
                lo, hi = int(bounds[0]), int(bounds[1])
                for n in range(lo, hi + 1):
                    if 1 <= n <= total:
                        indices.add(n - 1)
            except ValueError:
                pass
        else:
            try:
                n = int(part)
                if 1 <= n <= total:
                    indices.add(n - 1)
            except ValueError:
                pass
    return sorted(indices)


async def lesson_checkbox_menu(items: list[dict]) -> list[int]:
    """Table-based lesson selector. Returns sorted list of selected indices."""
    if not items:
        return []

    table = Table(box=box.ROUNDED, border_style="dim", padding=(0, 1))
    table.add_column("#", style="cyan", width=4)
    table.add_column("课时名称")
    table.add_column("日期", style="dim", justify="right")

    for i, item in enumerate(items):
        table.add_row(str(i + 1), item.get("title", ""), item.get("date", ""))

    console.print()
    console.print(table)
    console.print()
    console.print("  [dim]输入序号选择，支持: 1,3,5 | 2-6 | a(全选)[/dim]")
    console.print()

    while True:
        choice = console.input("  选择课时: ").strip()
        if not choice:
            continue
        result = _parse_selection(choice, len(items))
        if result:
            success(f"已选择 {len(result)} 个课时")
            return result
        console.print("  [red]无效输入，请重试[/red]")
