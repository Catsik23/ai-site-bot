from flask import Blueprint, request, jsonify
import sys, json
from shared.utils import parse_site, detect_site_type, aeo_audit, chunk_text, extract_entities, classify_chunk_topic
from shared.supabase import supabase
from shared.logger import log_event

crawler_bp = Blueprint('crawler', __name__)

@crawler_bp.route('/api/index-site', methods=['POST'])
def api_index_site():
    data = request.get_json()
    url = data.get('url','').strip()
    site_id = data.get('site_id','').strip()
    if not url or not site_id: return jsonify({'success':False,'message':'Нужны url и site_id'})
    result = parse_site(url)
    if not result['success']: return jsonify(result)
    chunks = chunk_text(result['text'])
    for chunk in chunks:
        supabase.table('knowledge_chunks').insert({'site_id':site_id,'chunk_text':chunk,'topic':classify_chunk_topic(chunk),'importance_score':3 if classify_chunk_topic(chunk) in ('pricing','delivery','contacts') else 1,'char_count':len(chunk)}).execute()
    for entity in extract_entities(result['text'], result['domain']):
        supabase.table('extracted_entities').insert({'site_id':site_id,'entity_type':entity['type'],'entity_value':entity['value'],'confidence':entity['confidence']}).execute()
    supabase.table('sites').update({'site_type':detect_site_type(result['text']),'contacts':json.dumps({'phones':result['phones'],'emails':result['emails']}),'last_indexed':'now()'}).eq('id',site_id).execute()
    log_event('crawl_completed', site_id=site_id)
    return jsonify({'success':True,'chunks_count':len(chunks),'entities_count':len(extract_entities(result['text'],result['domain']))})

@crawler_bp.route('/api/parse', methods=['POST'])
def api_parse():
    data = request.get_json()
    result = parse_site(data.get('url','').strip())
    if not result['success']: return jsonify(result)
    return jsonify({'success':True,'domain':result['domain'],'title':result['title'],'text':result['text'][:5000],'chunks':chunk_text(result['text']),'aeo_score':aeo_audit(result['text'])['score']})

def run_indexing(url, site_id):
    """Прямой вызов индексации без HTTP"""
    from shared.utils import parse_site, chunk_text, extract_entities, classify_chunk_topic, detect_site_type
    from shared.supabase import supabase
    import json as json_module
    from shared.logger import log_event

    result = parse_site(url)
    if not result['success']:
        return
    chunks = chunk_text(result['text'])
    for chunk in chunks:
        supabase.table('knowledge_chunks').insert({
            'site_id': site_id,
            'chunk_text': chunk,
            'topic': classify_chunk_topic(chunk),
            'importance_score': 3 if classify_chunk_topic(chunk) in ('pricing','delivery','contacts') else 1,
            'char_count': len(chunk)
        }).execute()
    entities = extract_entities(result['text'], result['domain'])
    for entity in entities:
        supabase.table('extracted_entities').insert({
            'site_id': site_id,
            'entity_type': entity['type'],
            'entity_value': entity['value'],
            'confidence': entity['confidence']
        }).execute()
    supabase.table('sites').update({
        'site_type': detect_site_type(result['text']),
        'contacts': json_module.dumps({'phones': result['phones'], 'emails': result['emails']}),
        'last_indexed': 'now()'
    }).eq('id', site_id).execute()
    log_event('crawl_completed', site_id=site_id)
