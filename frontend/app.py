import os
import json
import uuid
import urllib.parse
import urllib.request
from urllib.error import HTTPError, URLError

from flask import Flask, render_template, request, jsonify, Response

app = Flask(__name__)

BACKEND_URL = os.environ.get("BACKEND_URL", "http://backend:8080")


def encode_multipart_formdata(fields, files):
    boundary = uuid.uuid4().hex
    lines = []

    for name, value in (fields or {}).items():
        lines.append(f"--{boundary}".encode("utf-8"))
        lines.append(f'Content-Disposition: form-data; name="{name}"'.encode("utf-8"))
        lines.append(b"")
        if isinstance(value, str):
            lines.append(value.encode("utf-8"))
        else:
            lines.append(str(value).encode("utf-8"))

    for name, (filename, file_value, content_type) in (files or {}).items():
        if isinstance(file_value, bytes):
            file_content = file_value
        else:
            file_content = file_value.read()

        lines.append(f"--{boundary}".encode("utf-8"))
        lines.append(
            f'Content-Disposition: form-data; name="{name}"; filename="{filename}"'.encode(
                "utf-8"
            )
        )
        lines.append(
            f"Content-Type: {content_type or 'application/octet-stream'}".encode("utf-8")
        )
        lines.append(b"")
        lines.append(file_content)

    lines.append(f"--{boundary}--".encode("utf-8"))
    lines.append(b"")
    body = b"\r\n".join(lines)
    content_type = f"multipart/form-data; boundary={boundary}"
    return body, content_type


def http_request(method, url, params=None, json_data=None, files=None, timeout=5, headers=None):
    if params:
        url = f"{url}?{urllib.parse.urlencode(params)}"

    body = None
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
            content = resp.read()
            status = resp.getcode()
            content_type = resp.headers.get("Content-Type", "")
            return content, status, content_type
    except HTTPError as err:
        try:
            content = err.read()
        except Exception:
            content = b""
        status = err.code
        content_type = getattr(err, "headers", {}).get("Content-Type", "")
        return content, status, content_type
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
    content, status, _ = http_request("GET", f"{BACKEND_URL}{path}", params=params, timeout=5)
    if content is None or status is None or status >= 400:
        return None
    return parse_json(content)


def backend_post(path, data):
    content, status, _ = http_request(
        "POST",
        f"{BACKEND_URL}{path}",
        json_data=data,
        timeout=5,
    )
    if content is None or status is None:
        return None, 500
    result = parse_json(content)
    if status >= 400:
        return None, status
    return result, status


def backend_put(path, data):
    content, status, _ = http_request(
        "PUT",
        f"{BACKEND_URL}{path}",
        json_data=data,
        timeout=5,
    )
    if content is None or status is None:
        return None, 500
    return parse_json(content), status


def backend_delete(path):
    _, status, _ = http_request("DELETE", f"{BACKEND_URL}{path}", timeout=5)
    return status if status is not None else 500


def sidebar_data():
    boxes = backend_get("/api/boxes") or []
    locations = sorted(set(b.get("location") for b in boxes if b.get("location")))
    return boxes, locations


@app.route("/health")
def health():
    return jsonify({"status": "ok"})


@app.route("/")
def index():
    all_boxes, locations = sidebar_data()
    all_items = backend_get("/api/items") or []
    boxes_map = {b["id"]: b for b in all_boxes}
    return render_template("index.html", boxes=all_boxes, items=all_items,
                           boxes_map=boxes_map, locations=locations,
                           all_boxes=all_boxes)


@app.route("/boxes/<int:box_id>")
def box_detail(box_id):
    box = backend_get(f"/api/boxes/{box_id}")
    if not box:
        return render_template("error.html", message="Box not found"), 404
    all_items = backend_get("/api/items") or []
    box_items = [i for i in all_items if i.get("box_id") == box_id]
    all_boxes, locations = sidebar_data()
    return render_template("box_detail.html", box=box, items=box_items,
                           locations=locations, all_boxes=all_boxes)


@app.route("/items")
def items():
    all_items = backend_get("/api/items") or []
    all_boxes, locations = sidebar_data()
    boxes_map = {b["id"]: b for b in all_boxes}
    return render_template("items.html", items=all_items, boxes_map=boxes_map,
                           locations=locations, all_boxes=all_boxes)


@app.route("/items/<int:item_id>")
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
def search():
    q = request.args.get("q", "").strip()
    results = []
    all_boxes, locations = sidebar_data()
    if q:
        results = backend_get("/api/items/search", params={"q": q}) or []
    return render_template("search.html", q=q, results=results,
                           locations=locations, all_boxes=all_boxes)


# ── Proxy: static uploads ──────────────────────────────────────────────────

@app.route("/uploads/<path:filename>")
def proxy_upload(filename):
    content, status, content_type = http_request("GET", f"{BACKEND_URL}/uploads/{filename}", timeout=10)
    if content is None or status != 200:
        return Response(b"", status=404)
    return Response(content, mimetype=content_type or "image/jpeg")


# ── Proxy: single box JSON ────────────────────────────────────────────────

@app.route("/api/boxes/<int:box_id>", methods=["GET"])
def get_box_json(box_id):
    data = backend_get(f"/api/boxes/{box_id}")
    if data is None:
        return jsonify({"error": "not found"}), 404
    return jsonify(data)


# ── Proxy: QR ─────────────────────────────────────────────────────────────

@app.route("/api/boxes/<int:box_id>/qr")
def box_qr(box_id):
    content, status, _ = http_request("GET", f"{BACKEND_URL}/api/boxes/{box_id}/qr", timeout=10)
    if content is None or status != 200:
        return Response(b"", status=503)
    return Response(content, mimetype="image/png")


# ── Proxy: image upload ────────────────────────────────────────────────────

@app.route("/api/boxes/<int:box_id>/image", methods=["POST"])
def upload_box_image(box_id):
    if "file" not in request.files:
        return jsonify({"error": "No file"}), 400
    f = request.files["file"]
    print(f"[proxy] uploading box {box_id} image: filename={f.filename!r}", flush=True)
    file_bytes = f.read()
    content, status, _ = http_request(
        "POST",
        f"{BACKEND_URL}/api/boxes/{box_id}/image",
        files={"file": (f.filename, file_bytes, f.content_type)},
        timeout=15,
    )
    print(f"[proxy] backend responded {status}", flush=True)
    if content is None or status is None:
        return jsonify({"error": "Upload failed"}), 500
    return jsonify(parse_json(content) or {}), status


@app.route("/api/items/<int:item_id>/image", methods=["POST"])
def upload_item_image(item_id):
    if "file" not in request.files:
        return jsonify({"error": "No file"}), 400
    f = request.files["file"]
    print(f"[proxy] uploading item {item_id} image: filename={f.filename!r}", flush=True)
    file_bytes = f.read()
    content, status, _ = http_request(
        "POST",
        f"{BACKEND_URL}/api/items/{item_id}/image",
        files={"file": (f.filename, file_bytes, f.content_type)},
        timeout=15,
    )
    print(f"[proxy] backend responded {status}", flush=True)
    if content is None or status is None:
        return jsonify({"error": "Upload failed"}), 500
    return jsonify(parse_json(content) or {}), status


# ── Proxy: create ──────────────────────────────────────────────────────────

@app.route("/api/boxes", methods=["POST"])
def create_box():
    data = request.get_json(silent=True) or {}
    result, status = backend_post("/api/boxes", data)
    if result:
        return jsonify(result), status
    return jsonify({"error": "Failed to create box"}), status


@app.route("/api/items", methods=["POST"])
def create_item():
    data = request.get_json(silent=True) or {}
    result, status = backend_post("/api/items", data)
    if result:
        return jsonify(result), status
    return jsonify({"error": "Failed to create item"}), status


# ── Proxy: update (PUT) ────────────────────────────────────────────────────

@app.route("/api/boxes/<int:box_id>", methods=["PUT"])
def update_box(box_id):
    data = request.get_json(silent=True) or {}
    result, status = backend_put(f"/api/boxes/{box_id}", data)
    if status is None or status >= 500:
        return jsonify({"error": "Update failed"}), 500
    return jsonify(result or {}), status


@app.route("/api/items/<int:item_id>", methods=["PUT"])
def update_item(item_id):
    data = request.get_json(silent=True) or {}
    result, status = backend_put(f"/api/items/{item_id}", data)
    if status is None or status >= 500:
        return jsonify({"error": "Update failed"}), 500
    return jsonify(result or {}), status


# ── Proxy: delete (DELETE) ─────────────────────────────────────────────────

@app.route("/api/boxes/<int:box_id>", methods=["DELETE"])
def delete_box(box_id):
    status = backend_delete(f"/api/boxes/{box_id}")
    return Response(status=status)


@app.route("/api/items/<int:item_id>", methods=["DELETE"])
def delete_item(item_id):
    status = backend_delete(f"/api/items/{item_id}")
    return Response(status=status)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080)
