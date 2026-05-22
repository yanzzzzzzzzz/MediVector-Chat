import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx
import weaviate
from dotenv import load_dotenv
from weaviate.classes.config import Configure, DataType, Property, VectorDistances
from weaviate.classes.data import DataObject
from weaviate.classes.query import MetadataQuery


load_dotenv(Path(__file__).with_name(".env"))

COLLECTION_NAME = "Article"
EMBEDDING_MODEL = os.getenv("OPENAI_EMBEDDING_MODEL", "text-embedding-3-small")
CHAT_MODEL = os.getenv("OPENAI_CHAT_MODEL", "gpt-4.1-mini")
OPENAI_BASE_URL = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1").rstrip("/")
TOP_K = int(os.getenv("TOP_K", "3"))
MAX_REFERENCE_DISTANCE = float(os.getenv("MAX_REFERENCE_DISTANCE", "0.45"))
REFERENCE_DISTANCE_MARGIN = float(os.getenv("REFERENCE_DISTANCE_MARGIN", "0.04"))


CHINESE_TEST_ARTICLES = [
    {
        "source_id": 101,
        "title": "糖尿病飲食與血糖管理",
        "source": "中文健康測試資料 / diabetes-guide",
        "content": (
            "糖尿病患者應優先選擇高纖、低精緻糖的食物，將全穀類、豆類、蔬菜與優質蛋白質"
            "平均分配到三餐。飯後可以依照醫囑監測血糖，觀察不同食物對血糖的影響；若出現低血糖"
            "症狀，應先補充快速吸收的糖分並再度量測。"
        ),
    },
    {
        "source_id": 102,
        "title": "銀髮族運動安全",
        "source": "中文健康測試資料 / senior-exercise",
        "content": (
            "銀髮族運動應包含有氧、肌力與平衡訓練。每週可安排快走、腳踏車或水中運動，並加入"
            "坐站訓練、彈力帶與單腳站立等動作。開始前要先暖身，若有頭暈、胸悶或關節劇痛，"
            "應停止運動並尋求專業協助。"
        ),
    },
    {
        "source_id": 103,
        "title": "高血壓生活調整",
        "source": "中文健康測試資料 / hypertension-lifestyle",
        "content": (
            "高血壓患者可透過減少鈉攝取、規律運動、控制體重、限制酒精與維持充足睡眠來協助控制"
            "血壓。建議在固定時間量測血壓並記錄數值，回診時提供給醫師參考；藥物不可自行停用或"
            "任意調整劑量。"
        ),
    },
    {
        "source_id": 104,
        "title": "偏頭痛誘發因子",
        "source": "中文健康測試資料 / migraine-triggers",
        "content": (
            "偏頭痛常見誘發因子包含睡眠不足、壓力、脫水、跳餐、酒精、強光與部分食物。患者可以"
            "建立頭痛日記，記錄發作時間、飲食、睡眠與壓力狀態，協助找出個人誘因。若頭痛型態突然"
            "改變或伴隨神經學症狀，應盡快就醫。"
        ),
    },
]


@dataclass
class Reference:
    index: int
    source_id: int
    title: str
    source: str
    content: str
    distance: float | None


def require_openai_api_key() -> str:
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("請先設定 OPENAI_API_KEY，才能使用 OpenAI embedding 與 GPT 回答。")
    return api_key


def openai_post(api_key: str, path: str, payload: dict[str, Any]) -> dict[str, Any]:
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    try:
        response = httpx.post(
            f"{OPENAI_BASE_URL}{path}",
            headers=headers,
            json=payload,
            timeout=60,
        )
        response.raise_for_status()
    except httpx.HTTPStatusError as exc:
        detail = exc.response.text
        raise RuntimeError(f"OpenAI API 回傳錯誤 {exc.response.status_code}: {detail}") from exc
    except httpx.HTTPError as exc:
        raise RuntimeError(f"無法連線到 OpenAI API: {exc}") from exc

    return response.json()


def embed_texts(api_key: str, texts: list[str]) -> list[list[float]]:
    data = openai_post(
        api_key,
        "/embeddings",
        {
            "model": EMBEDDING_MODEL,
            "input": texts,
        },
    )
    return [item["embedding"] for item in data["data"]]


def chat_with_gpt(api_key: str, question: str, references: list[Reference]) -> str:
    if references:
        context = "\n\n".join(
            f"[{ref.index}] 來源: {ref.source} | 標題: {ref.title} | source_id: {ref.source_id}\n{ref.content}"
            for ref in references
        )
        user_content = (
            f"使用者問題：{question}\n\n"
            f"可用參考資料：\n{context}\n\n"
            "請根據可用參考資料回答。每個使用到的重點都要在句尾加上對應索引，例如 [1]。"
        )
    else:
        user_content = (
            f"使用者問題：{question}\n\n"
            "向量資料庫沒有找到足夠相關的參考資料。請直接回答，不要在回答中加任何 [1] 這類索引。"
        )

    data = openai_post(
        api_key,
        "/chat/completions",
        {
            "model": CHAT_MODEL,
            "temperature": 0.2,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "你是使用繁體中文回答的助理。若有參考資料，只能標註實際用到且能支持內容的索引；"
                        "不要編造來源。若沒有參考資料，不要輸出任何引用索引。"
                    ),
                },
                {"role": "user", "content": user_content},
            ],
        },
    )
    return data["choices"][0]["message"]["content"].strip()


def article_embedding_text(article: dict[str, Any]) -> str:
    return f"標題：{article['title']}\n來源：{article['source']}\n內容：{article['content']}"


def recreate_collection(client: weaviate.WeaviateClient) -> None:
    if client.collections.exists(COLLECTION_NAME):
        client.collections.delete(COLLECTION_NAME)

    client.collections.create(
        name=COLLECTION_NAME,
        properties=[
            Property(name="source_id", data_type=DataType.INT),
            Property(name="title", data_type=DataType.TEXT),
            Property(name="source", data_type=DataType.TEXT),
            Property(name="content", data_type=DataType.TEXT),
        ],
        vector_config=Configure.Vectors.self_provided(
            vector_index_config=Configure.VectorIndex.hnsw(
                distance_metric=VectorDistances.COSINE,
            ),
        ),
    )


def seed_chinese_articles(client: weaviate.WeaviateClient, api_key: str) -> None:
    articles = client.collections.get(COLLECTION_NAME)
    embeddings = embed_texts(
        api_key,
        [article_embedding_text(article) for article in CHINESE_TEST_ARTICLES],
    )

    objects = [
        DataObject(
            properties=article,
            vector=embedding,
        )
        for article, embedding in zip(CHINESE_TEST_ARTICLES, embeddings)
    ]
    result = articles.data.insert_many(objects)
    if result.has_errors:
        raise RuntimeError(f"寫入 Weaviate 失敗：{result.errors}")


def search_references(
    client: weaviate.WeaviateClient,
    api_key: str,
    question: str,
) -> list[Reference]:
    articles = client.collections.get(COLLECTION_NAME)
    question_vector = embed_texts(api_key, [question])[0]
    result = articles.query.near_vector(
        near_vector=question_vector,
        limit=TOP_K,
        return_metadata=MetadataQuery(distance=True),
    )

    distances = [obj.metadata.distance for obj in result.objects if obj.metadata.distance is not None]
    best_distance = min(distances) if distances else None
    max_allowed_distance = MAX_REFERENCE_DISTANCE
    if best_distance is not None:
        max_allowed_distance = min(MAX_REFERENCE_DISTANCE, best_distance + REFERENCE_DISTANCE_MARGIN)

    references: list[Reference] = []
    seen_reference_keys: set[tuple[str, str, str]] = set()
    for obj in result.objects:
        distance = obj.metadata.distance
        if distance is not None and distance > max_allowed_distance:
            continue

        properties = obj.properties
        reference_key = (
            str(properties.get("title", "")),
            str(properties.get("source", "")),
            str(properties.get("content", "")),
        )
        if reference_key in seen_reference_keys:
            continue
        seen_reference_keys.add(reference_key)

        references.append(
            Reference(
                index=len(references) + 1,
                source_id=properties["source_id"],
                title=properties["title"],
                source=properties["source"],
                content=properties["content"],
                distance=distance,
            )
        )

    return references


def ask_question(question: str) -> None:
    api_key = require_openai_api_key()
    client = weaviate.connect_to_local()

    try:
        recreate_collection(client)
        seed_chinese_articles(client, api_key)
        references = search_references(client, api_key, question)
        answer = chat_with_gpt(api_key, question, references)

        print("\n回答")
        print(answer)

        if references:
            print("\n參考來源")
            for ref in references:
                distance = "未知" if ref.distance is None else f"{ref.distance:.4f}"
                print(f"[{ref.index}] {ref.source} | {ref.title} | source_id={ref.source_id} | distance={distance}")
    finally:
        client.close()


def read_question_from_cli() -> str:
    if len(sys.argv) > 1:
        return " ".join(sys.argv[1:]).strip()

    return input("請輸入問題：").strip()


if __name__ == "__main__":
    user_question = read_question_from_cli()
    if not user_question:
        raise SystemExit("問題不可為空。")

    ask_question(user_question)
