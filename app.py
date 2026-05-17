from flask import Flask, render_template, request, jsonify
import sys, os
sys.path.insert(0, '/content/ai-site-bot')

from services.auth.app import auth_bp
from services.ai.app import ai_bp
from services.crawler.app import crawler_bp
from services.neurocard.app import neurocard_bp

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'ai-visibility-secret-2026')

app.register_blueprint(auth_bp)
app.register_blueprint(ai_bp)
app.register_blueprint(crawler_bp)
app.register_blueprint(neurocard_bp)

@app.route('/')
def index():
    return render_template('pages/index.html')

@app.route('/demo', methods=['POST'])
def demo():
    from shared.utils import parse_site, aeo_audit
    from services.ai.app import generate_faq
    from services.neurocard.app import generate_neuro_card_static

    url = request.form.get('url', '').strip()
    if not url:
        return jsonify({'success': False, 'message': 'Введите URL сайта'})

    result = parse_site(url)
    if not result['success']:
        return jsonify(result)

    audit = aeo_audit(result['text'])
    faq = generate_faq(result['title'], result['text'], result['phones'], result['emails'])
    filename = generate_neuro_card_static(result['domain'], result['title'], result['text'], result['phones'], result['emails'], faq, None)

    # Считаем количество найденных страниц
    pages_found = len(result.get('pages', []))

    return jsonify({
        'success': True, 'domain': result['domain'], 'title': result['title'],
        'pages_count': pages_found, 'aeo_score': audit['score'], 'aeo_details': audit['details'],
        'faq': faq, 'neuro_card_url': f'/neuro/{filename}',
    })

@app.route('/payment')
def payment():
    return render_template('pages/payment.html')

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
