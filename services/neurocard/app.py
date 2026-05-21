from flask import Blueprint, render_template, request, jsonify, send_from_directory
import re, sys, os, requests

from shared.supabase import supabase
from shared.logger import log_event
from shared.ai_client import ask_yandexgpt

neurocard_bp = Blueprint('neurocard', __name__)
STATIC_DIR = os.path.join(os.path.dirname(__file__), '..', '..', 'static', 'neurocards')
os.makedirs(STATIC_DIR, exist_ok=True)
bot_index = {}

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
    
    # Если домен передан, но его нет в bot_index — парсим сайт клиента
    if domain and domain not in bot_index:
        try:
            from shared.utils import parse_site, chunk_text
            url = 'https://' + domain
            result = parse_site(url)
            if result['success']:
                chunks = chunk_text(result['text'])
                bot_index[domain] = {
                    'chunks': chunks[:10],
                    'title': result['title'],
                    'site_type': 'general',
                    'all_text': result['text'][:5000]
                }
        except Exception as e:
            pass
    
    # Если домен не передан или нет в bot_index — используем наш сайт
    if not domain or domain not in bot_index:
        domain = os.environ.get('APP_HOST', 'ai-site-bot.onrender.com')
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
