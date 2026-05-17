from flask import Blueprint, render_template, request, jsonify, send_from_directory
import re, sys, os, requests

sys.path.insert(0, '/content/ai-site-bot')
from shared.supabase import supabase
from shared.logger import log_event

neurocard_bp = Blueprint('neurocard', __name__)
STATIC_DIR = os.path.join(os.path.dirname(__file__), '..', '..', 'static', 'neurocards')
os.makedirs(STATIC_DIR, exist_ok=True)
bot_index = {}

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
    except Exception as e:
        print(f"YandexGPT error: {e}")
    return _simple_search(question, context)


def _simple_search(question, context):
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


def generate_neuro_card_static(domain, title, text, phones, emails, faq, site_id):
    safe_name = re.sub(r'[^a-z0-9\-]', '', domain.replace('.', '-'))[:30]
    filepath = os.path.join(STATIC_DIR, f"{safe_name}.html")
    faq_html = ''.join(f'<div class="faq-item"><h3>{i["q"]}</h3><p>{i["a"]}</p></div>' for i in faq)
    contact = (f'<p><strong>Телефон:</strong> {phones[0]}</p>' if phones else '') + (f'<p><strong>Email:</strong> {emails[0]}</p>' if emails else '')
    html = f'<!DOCTYPE html><html lang="ru"><head><meta charset="UTF-8"><title>{title}</title><style>body{{font-family:Arial;max-width:800px;margin:0 auto;padding:20px;background:#f9fafb;color:#111}}h1{{font-size:2rem}}h2{{font-size:1.5rem;margin-top:30px}}.faq-item{{background:#fff;padding:15px;margin:10px 0;border-radius:10px}}.faq-item h3{{color:#7c3aed}}.contact{{background:#eef2ff;padding:15px;border-radius:10px;margin:20px 0}}</style></head><body><h1>{title}</h1><div class="contact">{contact or '<p>Контакты на сайте</p>'}</div><h2>FAQ</h2>{faq_html}<p style="margin-top:40px;color:#888">AI Visibility Optimizer</p></body></html>'
    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(html)
    if site_id:
        log_event('card_published', site_id=site_id)
    return f"{safe_name}.html"


@neurocard_bp.route('/neuro/<filename>')
def serve_neuro_card(filename):
    return send_from_directory(STATIC_DIR, filename)


@neurocard_bp.route('/api/generate-card', methods=['POST'])
def api_generate_card():
    data = request.get_json()
    fn = generate_neuro_card_static(data['domain'], data['title'], data.get('text', ''), data.get('phones', []), data.get('emails', []), data.get('faq', []), data.get('site_id', ''))
    if data.get('site_id'):
        supabase.table('sites').update({'neuro_card_url': f'/neuro/{fn}', 'neuro_card_active': True}).eq('id', data['site_id']).execute()
    return jsonify({'success': True, 'url': f'/neuro/{fn}'})


@neurocard_bp.route('/bot')
def bot_page():
    return render_template('pages/bot.html')


@neurocard_bp.route('/bot/chat', methods=['POST'])
def bot_chat():
    question = request.json.get('question', '').strip()
    domain = 'ai-site-bot.onrender.com'
    if domain not in bot_index:
        bot_index[domain] = {
            'chunks': [
                'AI Visibility Optimizer — нейро-карточки для бизнеса. 499 руб/мес.',
                'Ваш сайт находит Алиса и Яндекс.Нейро. Без правок на сайте.',
                'Первые 7 дней бесплатно. Подключение за 5 минут.',
            ],
            'title': 'AI Visibility Optimizer',
            'site_type': 'b2b',
            'all_text': 'AI Visibility Optimizer.'
        }
    idx = bot_index[domain]
    context = ' '.join(idx['chunks'][:10])
    answer = ask_yandexgpt(question, context)
    return jsonify({'answer': answer})
