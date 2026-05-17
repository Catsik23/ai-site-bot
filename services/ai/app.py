from flask import Blueprint, request, jsonify
import requests, re, os, sys
sys.path.insert(0, '/content/ai-site-bot')
from shared.supabase import supabase
from shared.logger import log_event

ai_bp = Blueprint('ai', __name__)
YANDEX_API_KEY = os.environ.get('YANDEX_API_KEY', '')
YANDEX_FOLDER_ID = os.environ.get('YANDEX_FOLDER_ID', '')

def generate_faq(title, text, phones, emails):
    if not YANDEX_API_KEY or not YANDEX_FOLDER_ID:
        return [{'q':'Чем вы занимаетесь?','a':title},{'q':'Как связаться?','a':phones[0] if phones else 'На сайте'}]
    try:
        prompt = "Создай FAQ для сайта: "+title+". Только факты. Только на русском. 10 вопросов. Формат: Q: вопрос? A: ответ.\nТЕКСТ:\n"+text[:4000]
        response = requests.post("https://llm.api.cloud.yandex.net/foundationModels/v1/completion",
            headers={"Authorization":f"Api-Key {YANDEX_API_KEY}","x-folder-id":YANDEX_FOLDER_ID},
            json={"modelUri":f"gpt://{YANDEX_FOLDER_ID}/yandexgpt-lite","completionOptions":{"maxTokens":1200,"temperature":0.3},
                  "messages":[{"role":"system","text":"Генератор FAQ на русском."},{"role":"user","text":prompt}]},timeout=25)
        data = response.json()
        if "result" in data:
            qa = []; lines = data["result"]["alternatives"][0]["message"]["text"].split('\n'); cur = None
            for line in lines:
                line = line.strip()
                if line.startswith('Q:') or line.startswith('В:'): cur = line.split(':',1)[-1].strip()
                elif (line.startswith('A:') or line.startswith('О:')) and cur:
                    ans = line.split(':',1)[-1].strip()
                    if len(ans)>10: qa.append({'q':cur,'a':ans}); cur = None
            return qa[:10] if qa else [{'q':'?','a':'Уточните на сайте'}]
    except: pass
    return [{'q':'Чем занимаетесь?','a':title}]

@ai_bp.route('/api/generate-faq', methods=['POST'])
def api_generate_faq():
    data = request.get_json()
    faq = generate_faq(data.get('title',''), data.get('text',''), data.get('phones',[]), data.get('emails',[]))
    log_event('faq_generated', site_id=data.get('site_id'))
    return jsonify({'faq':faq})
