"""Profile management — CRUD for login sessions stored under ~/.ykt-cli/profiles/."""

import json
import os
import re
import shutil
from pathlib import Path

from src.core.config import BASE_DIR

_VALID_NAME_RE = re.compile(r"^[a-zA-Z0-9_\-\u4e00-\u9fff]+$")


def validate_name(name: str) -> str:
    if not name or not _VALID_NAME_RE.match(name):
        raise ValueError(f"无效的账号名称: {name!r}（只允许字母、数字、下划线、连字符、中文）")
    return name


def _profiles_dir() -> Path:
    return BASE_DIR / "profiles"


def _index_path() -> Path:
    return _profiles_dir() / "profiles.json"


def _profile_dir(name: str) -> Path:
    return _profiles_dir() / name


def get_state_path(name: str) -> Path:
    return _profile_dir(name) / "state.json"


def load_index() -> dict:
    path = _index_path()
    if path.exists():
        try:
            return json.loads(path.read_text())
        except (json.JSONDecodeError, KeyError):
            pass
    return {"default": None, "profiles": []}


def _save_index(index: dict) -> None:
    path = _index_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(index, indent=2, ensure_ascii=False))


def create_profile(name: str) -> None:
    validate_name(name)
    pdir = _profile_dir(name)
    pdir.mkdir(parents=True, exist_ok=True)

    profile_data = {"name": name}
    (pdir / "profile.json").write_text(
        json.dumps(profile_data, indent=2, ensure_ascii=False)
    )

    index = load_index()
    if name not in index["profiles"]:
        index["profiles"].append(name)
    if index["default"] is None:
        index["default"] = name
    _save_index(index)


def load_profile(name: str) -> dict | None:
    path = _profile_dir(name) / "profile.json"
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text())
    except json.JSONDecodeError:
        return None


def delete_profile(name: str) -> None:
    pdir = _profile_dir(name)
    if pdir.exists():
        shutil.rmtree(pdir)

    index = load_index()
    if name in index["profiles"]:
        index["profiles"].remove(name)
    if index["default"] == name:
        index["default"] = index["profiles"][0] if index["profiles"] else None
    _save_index(index)


def list_profiles() -> list[str]:
    return load_index()["profiles"]


def save_state(name: str, state: dict) -> None:
    path = get_state_path(name)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, indent=2))
    os.chmod(path, 0o600)


def set_default(name: str) -> None:
    """Set the default profile."""
    index = load_index()
    index["default"] = name
    _save_index(index)


def has_state(name: str) -> bool:
    return get_state_path(name).exists()
