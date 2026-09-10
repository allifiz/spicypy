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
    "top_p": 0.95,
}

MOBILE_UI_PATCH = r"""
<style id="mobile-ui-patch">
  :root { --app-height: 100dvh; --mobile-header-height: 56px; }
  html, body { width: 100%; max-width: 100%; }
  @media (max-width: 768px) {
    html, body {
      height: var(--app-height, 100dvh) !important;
      min-height: var(--app-height, 100dvh) !important;
      overflow: hidden !important;
      overscroll-behavior: none;
    }
    .header {
      min-height: var(--mobile-header-height);
      padding-top: max(10px, env(safe-area-inset-top));
      flex-shrink: 0;
      position: relative;
      z-index: 200;
    }
    .main-container {
      flex: 1 !important;
      height: auto !important;
      min-height: 0 !important;
      overflow: hidden !important;
    }
    .sidebar {
      top: var(--mobile-header-height) !important;
      bottom: 0 !important;
      height: auto !important;
      max-height: calc(var(--app-height, 100dvh) - var(--mobile-header-height));
      z-index: 150 !important;
      overflow: hidden;
    }
    .sidebar-tabs { position: sticky; top: 0; z-index: 3; }
    .sidebar-content, .sidebar-content.active { min-height: 0; max-height: 100%; }
    .chat-container {
      width: 100%;
      height: 100% !important;
      min-width: 0;
      min-height: 0;
      overflow: hidden;
    }
    .chat-header { min-height: 48px; gap: 8px; }
    .chat-info {
      min-width: 0;
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
    }
    .messages {
      flex: 1 1 auto !important;
      min-height: 0 !important;
      padding-bottom: 16px;
      overscroll-behavior: contain;
    }
    .input-container {
      width: 100%;
      min-width: 0;
      align-items: center;
      gap: 6px !important;
      padding: 8px 8px max(8px, env(safe-area-inset-bottom)) !important;
      flex-wrap: nowrap;
      position: relative;
      z-index: 5;
    }
    .input-container input {
      min-width: 0 !important;
      width: 0;
      flex: 1 1 auto !important;
      font-size: 16px !important;
      padding: 10px 12px !important;
    }
    .input-container button {
      flex: 0 0 auto;
      white-space: nowrap;
      padding: 10px 12px !important;
    }
    .input-container button#italicBtn { padding: 10px !important; }
    .character-grid { align-content: start; }
    .modal { padding: max(12px, env(safe-area-inset-top)) 12px max(12px, env(safe-area-inset-bottom)); }
    .modal-content {
      width: 100% !important;
      max-height: calc(var(--app-height, 100dvh) - 24px) !important;
      padding: 18px !important;
    }
  }
</style>
<script>
(function () {
  function syncViewportHeight() {
    var height = window.visualViewport ? window.visualViewport.height : window.innerHeight;
    document.documentElement.style.setProperty('--app-height', height + 'px');
  }
  syncViewportHeight();
  window.addEventListener('resize', syncViewportHeight);
  window.addEventListener('orientationchange', syncViewportHeight);
  if (window.visualViewport) {
    window.visualViewport.addEventListener('resize', syncViewportHeight);
    window.visualViewport.addEventListener('scroll', syncViewportHeight);
  }
  document.addEventListener('DOMContentLoaded', function () {
    var input = document.getElementById('messageInput');
    if (!input) return;
    input.addEventListener('focus', function () {
      setTimeout(function () {
        syncViewportHeight();
        var messages = document.getElementById('messages');
        if (messages) messages.scrollTop = messages.scrollHeight;
      }, 120);
    });
  });
})();
</script>
"""

APP_BEHAVIOR_PATCH = r"""
<script id="home-chat-patch">
(function () {
  function closeSidebarOnMobile() {
    if (window.innerWidth <= 768) {
      var sidebar = document.getElementById('sidebar');
      if (sidebar) sidebar.classList.remove('active');
    }
  }

  function showChatError(message) {
    var messages = document.getElementById('messages');
    if (!messages) return;
    var bubble = document.createElement('div');
    bubble.className = 'message bot';
    bubble.style.color = '#b42318';
    bubble.textContent = 'Error: ' + message;
    messages.appendChild(bubble);
    messages.scrollTop = messages.scrollHeight;
  }

  document.addEventListener('DOMContentLoaded', function () {
    var tabs = document.querySelectorAll('.tab-btn');
    if (tabs.length > 1) tabs[1].innerHTML = '🏠 Home';
    var search = document.getElementById('searchInput');
    if (search) search.placeholder = 'Cari karakter SpicyChat...';
  });

  window.startNewChat = function (character) {
    var characterId = character && (character.character_id || character.id);
    if (!characterId) {
      showChatError('Character ID tidak ditemukan dari data SpicyChat.');
      return;
    }

    currentConvo = {
      id: null,
      character_id: characterId,
      character: character,
    };

    document.getElementById('chatHeader').style.display = 'flex';
    document.getElementById('inputContainer').style.display = 'flex';
    document.getElementById('charName').textContent = character.name || 'Unknown';

    var messages = document.getElementById('messages');
    messages.innerHTML = '<div class="empty-state">Mulai chat baru dengan ' +
      (character.name || 'bot') + '</div>';
    messages.scrollTop = messages.scrollHeight;
    closeSidebarOnMobile();
  };

  window.sendMessage = async function () {
    if (!currentConvo) return;

    var input = document.getElementById('messageInput');
    var sendBtn = document.getElementById('sendBtn');
    var messages = document.getElementById('messages');
    var message = input.value.trim();
    if (!message) return;

    if (!currentConvo.character_id) {
      showChatError('Character ID kosong. Pilih ulang karakter dari Home.');
      return;
    }

    sendBtn.disabled = true;
    input.value = '';

    var emptyState = messages.querySelector('.empty-state');
    if (emptyState) emptyState.remove();

    var userBubble = document.createElement('div');
    userBubble.className = 'message user';
    userBubble.innerHTML = formatMessage(message);
    messages.appendChild(userBubble);

    var loadingBubble = document.createElement('div');
    loadingBubble.className = 'message bot';
    loadingBubble.innerHTML = '<em>Bot sedang mengetik...</em>';
    messages.appendChild(loadingBubble);
    messages.scrollTop = messages.scrollHeight;

    try {
      var payload = {
        message: message,
        character_id: currentConvo.character_id,
      };
      if (currentConvo.id) payload.conversation_id = currentConvo.id;

      var response = await fetch('/api/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });

      var data;
      try {
        data = await response.json();
      } catch (_) {
        throw new Error('Response API bukan JSON (HTTP ' + response.status + ')');
      }

      if (!response.ok || data.error) {
        throw new Error(data.error || ('HTTP ' + response.status));
      }
      if (!data.content) {
        throw new Error('SpicyChat API tidak mengembalikan isi balasan.');
      }

      if (data.conversation_id) currentConvo.id = data.conversation_id;
      loadingBubble.innerHTML = formatMessage(data.content);
    } catch (err) {
      loadingBubble.style.color = '#b42318';
      loadingBubble.textContent = 'Error: ' + (err.message || String(err));
    } finally {
      sendBtn.disabled = false;
      input.focus();
      messages.scrollTop = messages.scrollHeight;
    }
  };
})();
</script>
"""


def api_headers(access_token=None):
    headers = {
        "Accept": "application/json, text/plain, */*",
        "x-app-id": "spicychat",
        "x-app-version": "4.1.0",
        "x-platform": "WEB",
        "x-platform-os": "DESKTOP",
        "User-Agent": "Mozilla/5.0",
    }
    if access_token:
        headers["Authorization"] = f"Bearer {access_token}"
    return headers


def get_access_token(refresh_token: str) -> str:
    data = (
        f"grant_type=refresh_token&refresh_token={urllib.parse.quote(refresh_token)}"
        f"&client_id={CLIENT_ID}"
    )
    req = urllib.request.Request(
        AUTH_URL,
        data=data.encode("utf-8"),
        headers={"Content-Type": "application/x-www-form-urlencoded", "User-Agent": "Mozilla/5.0"},
        method="POST",
    )
    with urllib.request.urlopen(req) as response:
        return json.loads(response.read().decode("utf-8"))["access_token"]


def get_conversations(access_token: str) -> list:
    req = urllib.request.Request(CONVO_URL, headers=api_headers(access_token))
    with urllib.request.urlopen(req) as response:
        return json.loads(response.read().decode("utf-8"))


def search_characters_typesense(query: str = "*", is_nsfw: bool = False, page: int = 1, per_page: int = 24) -> dict:
    nsfw_filter = "is_nsfw:true" if is_nsfw else "is_nsfw:false"
    payload = {
        "searches": [{
            "collection": "public_characters_alias",
            "q": query if query else "*",
            "query_by": "name,title,tags,creator_username,character_id,type",
            "include_fields": "name,title,tags,creator_username,character_id,avatar_is_nsfw,avatar_url,visibility,num_messages,rating_score,is_nsfw,type",
            "sort_by": "_text_match(buckets: 3):desc,num_messages_24h:desc",
            "filter_by": f"application_ids:spicychat && {nsfw_filter}",
            "per_page": per_page,
            "page": page,
        }]
    }
    headers = {
        "Content-Type": "text/plain",
        "Accept": "application/json",
        "User-Agent": "Mozilla/5.0",
    }
    req = urllib.request.Request(
        TYPESENSE_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers=headers,
        method="POST",
    )
    with urllib.request.urlopen(req) as response:
        data = json.loads(response.read().decode("utf-8"))
        hits = data.get("results", [{}])[0].get("hits", [])
        characters = [hit.get("document", {}) for hit in hits]
        return {"characters": characters, "total": len(characters)}


def get_app_config(access_token: str) -> dict:
    req = urllib.request.Request(APP_CONFIG_URL, headers=api_headers(access_token))
    try:
        with urllib.request.urlopen(req) as response:
            return json.loads(response.read().decode("utf-8"))
    except Exception:
        return {}


def send_message_api(message: str, access_token: str, char_id: str, conv_id: str | None, settings: dict) -> dict:
    payload = {
        "message": message,
        "character_id": char_id,
        "model_id": settings["model_id"],
        "temperature": settings["temperature"],
        "max_tokens": settings["max_tokens"],
        "top_p": settings["top_p"],
        "override_subscription": True,
        "allow_nsfw": True,
    }
    if conv_id:
        payload["conversation_id"] = conv_id

    headers = api_headers(access_token)
    headers["Content-Type"] = "application/json"
    req = urllib.request.Request(
        CHAT_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers=headers,
        method="POST",
    )
    with urllib.request.urlopen(req) as response:
        return json.loads(response.read().decode("utf-8"))


def parse_upstream_error(exc: urllib.error.HTTPError) -> str:
    try:
        body = exc.read().decode("utf-8", errors="replace")
        parsed = json.loads(body)
        if isinstance(parsed, dict):
            return str(parsed.get("message") or parsed.get("error") or body)
        return body
    except Exception:
        return str(exc)


@app.route("/")
def index():
    if "access_token" not in session:
        return render_template("login.html")
    html = render_template("index.html")
    html = html.replace("</head>", MOBILE_UI_PATCH + "\n</head>")
    return html.replace("</body>", APP_BEHAVIOR_PATCH + "\n</body>")


@app.route("/api/login", methods=["POST"])
def api_login():
    try:
        data = request.get_json(silent=True) or {}
        refresh_token = data.get("refresh_token")
        if not refresh_token:
            return jsonify({"error": "Token tidak boleh kosong"}), 400
        session["access_token"] = get_access_token(refresh_token)
        session["settings"] = DEFAULT_SETTINGS.copy()
        return jsonify({"success": True})
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@app.route("/api/conversations")
def api_conversations():
    if "access_token" not in session:
        return jsonify({"error": "Not logged in"}), 401
    try:
        return jsonify(get_conversations(session["access_token"]))
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@app.route("/api/characters")
def api_characters():
    if "access_token" not in session:
        return jsonify({"error": "Not logged in"}), 401
    try:
        search = request.args.get("search", "*")
        is_nsfw = request.args.get("is_nsfw", "false").lower() == "true"
        page = int(request.args.get("page", 1))
        per_page = int(request.args.get("per_page", 24))
        return jsonify(search_characters_typesense(search, is_nsfw, page, per_page))
    except Exception as exc:
        return jsonify({"error": str(exc), "characters": []}), 500


@app.route("/api/models")
def api_models():
    if "access_token" not in session:
        return jsonify({"error": "Not logged in"}), 401
    try:
        return jsonify(get_app_config(session["access_token"]).get("inferenceModels", []))
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@app.route("/api/settings", methods=["GET", "POST"])
def api_settings():
    if "access_token" not in session:
        return jsonify({"error": "Not logged in"}), 401
    if request.method == "POST":
        session.setdefault("settings", DEFAULT_SETTINGS.copy())
        session["settings"].update(request.get_json(silent=True) or {})
        return jsonify({"success": True, "settings": session["settings"]})
    return jsonify(session.get("settings", DEFAULT_SETTINGS.copy()))


@app.route("/api/chat", methods=["POST"])
def api_chat():
    if "access_token" not in session:
        return jsonify({"error": "Not logged in"}), 401

    data = request.get_json(silent=True) or {}
    message = data.get("message")
    character_id = data.get("character_id")
    conversation_id = data.get("conversation_id")

    if not message or not character_id:
        return jsonify({"error": "Missing message atau character_id"}), 400

    try:
        response = send_message_api(
            message,
            session["access_token"],
            character_id,
            conversation_id,
            session.get("settings", DEFAULT_SETTINGS.copy()),
        )

        message_obj = response.get("message") if isinstance(response, dict) else None
        content = message_obj.get("content") if isinstance(message_obj, dict) else None
        if not content and isinstance(response, dict):
            content = response.get("content") or response.get("response")

        returned_conversation_id = None
        if isinstance(response, dict):
            returned_conversation_id = response.get("conversation_id")
            if not returned_conversation_id and isinstance(response.get("conversation"), dict):
                returned_conversation_id = response["conversation"].get("id")
            if not returned_conversation_id and isinstance(message_obj, dict):
                returned_conversation_id = message_obj.get("conversation_id")

        if not content:
            keys = list(response.keys()) if isinstance(response, dict) else []
            return jsonify({
                "error": "SpicyChat API tidak mengembalikan balasan chat",
                "upstream_keys": keys,
            }), 502

        return jsonify({
            "content": content,
            "engine": response.get("engine", "unknown") if isinstance(response, dict) else "unknown",
            "conversation_id": returned_conversation_id or conversation_id,
        })
    except urllib.error.HTTPError as exc:
        return jsonify({
            "error": f"SpicyChat API HTTP {exc.code}: {parse_upstream_error(exc)}"
        }), 502
    except urllib.error.URLError as exc:
        return jsonify({"error": f"Gagal menghubungi SpicyChat API: {exc.reason}"}), 502
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@app.route("/logout")
def logout():
    session.clear()
    return render_template("login.html")


if __name__ == "__main__":
    print("\n" + "=" * 60)
    print("🌶️  SpicyChat Web Server")
    print("=" * 60)
    hostname = socket.gethostname()
    local_ip = socket.gethostbyname(hostname)
    print(f"\n📱 Akses dari HP: http://{local_ip}:5000")
    print("💻 Akses dari laptop: http://localhost:5000\n" + "=" * 60 + "\n")
    app.run(host="0.0.0.0", port=5000, debug=True)
