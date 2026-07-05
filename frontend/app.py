import os
import json
import uuid
import functools
import urllib.parse
import urllib.request
from urllib.error import HTTPError, URLError

from flask import (
    Flask, render_template, request, jsonify, Response,
    session, redirect, url_for,
)

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "wms-dev-secret-key")

BACKEND_URL      = os.environ.get("BACKEND_URL", "http://backend:8080")
AUTH_SERVICE_URL = os.environ.get("AUTH_SERVICE_URL", "http://auth-service:8080")


def image_url(img):
    """Images are stored either as a full S3 URL or (legacy) a local upload filename."""
    if not img:
        return ""
    if img.startswith("http://") or img.startswith("https://"):
        return img
    return f"/uploads/{img}"


app.jinja_env.filters["image_url"] = image_url


# ── Auth helpers ───────────────────────────────────────────────────────────────

def require_login(f):
    @functools.wraps(f)
    def decorated(*args, **kwargs):
        if not session.get("token"):
            return redirect(url_for("login", next=request.path))
        return f(*args, **kwargs)
    return decorated


@app.before_request
def ensure_workspace_in_session():
    if not session.get("token"):
        return
    if session.get("active_workspace_id"):
        return
    content, status, _ = http_request(
        "GET", f"{AUTH_SERVICE_URL}/auth/me",
        headers=_jwt_headers(), timeout=3,
    )
    if content and status == 200:
        data = parse_json(content)
        if data:
            workspaces = data.get("workspaces") or []
            session["workspaces"] = workspaces
            if workspaces:
                session["active_workspace_id"] = workspaces[0]["workspace_id"]
            session.modified = True


@app.context_processor
def inject_user():
    workspaces   = session.get("workspaces") or []
    active_ws_id = session.get("active_workspace_id")
    active_ws    = next((w for w in workspaces if w["workspace_id"] == active_ws_id), None)
    return {
        "current_user":             session.get("user"),
        "workspaces":               workspaces,
        "active_workspace_id":      active_ws_id,
        "active_workspace_name":    (active_ws["workspace_name"] if active_ws else None) or "No workspace",
        "active_workspace_role":    active_ws["role"] if active_ws else None,
        "active_workspace_invite":  active_ws.get("invite_code") if active_ws else None,
    }


def _auth_headers():
    """Headers for backend API calls: JWT + active workspace."""
    headers = {}
    token = session.get("token")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    ws_id = session.get("active_workspace_id")
    if ws_id:
        headers["X-Workspace-ID"] = str(ws_id)
    return headers


def _jwt_headers():
    """Headers for auth-service calls: JWT only (no workspace)."""
    token = session.get("token")
    if token:
        return {"Authorization": f"Bearer {token}"}
    return {}


# ── HTTP utilities ─────────────────────────────────────────────────────────────

def encode_multipart_formdata(fields, files):
    boundary = uuid.uuid4().hex
    lines = []

    for name, value in (fields or {}).items():
        lines.append(f"--{boundary}".encode("utf-8"))
        lines.append(f'Content-Disposition: form-data; name="{name}"'.encode("utf-8"))
        lines.append(b"")
        lines.append(value.encode("utf-8") if isinstance(value, str) else str(value).encode("utf-8"))

    for name, (filename, file_value, content_type) in (files or {}).items():
        file_content = file_value if isinstance(file_value, bytes) else file_value.read()
        lines.append(f"--{boundary}".encode("utf-8"))
        lines.append(
            f'Content-Disposition: form-data; name="{name}"; filename="{filename}"'.encode("utf-8")
        )
        lines.append(f"Content-Type: {content_type or 'application/octet-stream'}".encode("utf-8"))
        lines.append(b"")
        lines.append(file_content)

    lines.append(f"--{boundary}--".encode("utf-8"))
    lines.append(b"")
    body         = b"\r\n".join(lines)
    content_type = f"multipart/form-data; boundary={boundary}"
    return body, content_type


def http_request(method, url, params=None, json_data=None, files=None, timeout=5, headers=None):
    if params:
        url = f"{url}?{urllib.parse.urlencode(params)}"

    body            = None
    request_headers = dict(headers or {})

    if json_data is not None:
        body = json.dumps(json_data).encode("utf-8")
        request_headers["Content-Type"] = "application/json"
    elif files is not None:
        body, multipart_content_type = encode_multipart_formdata({}, files)
        request_headers["Content-Type"] = multipart_content_type

    req = urllib.request.Request(url, data=body, headers=request_headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.read(), resp.getcode(), resp.headers.get("Content-Type", "")
    except HTTPError as err:
        try:
            content = err.read()
        except Exception:
            content = b""
        return content, err.code, getattr(err, "headers", {}).get("Content-Type", "")
    except URLError:
        return None, None, None


def parse_json(content):
    if not content:
        return None
    try:
        return json.loads(content.decode("utf-8"))
    except Exception:
        return None


def backend_get(path, params=None):
    content, status, _ = http_request(
        "GET", f"{BACKEND_URL}{path}", params=params, timeout=5, headers=_auth_headers()
    )
    if content is None or status is None or status >= 400:
        return None
    return parse_json(content)


def backend_post(path, data):
    content, status, _ = http_request(
        "POST", f"{BACKEND_URL}{path}", json_data=data, timeout=5, headers=_auth_headers()
    )
    if content is None or status is None:
        return None, 500
    result = parse_json(content)
    if status >= 400:
        return None, status
    return result, status


def backend_put(path, data):
    content, status, _ = http_request(
        "PUT", f"{BACKEND_URL}{path}", json_data=data, timeout=5, headers=_auth_headers()
    )
    if content is None or status is None:
        return None, 500
    return parse_json(content), status


def backend_delete(path):
    _, status, _ = http_request(
        "DELETE", f"{BACKEND_URL}{path}", timeout=5, headers=_auth_headers()
    )
    return status if status is not None else 500


def backend_patch(path, data):
    content, status, _ = http_request(
        "PATCH", f"{BACKEND_URL}{path}", json_data=data, timeout=5, headers=_auth_headers()
    )
    if content is None or status is None:
        return None, 500
    return parse_json(content), status


def auth_post(path, data, headers=None):
    content, status, _ = http_request(
        "POST", f"{AUTH_SERVICE_URL}{path}", json_data=data, timeout=5, headers=headers or {}
    )
    if content is None or status is None:
        return None, 500
    return parse_json(content), status


def sidebar_data():
    boxes     = backend_get("/api/boxes") or []
    locations = sorted(set(b.get("location") for b in boxes if b.get("location")))
    return boxes, locations


def _store_workspace_in_session(ws_dict):
    """Add a workspace dict (from auth-service) to session and set it active."""
    entry = {
        "workspace_id":   ws_dict["id"],
        "workspace_name": ws_dict["name"],
        "invite_code":    ws_dict.get("invite_code"),
        "role":           ws_dict.get("role"),
    }
    workspaces = list(session.get("workspaces") or [])
    if not any(w["workspace_id"] == entry["workspace_id"] for w in workspaces):
        workspaces.append(entry)
        session["workspaces"] = workspaces
    session["active_workspace_id"] = entry["workspace_id"]
    session.modified = True


# ── Auth routes ────────────────────────────────────────────────────────────────

@app.route("/health")
def health():
    return jsonify({"status": "ok"})


def _safe_next(url):
    """Only allow same-site relative redirects (no scheme/host)."""
    if url and url.startswith("/") and not url.startswith("//"):
        return url
    return None


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "GET":
        next_url = _safe_next(request.args.get("next"))
        if session.get("token"):
            return redirect(next_url or url_for("index"))
        registered = request.args.get("registered")
        return render_template("login.html", registered=registered, next=next_url)

    next_url = _safe_next(request.form.get("next"))
    email    = request.form.get("email", "").strip()
    password = request.form.get("password", "")
    result, status = auth_post("/auth/login", {"email": email, "password": password})
    if status == 200 and result and result.get("access_token"):
        session["token"] = result["access_token"]
        user_data   = result.get("user") or {"email": email}
        first_name  = (user_data.get("first_name") or "").strip()
        last_name   = (user_data.get("last_name")  or "").strip()
        display_name = " ".join(filter(None, [first_name, last_name])) or None
        if display_name:
            user_data["display_name"] = display_name
        session["user"] = user_data
        workspaces = user_data.get("workspaces") or []
        session["workspaces"] = workspaces
        if workspaces:
            session["active_workspace_id"] = workspaces[0]["workspace_id"]
            return redirect(next_url or url_for("index"))
        return redirect(url_for("onboarding"))
    error = (result or {}).get("error") or "Invalid credentials"
    return render_template("login.html", error=error, next=next_url)


@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "GET":
        return render_template("register.html")

    email      = request.form.get("email", "").strip()
    password   = request.form.get("password", "")
    first_name = request.form.get("first_name", "").strip()
    last_name  = request.form.get("last_name", "").strip()
    result, status = auth_post("/auth/register", {
        "email": email, "password": password,
        "first_name": first_name or None, "last_name": last_name or None,
    })
    if status == 201:
        login_result, login_status = auth_post("/auth/login", {"email": email, "password": password})
        if login_status == 200 and login_result and login_result.get("access_token"):
            session["token"] = login_result["access_token"]
            user_data    = login_result.get("user") or {"email": email}
            display_name = " ".join(filter(None, [first_name, last_name])) or None
            if display_name:
                user_data["display_name"] = display_name
            session["user"]       = user_data
            session["workspaces"] = []
            session["active_workspace_id"] = None
        return redirect(url_for("onboarding"))
    error = (result or {}).get("error") or "Registration failed"
    return render_template("register.html", error=error)


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


# ── Onboarding routes ──────────────────────────────────────────────────────────

@app.route("/onboarding")
@require_login
def onboarding():
    return render_template("onboarding.html")


@app.route("/onboarding/create", methods=["POST"])
@require_login
def onboarding_create():
    name = request.form.get("name", "").strip()
    if not name:
        return render_template("onboarding.html", create_error="Workspace name is required")
    result, status = auth_post("/auth/workspaces", {"name": name}, headers=_jwt_headers())
    if status == 201 and result:
        _store_workspace_in_session(result)
        return redirect(url_for("index"))
    error = (result or {}).get("error") or "Failed to create workspace"
    return render_template("onboarding.html", create_error=error)


@app.route("/onboarding/join", methods=["POST"])
@require_login
def onboarding_join():
    invite_code = request.form.get("invite_code", "").strip()
    if not invite_code:
        return render_template("onboarding.html", join_error="Invite code is required")
    result, status = auth_post("/auth/workspaces/join", {"invite_code": invite_code},
                               headers=_jwt_headers())
    if status in (200, 201) and result:
        if result.get("status") == "pending":
            return redirect(url_for("workspace_pending"))
        _store_workspace_in_session(result)
        return redirect(url_for("index"))
    error = (result or {}).get("error") or "Invalid invite code"
    return render_template("onboarding.html", join_error=error)


@app.route("/workspace-pending")
@require_login
def workspace_pending():
    return render_template("workspace_pending.html")


@app.route("/switch-workspace/<int:workspace_id>")
@require_login
def switch_workspace(workspace_id):
    workspaces = session.get("workspaces") or []
    if any(w["workspace_id"] == workspace_id for w in workspaces):
        session["active_workspace_id"] = workspace_id
        session.modified = True
    return redirect(url_for("index"))


# ── Protected page routes ──────────────────────────────────────────────────────

@app.route("/")
@require_login
def index():
    all_boxes, locations = sidebar_data()
    all_items = backend_get("/api/items") or []
    boxes_map = {b["id"]: b for b in all_boxes}
    return render_template("index.html", boxes=all_boxes, items=all_items,
                           boxes_map=boxes_map, locations=locations,
                           all_boxes=all_boxes)


@app.route("/boxes/<int:box_id>")
@require_login
def box_detail(box_id):
    box = backend_get(f"/api/boxes/{box_id}")
    if not box:
        return render_template("error.html", message="Box not found"), 404
    all_items = backend_get("/api/items") or []
    box_items = [i for i in all_items if i.get("box_id") == box_id]
    all_boxes, locations = sidebar_data()
    return render_template("box_detail.html", box=box, items=box_items,
                           locations=locations, all_boxes=all_boxes)


# ── QR target ────────────────────────────────────────────────────────────────
# Single stable URL regardless of visibility: <FRONTEND_BASE_URL>/box/<id>.
# Public boxes render directly (no auth); private boxes require login, then
# land back here and get redirected into the authenticated box page.

@app.route("/box/<int:box_id>")
def box_qr_target(box_id):
    content, status, _ = http_request("GET", f"{BACKEND_URL}/api/boxes/{box_id}/public", timeout=5)
    data = parse_json(content) if content else None
    if status == 200 and data:
        return render_template("box_public.html", box=data, items=data.get("items") or [])
    if status == 403:
        if not session.get("token"):
            return redirect(url_for("login", next=request.path))
        return redirect(url_for("box_detail", box_id=box_id))
    return render_template("error.html", message="Box not found"), 404


@app.route("/items")
@require_login
def items():
    all_items = backend_get("/api/items") or []
    all_boxes, locations = sidebar_data()
    boxes_map = {b["id"]: b for b in all_boxes}
    return render_template("items.html", items=all_items, boxes_map=boxes_map,
                           locations=locations, all_boxes=all_boxes)


@app.route("/items/<int:item_id>")
@require_login
def item_detail(item_id):
    item = backend_get(f"/api/items/{item_id}")
    if not item:
        return render_template("error.html", message="Item not found"), 404
    box = None
    if item.get("box_id"):
        box = backend_get(f"/api/boxes/{item['box_id']}")
    all_boxes, locations = sidebar_data()
    return render_template("item_detail.html", item=item, box=box,
                           locations=locations, all_boxes=all_boxes)


@app.route("/search")
@require_login
def search():
    q       = request.args.get("q", "").strip()
    results = []
    all_boxes, locations = sidebar_data()
    if q:
        results = backend_get("/api/items/search", params={"q": q}) or []
    return render_template("search.html", q=q, results=results,
                           locations=locations, all_boxes=all_boxes)


# ── Proxy: static uploads ──────────────────────────────────────────────────────

@app.route("/uploads/<path:filename>")
@require_login
def proxy_upload(filename):
    content, status, content_type = http_request(
        "GET", f"{BACKEND_URL}/uploads/{filename}", timeout=10, headers=_auth_headers()
    )
    if content is None or status != 200:
        return Response(b"", status=404)
    return Response(content, mimetype=content_type or "image/jpeg")


# ── Proxy: single box JSON ─────────────────────────────────────────────────────

@app.route("/api/boxes/<int:box_id>", methods=["GET"])
@require_login
def get_box_json(box_id):
    data = backend_get(f"/api/boxes/{box_id}")
    if data is None:
        return jsonify({"error": "not found"}), 404
    return jsonify(data)


# ── Proxy: QR ──────────────────────────────────────────────────────────────────

@app.route("/api/boxes/<int:box_id>/qr")
@require_login
def box_qr(box_id):
    content, status, _ = http_request(
        "GET", f"{BACKEND_URL}/api/boxes/{box_id}/qr", timeout=10, headers=_auth_headers()
    )
    if content is None or status != 200:
        return Response(b"", status=503)
    return Response(content, mimetype="image/png")


# ── Proxy: image upload ────────────────────────────────────────────────────────

@app.route("/api/boxes/<int:box_id>/image", methods=["POST"])
@require_login
def upload_box_image(box_id):
    if "file" not in request.files:
        return jsonify({"error": "No file"}), 400
    f          = request.files["file"]
    file_bytes = f.read()
    content, status, _ = http_request(
        "POST",
        f"{BACKEND_URL}/api/boxes/{box_id}/image",
        files={"file": (f.filename, file_bytes, f.content_type)},
        timeout=15,
        headers=_auth_headers(),
    )
    if content is None or status is None:
        return jsonify({"error": "Upload failed"}), 500
    return jsonify(parse_json(content) or {}), status


@app.route("/api/items/<int:item_id>/image", methods=["POST"])
@require_login
def upload_item_image(item_id):
    if "file" not in request.files:
        return jsonify({"error": "No file"}), 400
    f          = request.files["file"]
    file_bytes = f.read()
    content, status, _ = http_request(
        "POST",
        f"{BACKEND_URL}/api/items/{item_id}/image",
        files={"file": (f.filename, file_bytes, f.content_type)},
        timeout=15,
        headers=_auth_headers(),
    )
    if content is None or status is None:
        return jsonify({"error": "Upload failed"}), 500
    return jsonify(parse_json(content) or {}), status


# ── Proxy: create ──────────────────────────────────────────────────────────────

@app.route("/api/boxes", methods=["GET"])
@require_login
def get_boxes():
    data = backend_get("/api/boxes")
    return jsonify(data or [])


@app.route("/api/boxes", methods=["POST"])
@require_login
def create_box():
    data = request.get_json(silent=True) or {}
    result, status = backend_post("/api/boxes", data)
    if result:
        return jsonify(result), status
    return jsonify({"error": "Failed to create box"}), status


@app.route("/api/items", methods=["GET"])
@require_login
def get_items():
    data = backend_get("/api/items")
    return jsonify(data or [])


@app.route("/api/items", methods=["POST"])
@require_login
def create_item():
    data = request.get_json(silent=True) or {}
    result, status = backend_post("/api/items", data)
    if result:
        return jsonify(result), status
    return jsonify({"error": "Failed to create item"}), status


# ── Proxy: update ──────────────────────────────────────────────────────────────

@app.route("/api/boxes/<int:box_id>", methods=["PUT"])
@require_login
def update_box(box_id):
    data = request.get_json(silent=True) or {}
    result, status = backend_put(f"/api/boxes/{box_id}", data)
    if status is None or status >= 500:
        return jsonify({"error": "Update failed"}), 500
    return jsonify(result or {}), status


@app.route("/api/boxes/<int:box_id>/visibility", methods=["PATCH"])
@require_login
def update_box_visibility(box_id):
    data = request.get_json(silent=True) or {}
    result, status = backend_patch(f"/api/boxes/{box_id}/visibility", data)
    if status is None or status >= 500:
        return jsonify({"error": "Update failed"}), 500
    return jsonify(result or {}), status


@app.route("/api/items/<int:item_id>", methods=["PUT"])
@require_login
def update_item(item_id):
    data = request.get_json(silent=True) or {}
    result, status = backend_put(f"/api/items/{item_id}", data)
    if status is None or status >= 500:
        return jsonify({"error": "Update failed"}), 500
    return jsonify(result or {}), status


# ── Proxy: delete ──────────────────────────────────────────────────────────────

@app.route("/api/boxes/<int:box_id>", methods=["DELETE"])
@require_login
def delete_box(box_id):
    status = backend_delete(f"/api/boxes/{box_id}")
    return Response(status=status)


@app.route("/api/items/<int:item_id>", methods=["DELETE"])
@require_login
def delete_item(item_id):
    status = backend_delete(f"/api/items/{item_id}")
    return Response(status=status)


# ── Proxy: workspace join requests (admin) ─────────────────────────────────────

@app.route("/api/workspace-requests")
@require_login
def get_workspace_requests():
    ws_id = session.get("active_workspace_id")
    if not ws_id:
        return jsonify([])
    content, status, _ = http_request(
        "GET",
        f"{AUTH_SERVICE_URL}/auth/workspaces/{ws_id}/requests",
        timeout=5,
        headers=_jwt_headers(),
    )
    if content is None or status is None or status >= 400:
        return jsonify([])
    return jsonify(parse_json(content) or [])


@app.route("/api/workspace-requests/<int:request_id>", methods=["PUT"])
@require_login
def resolve_workspace_request(request_id):
    ws_id = session.get("active_workspace_id")
    if not ws_id:
        return jsonify({"error": "No active workspace"}), 400
    data = request.get_json(silent=True) or {}
    content, status, _ = http_request(
        "PUT",
        f"{AUTH_SERVICE_URL}/auth/workspaces/{ws_id}/requests/{request_id}",
        json_data=data,
        timeout=5,
        headers=_jwt_headers(),
    )
    if content is None or status is None:
        return jsonify({"error": "Request failed"}), 500
    return jsonify(parse_json(content) or {}), status


# ── Proxy: locations (managed Location table in auth-service) ─────────────────

@app.route("/api/locations")
@require_login
def get_locations():
    ws_id = session.get("active_workspace_id")
    if not ws_id:
        return jsonify([])
    # Location records from auth-service
    loc_content, loc_status, _ = http_request(
        "GET",
        f"{AUTH_SERVICE_URL}/auth/workspaces/{ws_id}/locations",
        timeout=5,
        headers=_jwt_headers(),
    )
    locs = (parse_json(loc_content) or []) if loc_content and loc_status and loc_status < 400 else []
    # Box/item counts from backend
    stats_content, stats_status, _ = http_request(
        "GET",
        f"{BACKEND_URL}/api/locations/stats",
        timeout=5,
        headers=_auth_headers(),
    )
    stats = (parse_json(stats_content) or []) if stats_content and stats_status and stats_status < 400 else []
    stats_map = {s["name"]: s for s in stats}
    for loc in locs:
        s = stats_map.get(loc["name"], {})
        loc["box_count"]  = s.get("box_count",  0)
        loc["item_count"] = s.get("item_count", 0)
    return jsonify(locs)


@app.route("/api/locations", methods=["POST"])
@require_login
def create_location():
    ws_id = session.get("active_workspace_id")
    if not ws_id:
        return jsonify({"error": "No active workspace"}), 400
    data = request.get_json(silent=True) or {}
    content, status, _ = http_request(
        "POST",
        f"{AUTH_SERVICE_URL}/auth/workspaces/{ws_id}/locations",
        json_data=data,
        timeout=5,
        headers=_jwt_headers(),
    )
    if content is None or status is None:
        return jsonify({"error": "Request failed"}), 500
    return jsonify(parse_json(content) or {}), status


@app.route("/api/locations/<int:loc_id>", methods=["DELETE"])
@require_login
def delete_location(loc_id):
    ws_id = session.get("active_workspace_id")
    if not ws_id:
        return jsonify({"error": "No active workspace"}), 400
    content, status, _ = http_request(
        "DELETE",
        f"{AUTH_SERVICE_URL}/auth/workspaces/{ws_id}/locations/{loc_id}",
        timeout=5,
        headers=_jwt_headers(),
    )
    if content is None or status is None:
        return jsonify({"error": "Request failed"}), 500
    if status == 204:
        return "", 204
    return jsonify(parse_json(content) or {}), status


@app.route("/api/locations/clear", methods=["POST"])
@require_login
def clear_location():
    data = request.get_json(silent=True) or {}
    content, status, _ = http_request(
        "POST",
        f"{BACKEND_URL}/api/locations/clear",
        json_data=data,
        timeout=5,
        headers=_auth_headers(),
    )
    if content is None or status is None:
        return jsonify({"error": "Request failed"}), 500
    return jsonify(parse_json(content) or {}), status


# ── Proxy: workspace settings ──────────────────────────────────────────────────

@app.route("/api/workspace-settings", methods=["PUT"])
@require_login
def update_workspace_settings():
    ws_id = session.get("active_workspace_id")
    if not ws_id:
        return jsonify({"error": "No active workspace"}), 400
    data = request.get_json(silent=True) or {}
    content, status, _ = http_request(
        "PUT",
        f"{AUTH_SERVICE_URL}/auth/workspaces/{ws_id}",
        json_data=data,
        timeout=5,
        headers=_jwt_headers(),
    )
    if content is None or status is None:
        return jsonify({"error": "Request failed"}), 500
    result = parse_json(content)
    if status == 200 and result:
        workspaces = list(session.get("workspaces") or [])
        for w in workspaces:
            if w["workspace_id"] == ws_id:
                w["workspace_name"] = result.get("name", w["workspace_name"])
                break
        session["workspaces"] = workspaces
        session.modified = True
    return jsonify(result or {}), status


@app.route("/api/workspace-regenerate-invite", methods=["POST"])
@require_login
def regenerate_workspace_invite():
    ws_id = session.get("active_workspace_id")
    if not ws_id:
        return jsonify({"error": "No active workspace"}), 400
    content, status, _ = http_request(
        "POST",
        f"{AUTH_SERVICE_URL}/auth/workspaces/{ws_id}/regenerate-invite",
        json_data={},
        timeout=5,
        headers=_jwt_headers(),
    )
    if content is None or status is None:
        return jsonify({"error": "Request failed"}), 500
    result = parse_json(content)
    if status == 200 and result:
        workspaces = list(session.get("workspaces") or [])
        for w in workspaces:
            if w["workspace_id"] == ws_id:
                w["invite_code"] = result.get("invite_code", w.get("invite_code"))
                break
        session["workspaces"] = workspaces
        session.modified = True
    return jsonify(result or {}), status


# ── Proxy: workspace members ───────────────────────────────────────────────────

@app.route("/api/workspace-members")
@require_login
def get_workspace_members():
    ws_id = session.get("active_workspace_id")
    if not ws_id:
        return jsonify([])
    content, status, _ = http_request(
        "GET",
        f"{AUTH_SERVICE_URL}/auth/workspaces/{ws_id}/members",
        timeout=5,
        headers=_jwt_headers(),
    )
    if content is None or status is None or status >= 400:
        return jsonify([])
    return jsonify(parse_json(content) or [])


@app.route("/api/workspace-members/<int:uid>", methods=["PUT"])
@require_login
def update_workspace_member_role(uid):
    ws_id = session.get("active_workspace_id")
    if not ws_id:
        return jsonify({"error": "No active workspace"}), 400
    data = request.get_json(silent=True) or {}
    content, status, _ = http_request(
        "PUT",
        f"{AUTH_SERVICE_URL}/auth/workspaces/{ws_id}/members/{uid}",
        json_data=data,
        timeout=5,
        headers=_jwt_headers(),
    )
    if content is None or status is None:
        return jsonify({"error": "Request failed"}), 500
    return jsonify(parse_json(content) or {}), status


@app.route("/api/auth/me")
@require_login
def api_me():
    content, status, _ = http_request(
        "GET",
        f"{AUTH_SERVICE_URL}/auth/me",
        timeout=5,
        headers=_jwt_headers(),
    )
    if content is None or status is None:
        return jsonify({"error": "Request failed"}), 500
    user_data = parse_json(content) or {}
    if status == 200 and user_data.get("workspaces"):
        session["workspaces"] = user_data["workspaces"]
        if not session.get("active_workspace_id"):
            session["active_workspace_id"] = user_data["workspaces"][0]["workspace_id"]
        session.modified = True
    return jsonify(user_data), status


@app.route("/api/boxes/<int:box_id>/history")
@require_login
def box_history(box_id):
    data = backend_get(f"/api/boxes/{box_id}/history")
    return jsonify(data or [])


@app.route("/api/items/<int:item_id>/history")
@require_login
def item_history(item_id):
    data = backend_get(f"/api/items/{item_id}/history")
    return jsonify(data or [])


@app.route("/api/export/csv")
@require_login
def export_csv():
    content, status, _ = http_request(
        "GET", f"{BACKEND_URL}/api/export/csv", timeout=30, headers=_auth_headers()
    )
    if content is None or status != 200:
        return jsonify({"error": "Export failed"}), 500
    return Response(
        content,
        status=200,
        mimetype="text/csv",
        headers={"Content-Disposition": "attachment; filename=warehouse_export.csv"},
    )


@app.route("/api/export/excel")
@require_login
def export_excel():
    content, status, _ = http_request(
        "GET", f"{BACKEND_URL}/api/export/excel", timeout=30, headers=_auth_headers()
    )
    if content is None or status != 200:
        return jsonify({"error": "Export failed"}), 500
    return Response(
        content,
        status=200,
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": "attachment; filename=warehouse_export.xlsx"},
    )


@app.route("/api/refresh-session", methods=["POST"])
@require_login
def refresh_session():
    content, status, _ = http_request(
        "GET",
        f"{AUTH_SERVICE_URL}/auth/me",
        timeout=5,
        headers=_jwt_headers(),
    )
    if content is None or status is None or status != 200:
        return jsonify({"ok": False}), 500
    user_data = parse_json(content) or {}
    workspaces = user_data.get("workspaces") or []
    session["workspaces"] = workspaces
    if workspaces:
        ws_id = session.get("active_workspace_id")
        if not ws_id or not any(w["workspace_id"] == ws_id for w in workspaces):
            session["active_workspace_id"] = workspaces[0]["workspace_id"]
    first_name   = (user_data.get("first_name") or "").strip()
    last_name    = (user_data.get("last_name")  or "").strip()
    display_name = " ".join(filter(None, [first_name, last_name])) or None
    if display_name:
        user_data["display_name"] = display_name
    session["user"] = user_data
    session.modified = True
    return jsonify({"ok": True})


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080)
