import io
import os
import time
import uuid
from datetime import datetime

import qrcode
from flask import Flask, jsonify, request, send_file, send_from_directory, abort
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import event, text
from werkzeug.utils import secure_filename

app = Flask(__name__)
app.config["SQLALCHEMY_DATABASE_URI"] = os.environ.get("DATABASE_URL", "mysql+pymysql://root:root@localhost/warehouse")
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

db = SQLAlchemy(app)

UPLOAD_FOLDER = os.environ.get("UPLOAD_FOLDER", "/app/uploads")
ALLOWED_EXTENSIONS = {"jpg", "jpeg", "png", "gif", "webp"}

# Ensure the uploads directory exists at startup (before any request comes in)
os.makedirs(UPLOAD_FOLDER, exist_ok=True)


def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


def save_upload(file, prefix):
    os.makedirs(UPLOAD_FOLDER, exist_ok=True)
    safe_name = secure_filename(file.filename or "upload")
    # Fallback extension if secure_filename strips everything
    parts = safe_name.rsplit(".", 1)
    ext   = parts[1].lower() if len(parts) == 2 else "jpg"
    filename = f"{prefix}_{uuid.uuid4().hex[:10]}.{ext}"
    dest = os.path.join(UPLOAD_FOLDER, filename)
    file.save(dest)
    print(f"[upload] saved → {dest}  (size={os.path.getsize(dest)}B)", flush=True)
    return filename


def remove_file(filename):
    if filename:
        path = os.path.join(UPLOAD_FOLDER, filename)
        if os.path.exists(path):
            os.remove(path)


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------

class Box(db.Model):
    __tablename__ = "boxes"

    id         = db.Column(db.Integer, primary_key=True)
    name       = db.Column(db.String(255), nullable=False)
    location   = db.Column(db.String(255))
    code       = db.Column(db.String(10), unique=True, nullable=False, default="")
    image      = db.Column(db.String(255), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    items = db.relationship("Item", backref="box", lazy=True)

    def to_dict(self):
        return {
            "id":         self.id,
            "code":       self.code,
            "name":       self.name,
            "location":   self.location,
            "image":      self.image,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }

    @staticmethod
    def _generate_code(mapper, connection, target):
        connection.execute(
            mapper.persist_selectable.update()
            .where(mapper.persist_selectable.c.id == target.id)
            .values(code=f"B{target.id:03d}")
        )
        target.code = f"B{target.id:03d}"


class Item(db.Model):
    __tablename__ = "items"

    id         = db.Column(db.Integer, primary_key=True)
    name       = db.Column(db.String(255), nullable=False)
    category   = db.Column(db.String(255))
    location   = db.Column(db.String(255), nullable=True)
    code       = db.Column(db.String(10), unique=True, nullable=False, default="")
    box_id     = db.Column(db.Integer, db.ForeignKey("boxes.id"), nullable=True)
    image      = db.Column(db.String(255), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    tags = db.relationship("Tag", backref="item", lazy=True, cascade="all, delete-orphan")

    def to_dict(self):
        return {
            "id":         self.id,
            "code":       self.code,
            "name":       self.name,
            "category":   self.category,
            "location":   self.location,
            "box_id":     self.box_id,
            "image":      self.image,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "tags":       [t.name for t in self.tags],
        }

    @staticmethod
    def _generate_code(mapper, connection, target):
        connection.execute(
            mapper.persist_selectable.update()
            .where(mapper.persist_selectable.c.id == target.id)
            .values(code=f"I{target.id:03d}")
        )
        target.code = f"I{target.id:03d}"


event.listen(Box,  "after_insert", Box._generate_code)
event.listen(Item, "after_insert", Item._generate_code)


class Tag(db.Model):
    __tablename__ = "tags"

    id      = db.Column(db.Integer, primary_key=True)
    name    = db.Column(db.String(255), nullable=False)
    item_id = db.Column(db.Integer, db.ForeignKey("items.id"), nullable=False)

    def to_dict(self):
        return {"id": self.id, "name": self.name, "item_id": self.item_id}


# ---------------------------------------------------------------------------
# DB init — runs at import time so gunicorn workers also apply migrations
# ---------------------------------------------------------------------------

def _run_migrations(conn):
    """ADD COLUMN statements that are safe to repeat (ignored if column exists)."""
    migrations = [
        ("boxes", "image",    "VARCHAR(255)"),
        ("items", "image",    "VARCHAR(255)"),
        ("items", "location", "VARCHAR(255)"),
    ]
    for table, col, col_type in migrations:
        try:
            conn.execute(text(f"ALTER TABLE `{table}` ADD COLUMN `{col}` {col_type}"))
            conn.commit()
            print(f"[db] ALTER TABLE {table}: added column {col}", flush=True)
        except Exception as e:
            # Column already exists or other benign error — skip
            conn.rollback()


def _init_db():
    """Create tables and apply migrations. Retries up to 60 s for MySQL readiness."""
    for attempt in range(12):
        try:
            with app.app_context():
                db.create_all()
                with db.engine.connect() as conn:
                    _run_migrations(conn)
            print("[db] init complete", flush=True)
            return
        except Exception as exc:
            print(f"[db] attempt {attempt + 1}/12 failed: {exc}", flush=True)
            time.sleep(5)
    print("[db] WARNING: could not complete DB init after 12 attempts", flush=True)


_init_db()


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------

@app.route("/health")
def health():
    return jsonify({"status": "ok"})


# ---------------------------------------------------------------------------
# Static uploads
# ---------------------------------------------------------------------------

@app.route("/uploads/<path:filename>")
def serve_upload(filename):
    path = os.path.join(UPLOAD_FOLDER, filename)
    if not os.path.exists(path):
        print(f"[serve] 404 – file not found: {path}", flush=True)
        abort(404)
    return send_from_directory(UPLOAD_FOLDER, filename)


# ---------------------------------------------------------------------------
# Boxes — CRUD
# ---------------------------------------------------------------------------

@app.route("/api/boxes", methods=["GET"])
def get_boxes():
    return jsonify([b.to_dict() for b in Box.query.all()])


@app.route("/api/boxes", methods=["POST"])
def create_box():
    data = request.get_json(silent=True) or {}
    name = data.get("name")
    if not name:
        abort(400, description="'name' is required")
    box = Box(name=name, location=data.get("location"))
    db.session.add(box)
    db.session.commit()
    return jsonify(box.to_dict()), 201


@app.route("/api/boxes/<int:box_id>", methods=["GET"])
def get_box(box_id):
    return jsonify(db.get_or_404(Box, box_id).to_dict())


@app.route("/api/boxes/<int:box_id>", methods=["PUT"])
def update_box(box_id):
    box  = db.get_or_404(Box, box_id)
    data = request.get_json(silent=True) or {}
    if data.get("name"):
        box.name = data["name"]
    if "location" in data:
        box.location = data["location"] or None
    db.session.commit()
    return jsonify(box.to_dict())


@app.route("/api/boxes/<int:box_id>", methods=["DELETE"])
def delete_box(box_id):
    box = db.get_or_404(Box, box_id)
    remove_file(box.image)
    for item in box.items:
        item.box_id = None
    db.session.delete(box)
    db.session.commit()
    return "", 204


# ---------------------------------------------------------------------------
# Boxes — image & QR
# ---------------------------------------------------------------------------

@app.route("/api/boxes/<int:box_id>/image", methods=["POST"])
def upload_box_image(box_id):
    print(f"[upload] POST /api/boxes/{box_id}/image — files={list(request.files.keys())}", flush=True)
    box = db.get_or_404(Box, box_id)
    if "file" not in request.files:
        print(f"[upload] box {box_id}: no 'file' key in request.files", flush=True)
        abort(400, description="No file provided")
    file = request.files["file"]
    print(f"[upload] box {box_id}: filename={file.filename!r}  content_type={file.content_type!r}", flush=True)
    if not file.filename or not allowed_file(file.filename):
        print(f"[upload] box {box_id}: rejected — allowed_file={allowed_file(file.filename or '')}", flush=True)
        abort(400, description="Invalid file type — use jpg, png, gif, or webp")
    remove_file(box.image)
    box.image = save_upload(file, f"box_{box_id}")
    db.session.commit()
    print(f"[upload] box {box_id}: DB updated, image={box.image}", flush=True)
    return jsonify(box.to_dict())


@app.route("/api/boxes/<int:box_id>/qr", methods=["GET"])
def get_box_qr(box_id):
    from PIL import Image, ImageDraw, ImageFont

    box = db.get_or_404(Box, box_id)
    qr_data = f"box:{box.code}:{box.name}"
    qr_img  = qrcode.make(qr_data).convert("RGB")

    qr_w, qr_h = qr_img.size
    font     = ImageFont.load_default(size=20)
    label    = f"ID: {box.code} | {box.name}"
    banner_h = 40

    combined = Image.new("RGB", (qr_w, qr_h + banner_h), "white")
    combined.paste(qr_img, (0, 0))

    draw   = ImageDraw.Draw(combined)
    bbox   = draw.textbbox((0, 0), label, font=font)
    text_x = (qr_w - (bbox[2] - bbox[0])) // 2
    text_y = qr_h + (banner_h - (bbox[3] - bbox[1])) // 2
    draw.text((text_x, text_y), label, fill="black", font=font)

    buf = io.BytesIO()
    combined.save(buf, format="PNG")
    buf.seek(0)
    return send_file(buf, mimetype="image/png")


# ---------------------------------------------------------------------------
# Items — CRUD
# ---------------------------------------------------------------------------

@app.route("/api/items", methods=["GET"])
def get_items():
    return jsonify([i.to_dict() for i in Item.query.all()])


@app.route("/api/items", methods=["POST"])
def create_item():
    data = request.get_json(silent=True) or {}
    name = data.get("name")
    if not name:
        abort(400, description="'name' is required")

    box_id = data.get("box_id")
    if box_id is not None:
        db.get_or_404(Box, box_id)

    item = Item(
        name     = name,
        category = data.get("category"),
        location = data.get("location"),
        box_id   = box_id,
    )
    db.session.add(item)
    db.session.flush()

    for tag_name in data.get("tags", []):
        db.session.add(Tag(name=tag_name, item_id=item.id))

    db.session.commit()
    return jsonify(item.to_dict()), 201


@app.route("/api/items/search", methods=["GET"])
def search_items():
    q = request.args.get("q", "").strip()
    if not q:
        abort(400, description="Query parameter 'q' is required")

    pattern = f"%{q}%"
    items = (
        Item.query
        .outerjoin(Tag)
        .filter(db.or_(
            Item.name.ilike(pattern),
            Item.category.ilike(pattern),
            Item.location.ilike(pattern),
            Tag.name.ilike(pattern),
        ))
        .distinct()
        .all()
    )
    return jsonify([i.to_dict() for i in items])


@app.route("/api/items/<int:item_id>", methods=["GET"])
def get_item(item_id):
    return jsonify(db.get_or_404(Item, item_id).to_dict())


@app.route("/api/items/<int:item_id>", methods=["PUT"])
def update_item(item_id):
    item = db.get_or_404(Item, item_id)
    data = request.get_json(silent=True) or {}

    if data.get("name"):
        item.name = data["name"]
    if "category" in data:
        item.category = data["category"] or None
    if "location" in data:
        item.location = data["location"] or None
    if "box_id" in data:
        box_id = data["box_id"]
        if box_id is not None:
            db.get_or_404(Box, box_id)
        item.box_id = box_id

    if "tags" in data:
        for tag in list(item.tags):
            db.session.delete(tag)
        db.session.flush()
        for tag_name in data["tags"]:
            db.session.add(Tag(name=tag_name, item_id=item.id))

    db.session.commit()
    return jsonify(item.to_dict())


@app.route("/api/items/<int:item_id>", methods=["DELETE"])
def delete_item(item_id):
    item = db.get_or_404(Item, item_id)
    remove_file(item.image)
    db.session.delete(item)
    db.session.commit()
    return "", 204


# ---------------------------------------------------------------------------
# Items — image
# ---------------------------------------------------------------------------

@app.route("/api/items/<int:item_id>/image", methods=["POST"])
def upload_item_image(item_id):
    print(f"[upload] POST /api/items/{item_id}/image — files={list(request.files.keys())}", flush=True)
    item = db.get_or_404(Item, item_id)
    if "file" not in request.files:
        print(f"[upload] item {item_id}: no 'file' key in request.files", flush=True)
        abort(400, description="No file provided")
    file = request.files["file"]
    print(f"[upload] item {item_id}: filename={file.filename!r}  content_type={file.content_type!r}", flush=True)
    if not file.filename or not allowed_file(file.filename):
        print(f"[upload] item {item_id}: rejected — allowed_file={allowed_file(file.filename or '')}", flush=True)
        abort(400, description="Invalid file type — use jpg, png, gif, or webp")
    remove_file(item.image)
    item.image = save_upload(file, f"item_{item_id}")
    db.session.commit()
    print(f"[upload] item {item_id}: DB updated, image={item.image}", flush=True)
    return jsonify(item.to_dict())


# ---------------------------------------------------------------------------
# Error handlers
# ---------------------------------------------------------------------------

@app.errorhandler(400)
def bad_request(e):
    return jsonify({"error": str(e.description)}), 400


@app.errorhandler(404)
def not_found(e):
    return jsonify({"error": "not found"}), 404


# ---------------------------------------------------------------------------
# Entry point (python app.py)
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080)
