import json

from .config import RISK_MODEL
from .models import RiskAssessment
from .openai_client import openai_post


RISK_GREEN_ACTION = "一般衛教模式：提供健康教育資訊與自我照護建議。"
RISK_YELLOW_ACTION = "注意：可能有惡化風險，請提供保守建議並提醒觀察警訊與就醫時機。"
RISK_RED_ACTION = "急症分流：請立即提供就醫/急救指引，不進行一般衛教問答。"

def parse_risk_level(level: str) -> str:
    normalized = (level or "").strip().lower()
    if normalized in {"red", "yellow", "green"}:
        return normalized
    return "yellow"


def level_to_label(level: str) -> str:
    if level == "red":
        return "急症"
    if level == "yellow":
        return "注意"
    return "一般"


def level_to_action(level: str) -> str:
    if level == "red":
        return RISK_RED_ACTION
    if level == "yellow":
        return RISK_YELLOW_ACTION
    return RISK_GREEN_ACTION

def assess_question_risk(api_key: str, question: str) -> RiskAssessment:
    text = question.strip()
    if not text:
        return RiskAssessment(
            level="green",
            label="一般",
            reason="問題為空，預設一般風險。",
            diverted=False,
            action=RISK_GREEN_ACTION,
        )
    schema = {
        "name": "risk_triage",
        "schema": {
            "type": "object",
            "properties": {
                "level": {"type": "string", "enum": ["red", "yellow", "green"]},
                "reason": {"type": "string"},
            },
            "required": ["level", "reason"],
            "additionalProperties": False,
        },
    }
    messages = [
        {
            "role": "system",
            "content": (
                "你是醫療風險分級器。"
                "請只根據使用者描述判斷危險程度："
                "red=急症需立即就醫或撥打 119；"
                "yellow=可能惡化需儘快就醫或密切觀察；"
                "green=一般衛教情境。"
                "只輸出符合 schema 的 JSON。"
            ),
        },
        {
            "role": "user",
            "content": f"請判斷以下問題風險等級：\n{text}",
        },
    ]

    try:
        data = openai_post(
            api_key,
            "/chat/completions",
            {
                "model": RISK_MODEL,
                "temperature": 0,
                "messages": messages,
                "response_format": {
                    "type": "json_schema",
                    "json_schema": schema,
                },
            },
        )
        content = data["choices"][0]["message"]["content"]
        parsed = json.loads(content)
        level = parse_risk_level(str(parsed.get("level") or ""))
        reason = str(parsed.get("reason") or "AI 未提供原因。").strip()
    except Exception as exc:
        # Risk evaluation failure should fail safe to cautious triage.
        level = "yellow"
        reason = f"AI 風險評估暫時不可用，採保守分級。({exc})"

    return RiskAssessment(
        level=level,
        label=level_to_label(level),
        reason=reason,
        diverted=(level == "red"),
        action=level_to_action(level),
    )


def emergency_diversion_answer(question: str) -> str:
    return (
        "你的描述可能涉及急症風險，這裡不適合只靠線上衛教處理。\n"
        "請立即採取以下行動：\n"
        "1. 若有胸痛、呼吸困難、意識改變、大量出血，請立即撥打 119。\n"
        "2. 請盡快前往急診，並告知症狀開始時間、是否持續惡化。\n"
        "3. 若身邊有人可協助，請不要單獨前往。\n\n"
        f"你剛剛提到的問題：{question}\n"
        "若你願意，我可以再幫你整理給醫護人員的重點描述清單。"
    )
