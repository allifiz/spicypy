from flask import Flask, render_template, request, jsonify, session
import urllib.request
import urllib.error
import urllib.parse
import json
import socket

app = Flask(__name__)
app.secret_key = 'spicychat_secret_key_12345'

# --- KONFIGURASI ---
AUTH_URL = "https://auth.spicychat.ai/oauth2/token"
CONVO_URL = "https://prod.nd-api.com/v2/conversations?limit=25&sort=latest"
TYPESENSE_URL = "https://ts-lb.nd-api.com/multi_search?use_cache=true&x-typesense-api-key=STHKtT6jrC5z1IozTJHIeSN4qN9oL1s3"
CHAT_URL = "https://chat.nd-api.com/chat"
APP_CONFIG_URL = "https://prod.nd-api.com/v2/applications/spicychat"
CLIENT_ID = "fb5754f42ee84f4787f9bd8ff49cac7a"

DEFAULT_SETTINGS = {
    "model_id": "stheno-8b",
    "temperature": 0.7,
    "max_tokens": 180,
    "top_p": 0.95
}

def get_access_token(refresh_token: str) -> str:
    data = f"grant_type=refresh_token&refresh_token={urllib.parse.quote(refresh_token)}&client_id={CLIENT_ID}"
    req = urllib.request.Request(
        AUTH_URL, data=data.encode('utf-8'),
        headers={"Content-Type": "application/x-www-form-urlencoded", "User-Agent": "Mozilla/5.0"},
        method="POST"
    )
    with urllib.request.urlopen(req) as response:
        token_data = json.loads(response.read().decode('utf-8'))
        return token_data["access_token"]

def get_conversations(access_token: str) -> list:
    req = urllib.request.Request(
        CONVO_URL,
        headers={
            "Authorization": f"Bearer {access_token}",
            "Accept": "application/json, text/plain, */*",
            "x-app-id": "spicychat",
            "x-app-version": "4.1.0",
            "x-platform": "WEB",
            "x-platform-os": "DESKTOP",
            "User-Agent": "Mozilla/5.0"
        }
    )
    with urllib.request.urlopen(req) as response:
        return json.loads(response.read().decode('utf-8'))

def search_characters_typesense(query: str = "*", is_nsfw: bool = False, page: int = 1, per_page: int = 24) -> dict:
    """Mencari karakter menggunakan Typesense Multi-Search API"""
    
    # Filter dinamis berdasarkan preferensi NSFW
    nsfw_filter = "is_nsfw:true" if is_nsfw else "is_nsfw:false"
    # Kita hapus filter tag yang terlalu ketat agar hasil search lebih banyak, 
    # tapi tetap filter berdasarkan application_ids
    filter_by = f"application_ids:spicychat && {nsfw_filter}"
    
    payload = {
        "searches": [{
            "collection": "public_characters_alias",
            "q": query if query else "*",
            "query_by": "name,title,tags,creator_username,character_id,type",
            "include_fields": "name,title,tags,creator_username,character_id,avatar_is_nsfw,avatar_url,visibility,num_messages,rating_score,is_nsfw,type",
            "sort_by": "_text_match(buckets: 3):desc,num_messages_24h:desc",
            "filter_by": filter_by,
            "per_page": per_page,
            "page": page
        }]
    }
    
    headers = {
        "Content-Type": "text/plain",  # Typesense multi-search butuh ini
        "Accept": "application/json",
        "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36"
    }
    
    try:
        req = urllib.request.Request(
            TYPESENSE_URL,
            data=json.dumps(payload).encode('utf-8'),
            headers=headers,
            method="POST"
        )
        with urllib.request.urlopen(req) as response:
            data = json.loads(response.read().decode('utf-8'))
            
            # Typesense mengembalikan format: {"results": [{"hits": [...]}]}
            hits = data.get("results", [{}])[0].get("hits", [])
            characters = [hit.get("document", {}) for hit in hits]
            
            return {"characters": characters, "total": len(characters)}
            
    except Exception as e:
        print(f"[DEBUG] Typesense Error: {e}")
        return {"characters": [], "total": 0}

def get_app_config(access_token: str) -> dict:
    req = urllib.request.Request(
        APP_CONFIG_URL,
        headers={
            "Authorization": f"Bearer {access_token}",
            "Accept": "application/json, text/plain, */*",
            "x-app-id": "spicychat",
            "x-app-version": "4.1.0",
            "x-platform": "WEB",
            "x-platform-os": "DESKTOP",
            "User-Agent": "Mozilla/5.0"
        }
    )
    try:
        with urllib.request.urlopen(req) as response:
            return json.loads(response.read().decode('utf-8'))
    except:
        return {}

def send_message_api(message: str, access_token: str, char_id: str, conv_id: str, settings: dict) -> dict:
    payload = json.dumps({
        "message": message,
        "character_id": char_id,
        "conversation_id": conv_id,
        "model_id": settings["model_id"],
        "temperature": settings["temperature"],
        "max_tokens": settings["max_tokens"],
        "top_p": settings["top_p"],
        "override_subscription": True,
        "allow_nsfw": True
    }).encode('utf-8')
    
    req = urllib.request.Request(
        CHAT_URL, data=payload,
        headers={
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
            "x-app-id": "spicychat",
            "x-app-version": "4.1.0",
            "x-platform": "WEB",
            "x-platform-os": "DESKTOP",
            "User-Agent": "Mozilla/5.0"
        },
        method="POST"
    )
    
    with urllib.request.urlopen(req) as response:
        return json.loads(response.read().decode('utf-8'))

# --- ROUTES ---

@app.route('/')
def index():
    if 'access_token' not in session:
        return render_template('login.html')
    return render_template('index.html')

@app.route('/api/login', methods=['POST'])
def api_login():
    try:
        data = request.json
        refresh_token = data.get('refresh_token')
        if not refresh_token:
            return jsonify({'error': 'Token tidak boleh kosong'}), 400
        
        access_token = get_access_token(refresh_token)
        session['access_token'] = access_token
        session['settings'] = DEFAULT_SETTINGS.copy()
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/conversations')
def api_conversations():
    if 'access_token' not in session:
        return jsonify({'error': 'Not logged in'}), 401
    try:
        return jsonify(get_conversations(session['access_token']))
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/characters')
def api_characters():
    if 'access_token' not in session:
        return jsonify({'error': 'Not logged in'}), 401
    try:
        search = request.args.get('search', '*')
        is_nsfw = request.args.get('is_nsfw', 'false').lower() == 'true'
        page = int(request.args.get('page', 1))
        per_page = int(request.args.get('per_page', 24))
        
        return jsonify(search_characters_typesense(search, is_nsfw, page, per_page))
    except Exception as e:
        return jsonify({'error': str(e), 'characters': []}), 500

@app.route('/api/models')
def api_models():
    if 'access_token' not in session:
        return jsonify({'error': 'Not logged in'}), 401
    try:
        config = get_app_config(session['access_token'])
        return jsonify(config.get('inferenceModels', []))
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/settings', methods=['GET', 'POST'])
def api_settings():
    if 'access_token' not in session:
        return jsonify({'error': 'Not logged in'}), 401
    if request.method == 'POST':
        session['settings'].update(request.json)
        return jsonify({'success': True, 'settings': session['settings']})
    return jsonify(session['settings'])

@app.route('/api/chat', methods=['POST'])
def api_chat():
    if 'access_token' not in session:
        return jsonify({'error': 'Not logged in'}), 401
    try:
        data = request.json
        if not all([data.get('message'), data.get('character_id'), data.get('conversation_id')]):
            return jsonify({'error': 'Missing parameters'}), 400
        
        response = send_message_api(
            data['message'], session['access_token'], 
            data['character_id'], data['conversation_id'], session['settings']
        )
        return jsonify({
            'content': response['message']['content'],
            'engine': response.get('engine', 'unknown')
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/logout')
def logout():
    session.clear()
    return render_template('login.html')

if __name__ == '__main__':
    print("\n" + "="*60)
    print("🌶️  SpicyChat Web Server (Typesense Enabled)")
    print("="*60)
    hostname = socket.gethostname()
    local_ip = socket.gethostbyname(hostname)
    print(f"\n📱 Akses dari HP: http://{local_ip}:5000")
    print(f"💻 Akses dari laptop: http://localhost:5000\n" + "="*60 + "\n")
    app.run(host='0.0.0.0', port=5000, debug=True)