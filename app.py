from flask import Flask, render_template, request, jsonify, session, redirect, send_from_directory, Response
import urllib.request
import urllib.error
import urllib.parse
import json
import os

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "spicypy-dev-secret-change-me")

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


def get_access_token(refresh_token):
    body = (
        f"grant_type=refresh_token&refresh_token={urllib.parse.quote(refresh_token)}"
        f"&client_id={CLIENT_ID}"
    )
    req = urllib.request.Request(
        AUTH_URL,
        data=body.encode("utf-8"),
        headers={"Content-Type": "application/x-www-form-urlencoded", "User-Agent": "Mozilla/5.0"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=30) as response:
        return json.loads(response.read().decode("utf-8"))["access_token"]


def get_conversations(access_token):
    req = urllib.request.Request(CONVO_URL, headers=api_headers(access_token))
    with urllib.request.urlopen(req, timeout=30) as response:
        return json.loads(response.read().decode("utf-8"))


def clean_tag(tag):
    return str(tag).replace("`", "").replace(",", " ").strip()


def search_characters_typesense(query="*", nsfw_mode="all", page=1, per_page=24, tags=None, sort="trending"):
    tags = tags or []
    filters = ["application_ids:spicychat"]
    if nsfw_mode == "nsfw":
        filters.append("is_nsfw:true")
    elif nsfw_mode == "sfw":
        filters.append("is_nsfw:false")

    clean_tags = [clean_tag(tag) for tag in tags if clean_tag(tag)]
    if clean_tags:
        values = ",".join(f"`{tag}`" for tag in clean_tags)
        filters.append(f"tags:=[{values}]")

    sort_map = {
        "trending": "_text_match(buckets: 3):desc,num_messages_24h:desc",
        "popular": "_text_match(buckets: 3):desc,num_messages:desc",
        "rating": "_text_match(buckets: 3):desc,rating_score:desc,num_messages:desc",
    }

    payload = {
        "searches": [{
            "collection": "public_characters_alias",
            "q": query if query else "*",
            "query_by": "name,title,tags,creator_username,character_id,type",
            "include_fields": (
                "name,title,tags,creator_username,character_id,avatar_is_nsfw,avatar_url,"
                "visibility,num_messages,num_messages_24h,rating_score,is_nsfw,type"
            ),
            "sort_by": sort_map.get(sort, sort_map["trending"]),
            "filter_by": " && ".join(filters),
            "per_page": per_page,
            "page": page,
        }]
    }

    req = urllib.request.Request(
        TYPESENSE_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "text/plain", "Accept": "application/json", "User-Agent": "Mozilla/5.0"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=30) as response:
        result = json.loads(response.read().decode("utf-8")).get("results", [{}])[0]
        hits = result.get("hits", [])
        return {
            "characters": [hit.get("document", {}) for hit in hits],
            "total": result.get("found", len(hits)),
            "page": page,
            "per_page": per_page,
        }


def get_app_config(access_token):
    req = urllib.request.Request(APP_CONFIG_URL, headers=api_headers(access_token))
    try:
        with urllib.request.urlopen(req, timeout=30) as response:
            return json.loads(response.read().decode("utf-8"))
    except Exception:
        return {}


def send_message_api(message, access_token, char_id, conv_id, settings):
    payload = {
        "message": message,
        "character_id": char_id,
        "model_id": settings.get("model_id", DEFAULT_SETTINGS["model_id"]),
        "temperature": settings.get("temperature", DEFAULT_SETTINGS["temperature"]),
        "max_tokens": settings.get("max_tokens", DEFAULT_SETTINGS["max_tokens"]),
        "top_p": settings.get("top_p", DEFAULT_SETTINGS["top_p"]),
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
    with urllib.request.urlopen(req, timeout=90) as response:
        return json.loads(response.read().decode("utf-8"))


def parse_upstream_error(exc):
    try:
        body = exc.read().decode("utf-8", errors="replace")
        parsed = json.loads(body)
        if isinstance(parsed, dict):
            return str(parsed.get("message") or parsed.get("error") or body)
        return body
    except Exception:
        return str(exc)


def page(template):
    if "access_token" not in session:
        return render_template("login.html")
    return render_template(template)


@app.route("/")
def home():
    return page("home.html")


@app.route("/home")
def old_home():
    return redirect("/")


@app.route("/chat")
def chat():
    return page("chat.html")


@app.route("/manifest.webmanifest")
def manifest():
    return send_from_directory(app.static_folder, "manifest.webmanifest", mimetype="application/manifest+json")


@app.route("/service-worker.js")
def service_worker():
    response = send_from_directory(app.static_folder, "service-worker.js", mimetype="application/javascript")
    response.headers["Service-Worker-Allowed"] = "/"
    response.headers["Cache-Control"] = "no-cache"
    return response


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
        nsfw_mode = request.args.get("nsfw", "all").lower()
        if nsfw_mode not in {"all", "sfw", "nsfw"}:
            nsfw_mode = "all"
        page_number = max(1, int(request.args.get("page", 1)))
        per_page = min(48, max(8, int(request.args.get("per_page", 24))))
        tags = request.args.getlist("tag")
        sort = request.args.get("sort", "trending").lower()
        return jsonify(search_characters_typesense(search, nsfw_mode, page_number, per_page, tags, sort))
    except urllib.error.HTTPError as exc:
        return jsonify({"error": f"Typesense HTTP {exc.code}: {parse_upstream_error(exc)}", "characters": []}), 502
    except Exception as exc:
        return jsonify({"error": str(exc), "characters": []}), 500


@app.route("/api/avatar")
def api_avatar():
    if "access_token" not in session:
        return "", 401
    url = request.args.get("url", "")
    if not url:
        return "", 404
    try:
        parsed = urllib.parse.urlparse(url)
        host = (parsed.hostname or "").lower()
        allowed = host == "spicychat.ai" or host.endswith(".spicychat.ai") or host == "nd-api.com" or host.endswith(".nd-api.com")
        if parsed.scheme not in {"http", "https"} or not allowed:
            return "", 403
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0", "Accept": "image/*"})
        with urllib.request.urlopen(req, timeout=15) as response:
            return Response(
                response.read(),
                content_type=response.headers.get("Content-Type", "image/jpeg"),
                headers={"Cache-Control": "public, max-age=86400"},
            )
    except Exception:
        return "", 404


@app.route("/api/models")
def api_models():
    if "access_token" not in session:
        return jsonify({"error": "Not logged in"}), 401
    return jsonify(get_app_config(session["access_token"]).get("inferenceModels", []))


@app.route("/api/settings", methods=["GET", "POST"])
def api_settings():
    if "access_token" not in session:
        return jsonify({"error": "Not logged in"}), 401
    if request.method == "POST":
        current = session.get("settings", DEFAULT_SETTINGS.copy())
        current.update(request.get_json(silent=True) or {})
        session["settings"] = current
        return jsonify({"success": True, "settings": current})
    return jsonify(session.get("settings", DEFAULT_SETTINGS.copy()))


@app.route("/api/chat", methods=["POST"])
def api_chat():
    if "access_token" not in session:
        return jsonify({"error": "Not logged in"}), 401

    data = request.get_json(silent=True) or {}
    message = str(data.get("message") or "").strip()
    character_id = data.get("character_id")
    conversation_id = data.get("conversation_id")
    if not message or not character_id:
        return jsonify({"error": "Missing message atau character_id"}), 400

    try:
        upstream = send_message_api(
            message,
            session["access_token"],
            character_id,
            conversation_id,
            session.get("settings", DEFAULT_SETTINGS.copy()),
        )
        message_obj = upstream.get("message") if isinstance(upstream, dict) else None
        content = message_obj.get("content") if isinstance(message_obj, dict) else None
        if not content and isinstance(upstream, dict):
            content = upstream.get("content") or upstream.get("response")

        returned_id = conversation_id
        if isinstance(upstream, dict):
            returned_id = upstream.get("conversation_id") or returned_id
            if isinstance(upstream.get("conversation"), dict):
                returned_id = upstream["conversation"].get("id") or returned_id
            if isinstance(message_obj, dict):
                returned_id = message_obj.get("conversation_id") or returned_id

        if not content:
            return jsonify({"error": "SpicyChat API tidak mengembalikan isi balasan"}), 502
        return jsonify({"content": content, "conversation_id": returned_id})
    except urllib.error.HTTPError as exc:
        return jsonify({"error": f"SpicyChat API HTTP {exc.code}: {parse_upstream_error(exc)}"}), 502
    except urllib.error.URLError as exc:
        return jsonify({"error": f"Gagal menghubungi SpicyChat API: {exc.reason}"}), 502
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@app.route("/logout")
def logout():
    session.clear()
    return redirect("/")


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
