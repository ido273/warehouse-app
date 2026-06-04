import os
import requests
from flask import Flask, render_template, request, jsonify, Response

app = Flask(__name__)

BACKEND_URL = os.environ.get("BACKEND_URL", "http://backend:8080")


def backend_get(path, params=None):
    try:
        r = requests.get(f"{BACKEND_URL}{path}", params=params, timeout=5)
        r.raise_for_status()
        return r.json()
    except Exception:
        return None


def backend_post(path, data):
    try:
        r = requests.post(f"{BACKEND_URL}{path}", json=data, timeout=5)
        r.raise_for_status()
        return r.json(), r.status_code
    except requests.HTTPError as e:
        return None, e.response.status_code if e.response else 500
    except Exception:
        return None, 500


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
    try:
        r = requests.get(f"{BACKEND_URL}/uploads/{filename}", timeout=10)
        content_type = r.headers.get("Content-Type", "image/jpeg")
        return Response(r.content, mimetype=content_type)
    except Exception:
        return Response(b"", status=404)


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
    try:
        r = requests.get(f"{BACKEND_URL}/api/boxes/{box_id}/qr", timeout=10)
        return Response(r.content, mimetype="image/png")
    except Exception:
        return Response(b"", status=503)


# ── Proxy: image upload ────────────────────────────────────────────────────

@app.route("/api/boxes/<int:box_id>/image", methods=["POST"])
def upload_box_image(box_id):
    if "file" not in request.files:
        return jsonify({"error": "No file"}), 400
    f = request.files["file"]
    print(f"[proxy] uploading box {box_id} image: filename={f.filename!r}", flush=True)
    try:
        r = requests.post(
            f"{BACKEND_URL}/api/boxes/{box_id}/image",
            files={"file": (f.filename, f.stream, f.content_type)},
            timeout=15,
        )
        print(f"[proxy] backend responded {r.status_code}", flush=True)
        return jsonify(r.json()), r.status_code
    except Exception as e:
        print(f"[proxy] upload_box_image error: {e}", flush=True)
        return jsonify({"error": "Upload failed"}), 500


@app.route("/api/items/<int:item_id>/image", methods=["POST"])
def upload_item_image(item_id):
    if "file" not in request.files:
        return jsonify({"error": "No file"}), 400
    f = request.files["file"]
    print(f"[proxy] uploading item {item_id} image: filename={f.filename!r}", flush=True)
    try:
        r = requests.post(
            f"{BACKEND_URL}/api/items/{item_id}/image",
            files={"file": (f.filename, f.stream, f.content_type)},
            timeout=15,
        )
        print(f"[proxy] backend responded {r.status_code}", flush=True)
        return jsonify(r.json()), r.status_code
    except Exception as e:
        print(f"[proxy] upload_item_image error: {e}", flush=True)
        return jsonify({"error": "Upload failed"}), 500


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
    try:
        r = requests.put(f"{BACKEND_URL}/api/boxes/{box_id}", json=data, timeout=5)
        return jsonify(r.json()), r.status_code
    except Exception:
        return jsonify({"error": "Update failed"}), 500


@app.route("/api/items/<int:item_id>", methods=["PUT"])
def update_item(item_id):
    data = request.get_json(silent=True) or {}
    try:
        r = requests.put(f"{BACKEND_URL}/api/items/{item_id}", json=data, timeout=5)
        return jsonify(r.json()), r.status_code
    except Exception:
        return jsonify({"error": "Update failed"}), 500


# ── Proxy: delete (DELETE) ─────────────────────────────────────────────────

@app.route("/api/boxes/<int:box_id>", methods=["DELETE"])
def delete_box(box_id):
    try:
        r = requests.delete(f"{BACKEND_URL}/api/boxes/{box_id}", timeout=5)
        return Response(status=r.status_code)
    except Exception:
        return Response(status=500)


@app.route("/api/items/<int:item_id>", methods=["DELETE"])
def delete_item(item_id):
    try:
        r = requests.delete(f"{BACKEND_URL}/api/items/{item_id}", timeout=5)
        return Response(status=r.status_code)
    except Exception:
        return Response(status=500)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080)
