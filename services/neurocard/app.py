from flask import Blueprint, render_template, request, jsonify, send_from_directory
import re, sys, os, requests, html as html_module, json as json_module

from shared.supabase import supabase
from shared.logger import log_event
from shared.ai_client import ask_yandexgpt

neurocard_bp = Blueprint('neurocard', __name__)
STATIC_DIR = os.path.join(os.path.dirname(__file__), '..', '..', 'static', 'neurocards')
os.makedirs(STATIC_DIR, exist_ok=True)

def generate_neuro_card_static(domain, title, text, phones, emails, faq, site_id):
    safe_name = re.sub(r'[^a-z0-9\-]', '', domain.replace('.', '-'))[:30]
    filepath = os.path.join(STATIC_DIR, f"{safe_name}.html")
    faq_html = ''.join(f'<div class="faq-item"><h3>{i["q"]}</h3><p>{i["a"]}</p></div>' for i in faq)
    contact = (f'<p><strong>Телефон:</strong> {html_module.escape(phones[0])}</p>' if phones else '') + (f'<p><strong>Email:</strong> {html_module.escape(emails[0])}</p>' if emails else '')
    html = f'<!DOCTYPE html><html lang="ru"><head><meta charset="UTF-8"><title>{html_module.escape(title)}</title><style>body{{font-family:Arial;max-width:800px;margin:0 auto;padding:20px;background:#f9fafb;color:#111}}h1{{font-size:2rem}}h2{{font-size:1.5rem;margin-top:30px}}.faq-item{{background:#fff;padding:15px;margin:10px 0;border-radius:10px}}.faq-item h3{{color:#7c3aed}}.contact{{background:#eef2ff;padding:15px;border-radius:10px;margin:20px 0}}</style></head><body><h1>{html_module.escape(title)}</h1><div class="contact">{contact or '<p>Контакты на сайте</p>'}</div><h2>FAQ</h2>{faq_html}<p style="margin-top:40px;color:#888">AI Visibility Optimizer</p></body></html>'
        ld_json = {
        "@context": "https://schema.org",
        "@type": "FAQPage",
        "mainEntity": [
            {"@type": "Question", "name": i["q"], "acceptedAnswer": {"@type": "Answer", "text": i["a"]}}
            for i in faq
        ]
    }
    html += f'<script type="application/ld+json">{json_module.dumps(ld_json, ensure_ascii=False)}</script>'
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
    if not data or not data.get('domain') or not data.get('title'):
        return jsonify({'success': False, 'message': 'Нужны domain и title'})
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
    domain = request.json.get('domain', '').strip()
    
    # Адаптивные промпты по типу сайта
    PROMPTS = {
        'shop': 'Ты — консультант интернет-магазина. Перечисляй товары с ценами. Предлагай оформить заказ.',
        'service': 'Ты — администратор. Предлагай запись на услуги. Уточняй удобное время.',
        'food': 'Ты — официант. Перечисляй блюда и принимай заказы.',
        'b2b': 'Ты — менеджер по продажам. Рассказывай о решениях, предлагай демо или консультацию.',
        'general': 'Ты — ассистент. Отвечай по информации сайта. Предлагай связаться с менеджером.'
    }
    
    context = ''
    site_type = 'general'
    
    # Ищем сайт в Supabase
    if domain:
        try:
            site = supabase.table('sites').select('id,site_type').eq('domain', domain).execute()
            if site.data:
                site_id = site.data[0]['id']
                site_type = site.data[0].get('site_type', 'general')
                chunks = supabase.table('knowledge_chunks')                     .select('chunk_text')                     .eq('site_id', site_id)                     .order('importance_score', desc=True)                     .limit(10).execute()
                if chunks.data:
                    context = ' '.join([c['chunk_text'] for c in chunks.data])
        except:
            pass
    
    # Fallback — наш сайт
    if not context:
        context = 'AI Visibility Optimizer — нейро-карточки для бизнеса. 499 руб/мес. Первые 7 дней бесплатно.'
    
    system_prompt = PROMPTS.get(site_type, PROMPTS['general']) + '\nИНФО:\n' + context[:3000]
    
    # Используем ask_yandexgpt с кастомным system_prompt
    from shared.ai_client import YANDEX_API_KEY, YANDEX_FOLDER_ID
    import requests as req
    if YANDEX_API_KEY and YANDEX_FOLDER_ID:
        try:
            response = req.post(
                "https://llm.api.cloud.yandex.net/foundationModels/v1/completion",
                headers={"Authorization": f"Api-Key {YANDEX_API_KEY}", "x-folder-id": YANDEX_FOLDER_ID},
                json={
                    "modelUri": f"gpt://{YANDEX_FOLDER_ID}/yandexgpt-lite",
                    "completionOptions": {"maxTokens": 200, "temperature": 0.3},
                    "messages": [
                        {"role": "system", "text": system_prompt},
                        {"role": "user", "text": question}
                    ]
                },
                timeout=10
            )
            data = response.json()
            if "result" in data:
                return jsonify({'answer': data["result"]["alternatives"][0]["message"]["text"]})
        except:
            pass
    
    answer = ask_yandexgpt(question, context)
    return jsonify({'answer': answer})
