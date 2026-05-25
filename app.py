from flask import Flask, render_template, request, jsonify
import time
from collections import defaultdict
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from services.auth.app import auth_bp
from services.ai.app import ai_bp
from services.crawler.app import crawler_bp
from services.neurocard.app import neurocard_bp
from shared.logger import log_event

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY')
if not app.secret_key:
    raise RuntimeError('SECRET_KEY env var is not set')

_demo_limits = defaultdict(list)

def check_demo_limit(ip):
    now = time.time()
    window = 3600
    max_requests = 3
    _demo_limits[ip] = [ts for ts in _demo_limits[ip] if now - ts < window]
    if len(_demo_limits[ip]) >= max_requests:
        return False, 0
    _demo_limits[ip].append(now)
    return True, max_requests - len(_demo_limits[ip])

app.register_blueprint(auth_bp)
app.register_blueprint(ai_bp)
app.register_blueprint(crawler_bp)
app.register_blueprint(neurocard_bp)

@app.route('/')
def index():
    """Главная страница — лендинг с AEO-аудитом."""
    return render_template('pages/index.html')

@app.route('/demo', methods=['POST'])
def demo():
    """Демо-эндпоинт: парсит сайт, генерирует FAQ и нейро-карточку."""
    ip = request.headers.get('X-Forwarded-For', request.remote_addr) or 'unknown'
    if ',' in ip:
        ip = ip.split(',')[0].strip()
    allowed, remaining = check_demo_limit(ip)
    if not allowed:
        return jsonify({'success': False, 'message': 'Лимит демо исчерпан. Попробуйте через час или зарегистрируйтесь — первые 7 дней бесплатно.', 'remaining': 0})
    
    from shared.utils import parse_site, ai_visibility_audit
    from services.ai.app import generate_faq
    from services.neurocard.app import generate_neuro_card_static

    url = request.form.get('url', '').strip()
    if not url:
        return jsonify({'success': False, 'message': 'Введите URL сайта'})

    result = parse_site(url)
    if not result['success']:
        return jsonify(result)

    audit = ai_visibility_audit(result['text'], result.get('html', ''))
    faq = generate_faq(result['title'], result['text'], result['phones'], result['emails'])
    filename = generate_neuro_card_static(result['domain'], result['title'], result['text'], result['phones'], result['emails'], faq, None)

    # Сохраняем чанки в Supabase для векторного поиска
    demo_site_id = 'demo-' + result['domain']
    try:
        from shared.utils import chunk_text, classify_chunk_topic
        from shared.supabase import supabase
        
        # Удаляем старые чанки для этого домена
        supabase.table('knowledge_chunks').delete().eq('site_id', demo_site_id).execute()
        
        chunks = chunk_text(result['text'])
        for chunk in chunks:
            supabase.table('knowledge_chunks').insert({
                'site_id': demo_site_id,
                'chunk_text': chunk,
                'topic': classify_chunk_topic(chunk),
                'importance_score': 3 if classify_chunk_topic(chunk) in ('pricing', 'delivery', 'contacts') else 1,
                'char_count': len(chunk)
            }).execute()
    except Exception as e:
        log_event('demo_chunk_error', error=str(e), site_id=demo_site_id)

    # Считаем количество найденных страниц
    pages_found = len(result.get('pages', []))

    return jsonify({
        'success': True, 'domain': result['domain'], 'title': result['title'],
        'pages_count': pages_found, 'ai_visibility_score': audit['score'], 'ai_visibility_details': audit['details'],
        'faq': faq, 'neuro_card_url': f'/neuro/{filename}', 'site_id': demo_site_id, 'remaining': remaining,
    })

@app.route('/payment')
def payment():
    """Страница оплаты (заглушка)."""
    return render_template('pages/payment.html')

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
