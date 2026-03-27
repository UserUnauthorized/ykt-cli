"""YuKeTang HTTP API client for courses, lessons, and presentations."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta

import httpx

from src.core.logger import get_logger

logger = get_logger(__name__)

BASE_URL = "https://www.yuketang.cn"
_CST = timezone(timedelta(hours=8))


@dataclass
class Lesson:
    courseware_id: str
    title: str
    create_time: int


@dataclass
class Presentation:
    presentation_id: str
    title: str
    covers: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Pure functions
# ---------------------------------------------------------------------------


def extract_presentation_ids(timeline: list[dict]) -> list[str]:
    """Extract unique presentationIds from review timeline, preserving first-seen order."""
    seen: set[str] = set()
    result: list[str] = []
    for item in timeline:
        pid = item.get("presentationId")
        if pid and pid not in seen:
            seen.add(pid)
            result.append(pid)
    return result


def format_lesson_date(ts_ms: int) -> str:
    """Format millisecond timestamp to 'MM-DD' string in China timezone (UTC+8).

    Returns '' for 0 or negative values.
    """
    if ts_ms <= 0:
        return ""
    dt = datetime.fromtimestamp(ts_ms / 1000, tz=_CST)
    return dt.strftime("%m-%d")


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------


def build_cookies(context_cookies: list[dict]) -> dict[str, str]:
    """Convert Playwright cookie list to simple name→value dict."""
    return {c["name"]: c["value"] for c in context_cookies}


# ---------------------------------------------------------------------------
# Async API functions
# ---------------------------------------------------------------------------


async def fetch_courses(client: httpx.AsyncClient) -> list[dict]:
    """Fetch the user's course list (student identity).

    GET /v2/api/web/courses/list?identity=2
    """
    resp = await client.get(f"{BASE_URL}/v2/api/web/courses/list", params={"identity": 2})
    resp.raise_for_status()
    data = resp.json()
    return data.get("data", {}).get("list", [])


async def fetch_lessons(client: httpx.AsyncClient, classroom_id: int) -> list[Lesson]:
    """Fetch lesson activities for a classroom, filtered to type==14, oldest first.

    GET /v2/api/web/logs/learn/{cid}?actype=14&page=0&offset=500&sort=-1
    """
    resp = await client.get(
        f"{BASE_URL}/v2/api/web/logs/learn/{classroom_id}",
        params={"actype": 14, "page": 0, "offset": 500, "sort": -1},
    )
    resp.raise_for_status()
    data = resp.json()
    activities = data.get("data", {}).get("activities", [])
    lessons = [
        Lesson(
            courseware_id=str(a["courseware_id"]),
            title=a.get("title", ""),
            create_time=a.get("create_time", 0),
        )
        for a in activities
        if a.get("type") == 14
    ]
    lessons.reverse()  # API returns newest first; we want chronological (oldest first)
    return lessons


async def fetch_presentations(
    client: httpx.AsyncClient, lesson_id: str
) -> list[Presentation]:
    """Fetch presentations for a lesson via the review timeline.

    1. GET review timeline to discover presentationIds
    2. For each, fetch title from lesson-summary and covers from student/ppt
    """
    # Step 1: get timeline
    review_resp = await client.get(
        f"{BASE_URL}/api/v3/classroom-report/student/review",
        params={"lesson_id": lesson_id},
    )
    review_resp.raise_for_status()
    timeline = review_resp.json().get("data", {}).get("timelineList", [])
    pids = extract_presentation_ids(timeline)

    if not pids:
        logger.warning("No presentations found for lesson %s", lesson_id)
        return []

    presentations: list[Presentation] = []
    for pid in pids:
        # Fetch title
        summary_resp = await client.get(
            f"{BASE_URL}/api/v3/lesson-summary/student/presentation",
            params={"lesson_id": lesson_id, "presentation_id": pid},
        )
        summary_resp.raise_for_status()
        title = (
            summary_resp.json()
            .get("data", {})
            .get("presentation", {})
            .get("title", "untitled")
        )

        # Fetch slide covers
        ppt_resp = await client.get(
            f"{BASE_URL}/api/v3/classroom-report/student/ppt",
            params={"lesson_id": lesson_id, "presentationId": pid},
        )
        ppt_resp.raise_for_status()
        slide_list = ppt_resp.json().get("data", {}).get("slideList", [])
        slide_list.sort(key=lambda s: s.get("index", 0))
        covers = [s["cover"] for s in slide_list if s.get("cover")]

        presentations.append(
            Presentation(presentation_id=pid, title=title, covers=covers)
        )
        logger.debug("Presentation %s: %s (%d slides)", pid, title, len(covers))

    return presentations
