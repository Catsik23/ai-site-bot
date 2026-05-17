from flask import Blueprint, render_template, request, jsonify, send_from_directory
import re, sys, os
sys.path.insert(0, '/content/ai-site-bot')
from shared.supabase import supabase
from shared.logger import log_event

neurocard_bp = Blueprint('neurocard', __name__)
STATIC_DIR = os.path.join(os.path.dirname(__file__), '..', '..', 'static', 'neurocards')
os.makedirs(STATIC_DIR, exist_ok=True)
bot_index = {}

def generate_neuro_card_static(domain, title, text, phones, emails, faq, site_id):
    safe_name = re.sub(r'[^a-z0-9\-]','',domain.replace('.','-'))[:30]
    filepath = os.path.join(STATIC_DIR, f"{safe_name}.html")
    faq_html = ''.join(f'<div class="faq-item"><h3>{i["q"]}</h3><p>{i["a"]}</p></div>' for i in faq)
    contact = (f'<p><strong>Телефон:</strong> {phones[0]}</p>' if phones else '') + (f'<p><strong>Email:</strong> {emails[0]}</p>' if emails else '')
    html = f'<!DOCTYPE html><html lang="ru"><head><meta charset="UTF-8"><title>{title}</title><style>body{{font-family:Arial;max-width:800px;margin:0 auto;padding:20px;background:#f9fafb;color:#111}}h1{{font-size:2rem}}h2{{font-size:1.5rem;margin-top:30px}}.faq-item{{background:#fff;padding:15px;margin:10px 0;border-radius:10px}}.faq-item h3{{color:#7c3aed}}.contact{{background:#eef2ff;padding:15px;border-radius:10px;margin:20px 0}}</style></head><body><h1>{title}</h1><div class="contact">{contact or '<p>Контакты на сайте</p>'}</div><h2>FAQ</h2>{faq_html}<p style="margin-top:40px;color:#888">AI Visibility Optimizer</p></body></html>'
    with open(filepath, 'w', encoding='utf-8') as f: f.write(html)
    if site_id: log_event('card_published', site_id=site_id)
    return f"{safe_name}.html"

@neurocard_bp.route('/neuro/<filename>')
def serve_neuro_card(filename):
    return send_from_directory(STATIC_DIR, filename)

@neurocard_bp.route('/api/generate-card', methods=['POST'])
def api_generate_card():
    data = request.get_json()
    fn = generate_neuro_card_static(data['domain'],data['title'],data.get('text',''),data.get('phones',[]),data.get('emails',[]),data.get('faq',[]),data.get('site_id',''))
    if data.get('site_id'): supabase.table('sites').update({'neuro_card_url':f'/neuro/{fn}','neuro_card_active':True}).eq('id',data['site_id']).execute()
    return jsonify({'success':True,'url':f'/neuro/{fn}'})

@neurocard_bp.route('/bot')
def bot_page(): return render_template('pages/bot.html')

@neurocard_bp.route('/bot/chat', methods=['POST'])
def bot_chat():
    q = request.json.get('question','').strip()
    return jsonify({'answer': _simple(q)})

def _simple(q):
    kw = q.lower().split(); best = []
    for s in ['AI Visibility Optimizer — нейро-карточки для бизнеса.','Ваш сайт находит Алиса и Яндекс.Нейро.']:
        score = sum(1 for w in kw if w in s.lower())
        if score > 0: best.append((score, s))
    best.sort(reverse=True)
    return best[0][1] if best else 'Уточните у менеджера.'
