import os, requests

YANDEX_API_KEY = os.environ.get('YANDEX_API_KEY', '')
YANDEX_FOLDER_ID = os.environ.get('YANDEX_FOLDER_ID', '')

def ask_yandexgpt(question, context):
    if not YANDEX_API_KEY or not YANDEX_FOLDER_ID:
        return _simple_search(question, context)
    try:
        response = requests.post(
            "https://llm.api.cloud.yandex.net/foundationModels/v1/completion",
            headers={
                "Authorization": f"Api-Key {YANDEX_API_KEY}",
                "x-folder-id": YANDEX_FOLDER_ID
            },
            json={
                "modelUri": f"gpt://{YANDEX_FOLDER_ID}/yandexgpt-lite",
                "completionOptions": {"maxTokens": 200, "temperature": 0.3},
                "messages": [
                    {"role": "system", "text": "Ты — бот сайта. Отвечай на основе информации.\nИНФО:\n" + context[:3000]},
                    {"role": "user", "text": question}
                ]
            },
            timeout=10
        )
        data = response.json()
        if "result" in data:
            return data["result"]["alternatives"][0]["message"]["text"]
    except requests.Timeout:
        log_event("YANDEX_TIMEOUT", data={"error": "YandexGPT timeout"})
    except requests.ConnectionError:
        log_event("YANDEX_CONNECTION_ERROR", data={"error": "YandexGPT connection failed"})
    except Exception as e:
        log_event("YANDEX_ERROR", data={"error": str(e)})
    return _simple_search(question, context)

def _simple_search(question, context):
    import re
    keywords = question.lower().split()
    sentences = re.split(r'(?<=[.!?])\s+', context)
    best = []
    for s in sentences:
        score = sum(1 for kw in keywords if kw in s.lower())
        if score > 0:
            best.append((score, s))
    best.sort(reverse=True)
    if best:
        return ' '.join([s for _, s in best[:2]])[:300]
    return 'Уточните у менеджера.'
