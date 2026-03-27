"""Quiz detection, AI solving, submission, and retry/brute-force logic."""

import asyncio
import re
from itertools import combinations

from openai import OpenAI
from playwright.async_api import Page

from src.core.logger import get_logger
from src import ui

logger = get_logger(__name__)


def _get_ai_client(api_key: str, base_url: str) -> OpenAI:
    return OpenAI(base_url=base_url, api_key=api_key)


async def detect_quiz(page: Page) -> bool:
    submit_btn = page.get_by_role("button", name="提交答案")
    return await submit_btn.count() > 0 and await submit_btn.is_visible()


async def extract_quiz(page: Page) -> dict:
    quiz_type = "不定项选择题"
    for t in ["单选题", "多选题", "判断题", "填空题"]:
        if await page.locator(f"text={t}").first.count() > 0:
            if await page.locator(f"text={t}").first.is_visible():
                quiz_type = t
                break

    quiz_container = page.locator("button:has-text('提交答案')").locator("..").locator("..")
    all_text = await quiz_container.inner_text()

    options = []
    option_items = quiz_container.locator("li")
    opt_count = await option_items.count()

    for i in range(opt_count):
        item = option_items.nth(i)
        text = await item.inner_text()
        text = text.strip().replace("\n", " ")
        if quiz_type == "判断题":
            clean = text.replace(" ", "")
            if "正确" in clean:
                options.append({"key": "正确", "text": "正确"})
            elif "错误" in clean or "错" in clean:
                options.append({"key": "错误", "text": "错误"})
        else:
            match = re.match(r"^([A-Z])\s+(.+)$", text)
            if match:
                options.append({"key": match.group(1), "text": match.group(2)})
            else:
                if text and text[0].isalpha():
                    options.append({"key": text[0], "text": text[1:].strip()})

    question = all_text
    question = question.replace(quiz_type, "", 1).strip()
    for opt in options:
        question = question.replace(f"{opt['key']} {opt['text']}", "")
        question = question.replace(f"{opt['key']}{opt['text']}", "")
    question = question.replace("提交答案", "").strip()
    question = re.sub(r"\s+", " ", question).strip()

    logger.info("题目提取: type=%s, options=%d", quiz_type, len(options))
    return {"type": quiz_type, "question": question, "options": options}


def solve_with_ai(quiz_data: dict, model: str, api_key: str, base_url: str,
                  wrong_answers: list[str] | None = None) -> list[str]:
    client = _get_ai_client(api_key, base_url)
    options_text = "\n".join(f"{opt['key']}. {opt['text']}" for opt in quiz_data["options"])

    q_type = quiz_data["type"]
    if q_type == "判断题":
        answer_hint = '请只返回 "正确" 或 "错误"'
    elif q_type not in ("单选题", "多选题"):
        q_type = "不定项选择题（可能是单选或多选）"
        answer_hint = '请只返回答案字母，用逗号分隔，如 "A" 或 "A,B,C"'
    else:
        answer_hint = '请只返回答案字母，用逗号分隔，如 "A" 或 "A,B,C"'

    wrong_hint = ""
    if wrong_answers:
        wrong_list = "\n".join(f"  - 第{i+1}次尝试: [{w}] ❌" for i, w in enumerate(wrong_answers))
        wrong_hint = (
            f"\n\n⚠️ 重要：以下答案组合已确认是错误的，你必须给出不同的答案组合！\n"
            f"{wrong_list}\n请仔细重新分析题目，选择上面没有出现过的答案组合。"
        )

    temperature = min(len(wrong_answers) * 0.4, 1.5) if wrong_answers else 0
    logger.info("调用 AI 解题 (model=%s, temperature=%.1f)", model, temperature)

    try:
        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": (
                    "你是一个答题助手。请直接给出正确答案，禁止输出任何分析、推理或解释。\n"
                    "严格按以下格式回答（只输出这一行，不要输出其他内容）：\n"
                    "答案：A\n"
                    "答案：A,B,C\n"
                    "答案：正确\n"
                    "答案：错误"
                )},
                {"role": "user", "content": (
                    f"题目类型：{q_type}\n题干：{quiz_data['question']}\n"
                    f"选项：\n{options_text}\n\n{answer_hint}{wrong_hint}\n\n"
                    "请严格按格式回答：答案：X，不要输出任何分析或推理过程。"
                )},
            ],
            temperature=temperature,
        )
        answer_text = response.choices[0].message.content.strip()
    except Exception as e:
        logger.exception("AI 调用失败")
        ui.warn(f"AI 调用失败 ({type(e).__name__})，回退到穷举")
        return []

    # 去除 <think>...</think> 推理块
    answer_text = re.sub(r"<think>.*?</think>", "", answer_text, flags=re.DOTALL).strip()

    if quiz_data["type"] == "判断题":
        if "正确" in answer_text or "对" in answer_text:
            return ["正确"]
        return ["错误"]

    # 优先从 "答案：X,Y,Z" 格式行提取
    valid_keys = {opt["key"].upper() for opt in quiz_data["options"]}
    answer_line = re.search(r"答案[：:]\s*([A-Za-z,\s]+)", answer_text)
    if answer_line:
        answer_text = answer_line.group(1)

    answer_text = answer_text.upper()
    keys = re.findall(r"[A-Z]", answer_text)
    seen = set()
    result = []
    for k in keys:
        if k not in seen and k in valid_keys:
            seen.add(k)
            result.append(k)

    logger.info("AI 返回答案: %s", result)
    return result


async def submit_answer(page: Page, answer_keys: list[str]) -> None:
    logger.info("提交答案: %s", answer_keys)
    await page.evaluate("""() => {
        const items = document.querySelectorAll('li.list-unstyled-item');
        for (const li of items) {
            const el = li.querySelector('.el-checkbox.correct, .el-radio.correct');
            if (el) { li.click(); }
        }
    }""")
    await page.wait_for_timeout(500)

    for key in answer_keys:
        clicked = await page.evaluate("""(key) => {
            const items = document.querySelectorAll('li');
            for (const li of items) {
                const text = li.textContent.replace(/\\s/g, '');
                if (key === '正确' && text.includes('正确')) { li.click(); return text; }
                if (key === '错误' && (text.includes('错误') || text === '错')) { li.click(); return text; }
                const raw = li.textContent.trim();
                if (raw.startsWith(key + ' ') || raw.startsWith(key + '.') ||
                    raw.startsWith(key + '、') || raw.startsWith(key + '\\t') ||
                    raw.match(new RegExp('^' + key + '\\\\s'))) {
                    li.click();
                    return raw.substring(0, 30);
                }
            }
            return null;
        }""", key)
        if clicked:
            ui.info(f"已选择: {key}")
        else:
            ui.warn(f"未找到选项: {key}")
        await page.wait_for_timeout(500)

    await page.wait_for_timeout(1000)

    submitted = await page.evaluate("""() => {
        const btns = document.querySelectorAll('button');
        for (const btn of btns) {
            if (btn.textContent.includes('提交答案') && btn.offsetParent !== null) {
                btn.click(); return true;
            }
        }
        return false;
    }""")
    if submitted:
        ui.success("已提交答案")
    else:
        ui.error("未找到提交按钮")


def _generate_all_combinations(quiz_data: dict) -> list[list[str]]:
    keys = [opt["key"] for opt in quiz_data["options"]]
    q_type = quiz_data["type"]

    if q_type == "判断题":
        return [["正确"], ["错误"]]
    elif q_type == "单选题":
        return [[k] for k in keys]
    else:
        combos = []
        for r in range(1, len(keys) + 1):
            for combo in combinations(keys, r):
                combos.append(list(combo))
        return combos


async def handle_quiz(page: Page, model: str, api_key: str, base_url: str) -> None:
    logger.info("检测到题目弹窗")
    ui.quiz_detected()

    quiz_data = await extract_quiz(page)
    ui.quiz_info(quiz_data["type"], quiz_data["question"], quiz_data["options"])

    tried = set()
    wrong_answers = []
    all_combos = _generate_all_combinations(quiz_data)

    max_attempts = len(all_combos)
    for attempt in range(max_attempts):
        is_retry = attempt > 0

        if attempt < 3:
            answer = solve_with_ai(quiz_data, model, api_key, base_url,
                                   wrong_answers=wrong_answers if wrong_answers else None)
            answer_key = ",".join(sorted(answer)) if answer else ""
            if not answer or answer_key in tried:
                answer = None
                for combo in all_combos:
                    ck = ",".join(sorted(combo))
                    if ck not in tried:
                        answer = combo
                        break
                if not answer:
                    break
                ui.warn("AI 给出重复答案，改用枚举")
        else:
            answer = None
            for combo in all_combos:
                ck = ",".join(sorted(combo))
                if ck not in tried:
                    answer = combo
                    break
            if not answer:
                break
            if attempt == 3:
                ui.warn("AI 多次失败，切换暴力枚举")

        ui.quiz_answer(answer, is_retry=is_retry)
        tried.add(",".join(sorted(answer)))
        await submit_answer(page, answer)

        await asyncio.sleep(2)
        if not await detect_quiz(page):
            ui.quiz_result(True)
            return

        ui.quiz_result(False)
        wrong_answers.append(",".join(answer))

    ui.error(f"题目所有 {len(all_combos)} 种组合均已尝试，仍未通过")
    raise RuntimeError("题目所有组合均已尝试仍未通过")
