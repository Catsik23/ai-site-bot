from flask import Blueprint, render_template, request, redirect, url_for, flash, session
import bcrypt
from datetime import datetime, timedelta
from shared.supabase import supabase
from shared.utils import parse_site, detect_site_type
from shared.logger import log_event

auth_bp = Blueprint('auth', __name__)

def login_required(f):
    """Декоратор: требует авторизацию для доступа к маршруту."""
    from functools import wraps
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'user_id' not in session:
            flash('Войдите в систему', 'error')
            return redirect(url_for('auth.login'))
        return f(*args, **kwargs)
    return decorated

@auth_bp.route('/register', methods=['GET', 'POST'])
def register():
    """Регистрация нового пользователя."""
    if request.method == 'POST':
        email = request.form.get('email', '').strip()
        password = request.form.get('password', '').strip()
        password2 = request.form.get('password2', '').strip()

        if not email or not password:
            flash('Заполните все поля', 'error')
            return render_template('pages/register.html')
        if password != password2:
            flash('Пароли не совпадают', 'error')
            return render_template('pages/register.html')

        existing = supabase.table('users').select('id').eq('email', email).execute()
        if existing.data:
            flash('Пользователь с таким email уже существует', 'error')
            return render_template('pages/register.html')

        password_hash = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()
        supabase.table('users').insert({
            'email': email,
            'password_hash': password_hash,
            'tariff': 'trial',
            'trial_ends_at': (datetime.utcnow() + timedelta(days=7)).isoformat(),
            'subscription_active': False
        }).execute()

        log_event('user_registered')
        flash('Регистрация успешна!', 'success')
        return redirect(url_for('auth.login'))

    return render_template('pages/register.html')

@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    """Вход в систему."""
    if request.method == 'POST':
        email = request.form.get('email', '').strip()
        password = request.form.get('password', '').strip()

        if not email or not password:
            flash('Заполните все поля', 'error')
            return render_template('pages/login.html')

        user = supabase.table('users').select('*').eq('email', email).execute()
        if not user.data:
            flash('Неверный email или пароль', 'error')
            return render_template('pages/login.html')

        user_data = user.data[0]
        if not bcrypt.checkpw(password.encode(), user_data['password_hash'].encode()):
            flash('Неверный email или пароль', 'error')
            return render_template('pages/login.html')

        session['user_id'] = user_data['id']
        session['user_email'] = user_data['email']
        session['tariff'] = user_data['tariff']
        log_event('user_login', user_id=user_data['id'])
        flash('Добро пожаловать!', 'success')
        return redirect(url_for('auth.dashboard'))

    return render_template('pages/login.html')

@auth_bp.route('/logout')
def logout():
    """Выход из системы."""
    session.clear()
    flash('Вы вышли из системы', 'success')
    return redirect(url_for('index'))

@auth_bp.route('/dashboard')
@login_required
def dashboard():
    """Дашборд — список сайтов пользователя."""
    import json as json_module
    sites = supabase.table('sites').select('*').eq('user_id', session['user_id']).execute()
    total_faq = 0
    for site in sites.data:
        faq = site.get('faq', [])
        if isinstance(faq, str):
            try:
                faq = json_module.loads(faq)
            except:
                faq = []
        total_faq += len(faq)
    return render_template('pages/dashboard.html', sites=sites.data, total_faq=total_faq)

@auth_bp.route('/dashboard/sites/new', methods=['GET', 'POST'])
@login_required
def add_site():
    """Добавление нового сайта: парсинг, индексация, FAQ, нейро-карточка."""
    if request.method == 'POST':
        url = request.form.get('url', '').strip()
        if not url:
            flash('Введите URL сайта', 'error')
            return render_template('pages/add_site.html')
        if not url.startswith('http'):
            url = 'https://' + url

        result = parse_site(url)
        if not result['success']:
            flash(result.get('message', 'Ошибка анализа сайта'), 'error')
            return render_template('pages/add_site.html')

        # Сохраняем сайт
        site_result = supabase.table('sites').insert({
            'user_id': session['user_id'],
            'url': url,
            'domain': result['domain'],
            'title': result['title'],
            'text_content': '',  # текст сохраним в чанках
            'faq': '[]',
            'site_type': detect_site_type(result['text']),
            'contacts': '{"phones": [], "emails": []}',
            'neuro_card_url': '',
            'neuro_card_active': False
        }).execute()
        
        site_id = site_result.data[0]['id']

        # === ЗАПУСКАЕМ КОНВЕЙЕР (ПРЯМЫЕ ВЫЗОВЫ) ===
        import json as json_module
        
        # 1. Индексация чанков и сущностей
        from services.crawler.app import run_indexing
        try:
            run_indexing(url, site_id)
        except Exception as e:
            print(f"Indexing error: {e}")

        # 2. Генерация FAQ
        from services.ai.app import generate_faq
        faq = []
        try:
            faq = generate_faq(result['title'], result['text'], result['phones'], result['emails'])
        except Exception as e:
            print(f"FAQ error: {e}")

        # 3. Создание нейро-карточки
        from services.neurocard.app import generate_neuro_card_static
        card_url = ''
        try:
            filename = generate_neuro_card_static(
                result['domain'], result['title'], result['text'],
                result['phones'], result['emails'], faq, site_id
            )
            card_url = f'/neuro/{filename}'
        except Exception as e:
            print(f"Card error: {e}")

        # Обновляем сайт с FAQ и URL карточки
        supabase.table('sites').update({
            'faq': json_module.dumps(faq, ensure_ascii=False),
            'neuro_card_url': card_url,
            'neuro_card_active': True
        }).eq('id', site_id).execute()

        log_event('site_added', site_id=site_id, user_id=session['user_id'])
        flash('Сайт добавлен!', 'success')
        return redirect(url_for('auth.dashboard'))

    return render_template('pages/add_site.html')

@auth_bp.route('/dashboard/sites/<site_id>')
@login_required
def site_card(site_id):
    """Карточка сайта: FAQ, код виджета, нейро-карточка."""
    import json
    site = supabase.table('sites').select('*').eq('id', site_id).eq('user_id', session['user_id']).execute()
    if not site.data:
        flash('Сайт не найден', 'error')
        return redirect(url_for('auth.dashboard'))

    site_data = site.data[0]
    site_data['faq'] = json.loads(site_data['faq']) if isinstance(site_data['faq'], str) else site_data['faq']
    site_data['contacts'] = json.loads(site_data['contacts']) if isinstance(site_data['contacts'], str) else site_data['contacts']
    return render_template('pages/site_card.html', site=site_data)


@auth_bp.route('/dashboard/sites/<site_id>/delete', methods=['POST'])
@login_required
def delete_site(site_id):
    site = supabase.table('sites').select('*').eq('id', site_id).eq('user_id', session['user_id']).execute()
    if not site.data:
        flash('Сайт не найден', 'error')
        return redirect(url_for('auth.dashboard'))
    
    supabase.table('sites').delete().eq('id', site_id).execute()
    supabase.table('knowledge_chunks').delete().eq('site_id', site_id).execute()
    supabase.table('extracted_entities').delete().eq('site_id', site_id).execute()
    log_event('site_deleted', site_id=site_id, user_id=session['user_id'])
    flash('Сайт удалён', 'success')
    return redirect(url_for('auth.dashboard'))

@auth_bp.route('/dashboard/settings', methods=['GET', 'POST'])
@login_required
def settings():
    """Настройки профиля: ключи Яндекса, тариф."""
    if request.method == 'POST':
        api_key = request.form.get('yandex_api_key', '').strip()
        folder_id = request.form.get('yandex_folder_id', '').strip()
        supabase.table('users').update({
            'yandex_api_key_encrypted': api_key,
            'yandex_folder_id_encrypted': folder_id
        }).eq('id', session['user_id']).execute()
        flash('Настройки сохранены', 'success')
        return redirect(url_for('auth.dashboard'))

    user = supabase.table('users').select('*').eq('id', session['user_id']).execute()
    return render_template('pages/settings.html', user=user.data[0] if user.data else {})
