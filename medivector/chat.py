from .config import CHAT_MODEL, MEMORY_MESSAGES
from .models import EvidenceAssessment, Reference, RiskAssessment
from .openai_client import openai_post


RESPONSE_SECTION_SUMMARY = "【重點摘要】"
RESPONSE_SECTION_ACTIONS = "【你現在可以做的事】"
RESPONSE_SECTION_WARNINGS = "【警訊（出現以下情況請就醫）】"
RESPONSE_SECTION_WHEN_TO_SEEK_CARE = "【何時就醫】"
RESPONSE_SECTIONS = (
    RESPONSE_SECTION_SUMMARY,
    RESPONSE_SECTION_ACTIONS,
    RESPONSE_SECTION_WARNINGS,
    RESPONSE_SECTION_WHEN_TO_SEEK_CARE,
)

def has_required_response_sections(answer: str) -> bool:
    return all(section in answer for section in RESPONSE_SECTIONS)


def normalized_template_answer(answer: str, risk: RiskAssessment) -> str:
    if has_required_response_sections(answer):
        return answer

    summary = answer.strip() or "目前資訊有限，以下提供一般衛教建議。"
    action_lines = [
        "- 先休息、補充水分，避免劇烈活動或自行加重處置。",
        "- 記錄症狀發生時間、頻率與加重/緩解因素。",
        "- 若你有慢性病或正在用藥，請先避免自行增減藥物。",
    ]

    warning_lines = [
        "- 症狀快速惡化、持續不改善或影響日常活動。",
        "- 出現呼吸困難、意識改變、胸痛、持續高燒等危險訊號。",
        "- 出現脫水、反覆嘔吐、無法進食或其他明顯異常。",
    ]

    when_to_seek_care_lines = ["- 若有任何危險訊號，請立即就醫或撥打 119。"]
    if risk.level == "yellow":
        when_to_seek_care_lines.append("- 建議今天內或 24 小時內安排門診/急診評估。")
    else:
        when_to_seek_care_lines.append("- 若症狀持續超過 1 至 2 天或反覆發作，請儘快就醫。")

    return "\n\n".join(
        [
            RESPONSE_SECTION_SUMMARY,
            summary,
            RESPONSE_SECTION_ACTIONS,
            "\n".join(action_lines),
            RESPONSE_SECTION_WARNINGS,
            "\n".join(warning_lines),
            RESPONSE_SECTION_WHEN_TO_SEEK_CARE,
            "\n".join(when_to_seek_care_lines),
        ]
    )

def chat_with_gpt(
    api_key: str,
    question: str,
    references: list[Reference],
    history: list[dict[str, str]],
    risk: RiskAssessment,
    evidence: EvidenceAssessment,
    rag_enabled: bool = True,
) -> str:
    template_instruction = (
        "回答必須使用以下四段固定格式，且段落標題需完全一致：\n"
        f"{RESPONSE_SECTION_SUMMARY}\n"
        f"{RESPONSE_SECTION_ACTIONS}\n"
        f"{RESPONSE_SECTION_WARNINGS}\n"
        f"{RESPONSE_SECTION_WHEN_TO_SEEK_CARE}\n"
        "每段內容請簡潔、可執行。"
    )

    evidence_instruction = (
        f"本次引用證據狀態：{'足夠' if evidence.sufficient else '不足'}。"
        f"原因：{evidence.reason}"
    )

    if references:
        context = "\n\n".join(
            (
                f"[{ref.index}] 來源: {ref.source} | 標題: {ref.title} | source_id: {ref.source_id} "
                f"| 日期: {ref.published_date or '未填'} | 適用對象: {ref.audience or '未填'} "
                f"| 主題: {ref.topic or '未填'}\n{ref.content}"
            )
            for ref in references
        )
        user_content = (
            f"使用者目前問題：{question}\n\n"
            f"可用參考資料：\n{context}\n\n"
            "請根據可用參考資料回答。"
            "每個使用到參考資料的重點都要在句尾加上對應索引，例如 [1]。"
            "不要引用未使用或不存在的索引。\n\n"
            f"{evidence_instruction}\n"
            "如果證據不足，請以保守方式回答，不要下定論或使用過度肯定語氣。\n\n"
            f"{template_instruction}"
        )
    elif not rag_enabled:
        user_content = (
            f"使用者目前問題：{question}\n\n"
            "本次使用者已關閉 RAG 搜尋，請不要使用向量資料庫參考，也不要在回答中加任何 [1] 這類索引。"
            f"\n\n{evidence_instruction}\n"
            "請以保守方式回答，不要表現出有檢索證據支持的確定語氣。\n\n"
            f"{template_instruction}"
        )
    else:
        user_content = (
            f"使用者目前問題：{question}\n\n"
            "向量資料庫沒有找到足夠相關的參考資料。請直接回答，不要在回答中加任何 [1] 這類索引。"
            f"\n\n{evidence_instruction}\n"
            "請明確標示這是保守衛教，不要給出確定性判斷。\n\n"
            f"{template_instruction}"
        )

    risk_instruction = (
        "本次風險分級："
        f"{risk.label}（{risk.level}）。"
        f"處置原則：{risk.action}"
    )

    messages = [
        {
            "role": "system",
            "content": (
                "你是使用繁體中文回答的助理。你可以參考同一個對話的短期上下文。"
                "若有向量資料庫參考，只能標註實際用到且能支持內容的索引；不要編造來源。"
                "若沒有參考資料，或本次 RAG 關閉，不要輸出任何引用索引。"
                "你只提供衛教資訊，不可做出診斷、處方、劑量建議或保證療效。"
                "當引用證據不足時，必須主動降低語氣強度，明確說明不確定性。"
                "語氣需保守，不可過度肯定，遇到不確定資訊要明確說明限制。"
            ),
        },
        {"role": "system", "content": risk_instruction},
        {"role": "system", "content": evidence_instruction},
        *history[-MEMORY_MESSAGES:],
        {"role": "user", "content": user_content},
    ]
    data = openai_post(
        api_key,
        "/chat/completions",
        {
            "model": CHAT_MODEL,
            "temperature": 0.2,
            "messages": messages,
        },
    )
    answer = data["choices"][0]["message"]["content"].strip()
    return normalized_template_answer(answer, risk)
