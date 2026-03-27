"""Course fetching and selection logic."""

from playwright.async_api import Page
from src.core.logger import get_logger

logger = get_logger(__name__)

INDEX_URL = "https://www.yuketang.cn/v2/web/index"

_SEMESTER_NAMES = {1: "秋", 2: "春"}


def term_label(term: int) -> str:
    year = term // 100
    sem = term % 100
    name = _SEMESTER_NAMES.get(sem)
    if name:
        return f"{year + (1 if sem == 2 else 0)}{name}"
    return f"{year}-{sem:02d}"


def group_by_term(courses: list[dict]) -> dict[int, list[dict]]:
    groups: dict[int, list[dict]] = {}
    for c in courses:
        groups.setdefault(c["term"], []).append(c)
    return dict(sorted(groups.items(), reverse=True))


def build_course_url(course: dict) -> str:
    cid = course["classroom_id"]
    uid = course["course"]["university_id"]
    return (
        f"https://www.yuketang.cn/v2/web/studentLog/{cid}"
        f"?university_id={uid}&platform_id=3&classroom_id={cid}"
    )


async def fetch_courses(page: Page) -> list[dict]:
    logger.info("获取课程列表")
    try:
        result = await page.evaluate("""async () => {
            const resp = await fetch('/v2/api/web/courses/list?identity=2');
            if (!resp.ok) return null;
            const data = await resp.json();
            if (data.errcode !== 0) return null;
            return data.data.list;
        }""")
        if result is None:
            logger.warning("课程列表 API 返回异常")
            return []
        logger.info("获取到 %d 门课程", len(result))
        return result
    except Exception:
        logger.exception("获取课程列表失败")
        return []
