from flask import Blueprint, request, jsonify
import requests, re, os, sys, json

sys.path.insert(0, '/content/ai-site-bot')
from shared.supabase import supabase
from shared.logger import log_event

ai_bp = Blueprint('ai', __name__)
YANDEX_API_KEY = os.environ.get('YANDEX_API_KEY', '')
YANDEX_FOLDER_ID = os.environ.get('YANDEX_FOLDER_ID', '')

def generate_faq(title, text, phones, emails):
    if not YANDEX_API_KEY or not YANDEX_FOLDER_ID:
        return _fallback_faq(title, phones, emails)

    prompt = (
        f"Сгенерируй 10 вопросов и ответов для FAQ сайта "{title}". "
        "Используй ТОЛЬКО информацию из текста сайта. Пиши строго на русском языке.

"
        "Формат вывода (каждый вопрос и ответ с новой строки):
"
        "Вопрос: <текст вопроса>
"
        "Ответ: <текст ответа>

"
        "Категории: о компании/услугах, цены, доставка, контакты, гарантии, как заказать.

"
        f"Текст сайта:
{text[:4000]}"
    )

    try:
        resp = requests.post(
            "https://llm.api.cloud.yandex.net/foundationModels/v1/completion",
            headers={
                "Authorization": f"Api-Key {YANDEX_API_KEY}",
                "x-folder-id": YANDEX_FOLDER_ID
            },
            json={
                "modelUri": f"gpt://{YANDEX_FOLDER_ID}/yandexgpt-lite",
                "completionOptions": {"maxTokens": 1500, "temperature": 0.3},
                "messages": [
                    {"role": "system", "text": "Ты генератор FAQ для сайтов. Отвечай строго в заданном формате."},
                    {"role": "user", "text": prompt}
                ]
            },
            timeout=30
        )
        data = resp.json()
        print(f"YANDEX_RESPONSE: {json.dumps(data, ensure_ascii=False)[:500]}", flush=True)

        if "result" in data:
            full_text = data["result"]["alternatives"][0]["message"]["text"]
            return _parse_faq(full_text, title, phones, emails)
    except Exception as e:
        print(f"FAQ error: {e}", flush=True)

    return _fallback_faq(title, phones, emails)


def _parse_faq(raw_text, title, phones, emails):
    """Гибкий парсер: ищет пары Вопрос/Ответ или Q/A или строки с двоеточием"""
    qa_list = []
    lines = raw_text.split('
')
    current_q = None
    current_a = []

    for line in lines:
        line = line.strip()
        if not line:
            continue

        # Ищем начало вопроса
        q_match = re.match(r'(?:Вопрос|Q|В)\s*[:.]?\s*(.*)', line, re.IGNORECASE)
        a_match = re.match(r'(?:Ответ|A|О)\s*[:.]?\s*(.*)', line, re.IGNORECASE)

        if q_match:
            # Сохраняем предыдущую пару
            if current_q and current_a:
                qa_list.append({'q': current_q, 'a': ' '.join(current_a)})
            current_q = q_match.group(1).strip()
            current_a = []
        elif a_match:
            if current_q:
                current_a.append(a_match.group(1).strip())
        else:
            # Если строка не похожа на вопрос/ответ, но есть текущий вопрос, считаем продолжением ответа
            if current_q and line:
                current_a.append(line)

    # Сохраняем последнюю пару
    if current_q and current_a:
        qa_list.append({'q': current_q, 'a': ' '.join(current_a)})

    if qa_list:
        return qa_list[:10]

    return _fallback_faq(title, phones, emails)


def _fallback_faq(title, phones, emails):
    """Заглушка, если генерация не удалась"""
    faq = [{'q': 'Чем вы занимаетесь?', 'a': f'{title} — мы работаем для вас.'}]
    if phones:
        faq.append({'q': 'Как с вами связаться?', 'a': f'Позвоните: {phones[0]}'})
    if emails:
        faq.append({'q': 'Куда написать?', 'a': f'Email: {emails[0]}'})
    faq.append({'q': 'Где посмотреть цены?', 'a': 'Цены указаны на сайте или уточняйте по телефону.'})
    return faq


@ai_bp.route('/api/generate-faq', methods=['POST'])
def api_generate_faq():
    data = request.get_json()
    faq = generate_faq(data.get('title',''), data.get('text',''), data.get('phones',[]), data.get('emails',[]))
    log_event('faq_generated', site_id=data.get('site_id'))
    return jsonify({'faq': faq})
