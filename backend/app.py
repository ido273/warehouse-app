import io
import json
import os
import time
import uuid
import urllib.request as _urllib_request
from datetime import datetime

import boto3
import qrcode
from flask import Flask, jsonify, request, send_file, send_from_directory, abort, Response
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import event, text
from werkzeug.utils import secure_filename

app = Flask(__name__)
app.config["SQLALCHEMY_DATABASE_URI"] = os.environ.get(
    "DATABASE_URL", "mysql+pymysql://root:root@localhost/warehouse"
)
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
# Keep pooled connections healthy: ping before use and recycle before MySQL's
# wait_timeout closes them, avoiding "MySQL server has gone away" after idle.
app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {"pool_pre_ping": True, "pool_recycle": 280}
# Cap upload size to protect memory / S3 from oversized or abusive uploads.
app.config["MAX_CONTENT_LENGTH"] = int(os.environ.get("MAX_UPLOAD_BYTES", 10 * 1024 * 1024))

db = SQLAlchemy(app)

AUTH_SERVICE_URL   = os.environ.get("AUTH_SERVICE_URL", "http://auth-service:8080")
FRONTEND_BASE_URL  = os.environ.get("FRONTEND_BASE_URL", "http://localhost:5000")
UPLOAD_FOLDER      = os.environ.get("UPLOAD_FOLDER", "/app/uploads")
ALLOWED_EXTENSIONS = {"jpg", "jpeg", "png", "gif", "webp"}

S3_BUCKET_NAME = os.environ.get("S3_BUCKET_NAME")
S3_REGION      = "eu-west-1"
S3_URL_PREFIX  = f"https://{S3_BUCKET_NAME}.s3.{S3_REGION}.amazonaws.com/"
s3_client      = boto3.client("s3", region_name=S3_REGION)

os.makedirs(UPLOAD_FOLDER, exist_ok=True)


def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


def upload_to_s3(file, prefix):
    safe_name = secure_filename(file.filename or "upload")
    parts     = safe_name.rsplit(".", 1)
    ext       = parts[1].lower() if len(parts) == 2 else "jpg"
    key       = f"images/{uuid.uuid4()}.{ext}"
    s3_client.upload_fileobj(file, S3_BUCKET_NAME, key)
    url = f"{S3_URL_PREFIX}{key}"
    print(f"[upload] uploaded → {url}", flush=True)
    return url


def remove_file(filename):
    if not filename:
        return
    if filename.startswith(S3_URL_PREFIX):
        key = filename[len(S3_URL_PREFIX):]
        try:
            s3_client.delete_object(Bucket=S3_BUCKET_NAME, Key=key)
        except Exception as exc:
            print(f"[upload] failed to delete s3 object {key}: {exc}", flush=True)
        return
    path = os.path.join(UPLOAD_FOLDER, filename)
    if os.path.exists(path):
        os.remove(path)


# ---------------------------------------------------------------------------
# Workspace + role helpers
# ---------------------------------------------------------------------------

def _get_workspace_id():
    """Return workspace_id from X-Workspace-ID header, or None."""
    ws_id = request.headers.get("X-Workspace-ID")
    if ws_id:
        try:
            return int(ws_id)
        except (ValueError, TypeError):
            pass
    return None


def _get_user_role_in_workspace():
    """Call auth-service /auth/me to get the caller's role in the active workspace."""
    auth_header = request.headers.get("Authorization")
    ws_id = _get_workspace_id()
    if not auth_header or not ws_id:
        return None
    try:
        req = _urllib_request.Request(
            f"{AUTH_SERVICE_URL}/auth/me",
            headers={"Authorization": auth_header},
            method="GET",
        )
        with _urllib_request.urlopen(req, timeout=3) as resp:
            data = json.loads(resp.read().decode())
        for w in (data.get("workspaces") or []):
            if w.get("workspace_id") == ws_id:
                return w.get("role")
    except Exception:
        pass
    return None


def _check_role(*allowed_roles):
    """Return error response tuple if caller's role is not in allowed_roles, else None."""
    role = _get_user_role_in_workspace()
    if not role or role not in allowed_roles:
        return jsonify({"error": "You don't have permission to perform this action"}), 403
    return None


def _check_workspace_access():
    """Verify the caller is a member of the workspace in X-Workspace-ID.

    Read endpoints previously trusted the X-Workspace-ID header without
    checking membership, so any authenticated user could read another
    workspace's data by changing the header (IDOR). Call this at the top of
    every read endpoint. Returns a 403 tuple when a workspace is requested the
    caller has no role in; returns None when access is allowed or when no
    workspace is set (endpoints already handle the no-workspace case).
    """
    if _get_workspace_id() is None:
        return None
    if not _get_user_role_in_workspace():
        return jsonify({"error": "You don't have access to this workspace"}), 403
    return None


def get_current_user_display_name():
    auth_header = request.headers.get("Authorization")
    if not auth_header:
        return "Unknown"
    try:
        req = _urllib_request.Request(
            f"{AUTH_SERVICE_URL}/auth/me",
            headers={"Authorization": auth_header},
            method="GET",
        )
        with _urllib_request.urlopen(req, timeout=3) as resp:
            data = json.loads(resp.read().decode())
        first   = (data.get("first_name") or "").strip()
        last    = (data.get("last_name")  or "").strip()
        display = " ".join(filter(None, [first, last]))
        return display or data.get("email") or "Unknown"
    except Exception:
        return "Unknown"


def log_change(entity_type, entity_id, action, changed_by, workspace_id, changes=None):
    if changes:
        for field, (old_val, new_val) in changes.items():
            db.session.add(ChangeLog(
                entity_type   = entity_type,
                entity_id     = entity_id,
                action        = action,
                field_changed = field,
                old_value     = str(old_val) if old_val is not None else None,
                new_value     = str(new_val) if new_val is not None else None,
                changed_by    = changed_by,
                workspace_id  = workspace_id,
            ))
    else:
        db.session.add(ChangeLog(
            entity_type  = entity_type,
            entity_id    = entity_id,
            action       = action,
            changed_by   = changed_by,
            workspace_id = workspace_id,
        ))


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------

class Box(db.Model):
    __tablename__ = "boxes"

    id               = db.Column(db.Integer, primary_key=True)
    name             = db.Column(db.String(255), nullable=False)
    location         = db.Column(db.String(255))
    code             = db.Column(db.String(10), unique=True, nullable=False, default="")
    image            = db.Column(db.String(255), nullable=True)
    is_public        = db.Column(db.Boolean, nullable=False, default=False)
    workspace_id     = db.Column(db.Integer, nullable=True, index=True)
    last_modified_by = db.Column(db.String(255), nullable=True)
    created_at       = db.Column(db.DateTime, default=datetime.utcnow)

    items = db.relationship("Item", backref="box", lazy=True)

    def to_dict(self):
        return {
            "id":               self.id,
            "code":             self.code,
            "name":             self.name,
            "location":         self.location,
            "image":            self.image,
            "is_public":        bool(self.is_public),
            "workspace_id":     self.workspace_id,
            "last_modified_by": self.last_modified_by,
            "created_at":       self.created_at.isoformat() if self.created_at else None,
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

    id               = db.Column(db.Integer, primary_key=True)
    name             = db.Column(db.String(255), nullable=False)
    category         = db.Column(db.String(255))
    location         = db.Column(db.String(255), nullable=True)
    code             = db.Column(db.String(10), unique=True, nullable=False, default="")
    box_id           = db.Column(db.Integer, db.ForeignKey("boxes.id"), nullable=True, index=True)
    image            = db.Column(db.String(255), nullable=True)
    quantity         = db.Column(db.Integer, nullable=False, default=1)
    workspace_id     = db.Column(db.Integer, nullable=True, index=True)
    last_modified_by = db.Column(db.String(255), nullable=True)
    created_at       = db.Column(db.DateTime, default=datetime.utcnow)

    tags = db.relationship("Tag", backref="item", lazy=True, cascade="all, delete-orphan")

    def to_dict(self):
        return {
            "id":               self.id,
            "code":             self.code,
            "name":             self.name,
            "category":         self.category,
            "location":         self.location,
            "box_id":           self.box_id,
            "image":            self.image,
            "quantity":         self.quantity if self.quantity is not None else 1,
            "workspace_id":     self.workspace_id,
            "last_modified_by": self.last_modified_by,
            "created_at":       self.created_at.isoformat() if self.created_at else None,
            "tags":             [t.name for t in self.tags],
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
    item_id = db.Column(db.Integer, db.ForeignKey("items.id"), nullable=False, index=True)

    def to_dict(self):
        return {"id": self.id, "name": self.name, "item_id": self.item_id}


class ChangeLog(db.Model):
    __tablename__ = "change_logs"

    id            = db.Column(db.Integer, primary_key=True)
    entity_type   = db.Column(db.String(10),  nullable=False)
    entity_id     = db.Column(db.Integer,     nullable=False)
    action        = db.Column(db.String(10),  nullable=False)
    field_changed = db.Column(db.String(255), nullable=True)
    old_value     = db.Column(db.Text,        nullable=True)
    new_value     = db.Column(db.Text,        nullable=True)
    changed_by    = db.Column(db.String(255), nullable=False)
    workspace_id  = db.Column(db.Integer,     nullable=False)
    created_at    = db.Column(db.DateTime,    default=datetime.utcnow)

    __table_args__ = (
        db.Index("ix_change_logs_entity", "entity_type", "entity_id", "workspace_id"),
    )

    def to_dict(self):
        return {
            "id":            self.id,
            "entity_type":   self.entity_type,
            "entity_id":     self.entity_id,
            "action":        self.action,
            "field_changed": self.field_changed,
            "old_value":     self.old_value,
            "new_value":     self.new_value,
            "changed_by":    self.changed_by,
            "workspace_id":  self.workspace_id,
            "created_at":    self.created_at.isoformat() if self.created_at else None,
        }


# ---------------------------------------------------------------------------
# DB init
# ---------------------------------------------------------------------------

def _run_migrations(conn):
    migrations = [
        ("boxes", "image",            "VARCHAR(255)"),
        ("items", "image",            "VARCHAR(255)"),
        ("items", "location",         "VARCHAR(255)"),
        ("boxes", "workspace_id",     "INT"),
        ("items", "workspace_id",     "INT"),
        ("items", "quantity",         "INT NOT NULL DEFAULT 1"),
        ("boxes", "last_modified_by", "VARCHAR(255)"),
        ("items", "last_modified_by", "VARCHAR(255)"),
        ("boxes", "is_public",        "TINYINT(1) NOT NULL DEFAULT 0"),
    ]
    for table, col, col_type in migrations:
        try:
            conn.execute(text(f"ALTER TABLE `{table}` ADD COLUMN `{col}` {col_type}"))
            conn.commit()
            print(f"[db] ALTER TABLE {table}: added column {col}", flush=True)
        except Exception:
            conn.rollback()

    # Indexes on hot query columns. create_all() covers fresh DBs; these add
    # them to pre-existing tables. Duplicate-index errors are ignored.
    indexes = [
        ("ix_boxes_workspace_id",  "boxes",       "(`workspace_id`)"),
        ("ix_items_workspace_id",  "items",       "(`workspace_id`)"),
        ("ix_items_box_id",        "items",       "(`box_id`)"),
        ("ix_tags_item_id",        "tags",        "(`item_id`)"),
        ("ix_change_logs_entity",  "change_logs", "(`entity_type`, `entity_id`, `workspace_id`)"),
    ]
    for name, table, cols in indexes:
        try:
            conn.execute(text(f"CREATE INDEX `{name}` ON `{table}` {cols}"))
            conn.commit()
            print(f"[db] CREATE INDEX {name} ON {table}", flush=True)
        except Exception:
            conn.rollback()


def _init_db():
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
        abort(404)
    return send_from_directory(UPLOAD_FOLDER, filename)


# ---------------------------------------------------------------------------
# Boxes — CRUD
# ---------------------------------------------------------------------------

@app.route("/api/boxes", methods=["GET"])
def get_boxes():
    err = _check_workspace_access()
    if err:
        return err
    ws_id = _get_workspace_id()
    if not ws_id:
        return jsonify([])
    return jsonify([b.to_dict() for b in Box.query.filter_by(workspace_id=ws_id).all()])


@app.route("/api/boxes", methods=["POST"])
def create_box():
    err = _check_role("contributor", "manager", "admin")
    if err:
        return err
    ws_id = _get_workspace_id()
    if not ws_id:
        abort(401, description="X-Workspace-ID header required")
    data = request.get_json(silent=True) or {}
    name = data.get("name")
    if not name:
        abort(400, description="'name' is required")
    user_display = get_current_user_display_name()
    box = Box(name=name, location=data.get("location"), workspace_id=ws_id,
              is_public=bool(data.get("is_public", False)), last_modified_by=user_display)
    db.session.add(box)
    db.session.flush()
    log_change("box", box.id, "created", user_display, ws_id)
    db.session.commit()
    return jsonify(box.to_dict()), 201


@app.route("/api/boxes/<int:box_id>", methods=["GET"])
def get_box(box_id):
    err = _check_workspace_access()
    if err:
        return err
    ws_id = _get_workspace_id()
    box   = Box.query.filter_by(id=box_id, workspace_id=ws_id).first_or_404()
    return jsonify(box.to_dict())


@app.route("/api/boxes/<int:box_id>", methods=["PUT"])
def update_box(box_id):
    err = _check_role("manager", "admin")
    if err:
        return err
    ws_id = _get_workspace_id()
    box   = Box.query.filter_by(id=box_id, workspace_id=ws_id).first_or_404()
    data  = request.get_json(silent=True) or {}
    changes = {}
    if data.get("name") and data["name"] != box.name:
        changes["name"] = (box.name, data["name"])
        box.name = data["name"]
    if "location" in data:
        new_loc = data["location"] or None
        if new_loc != box.location:
            changes["location"] = (box.location, new_loc)
        box.location = new_loc
    user_display = get_current_user_display_name()
    box.last_modified_by = user_display
    if changes:
        log_change("box", box.id, "updated", user_display, ws_id, changes)
    db.session.commit()
    return jsonify(box.to_dict())


@app.route("/api/boxes/<int:box_id>", methods=["DELETE"])
def delete_box(box_id):
    err = _check_role("manager", "admin")
    if err:
        return err
    ws_id = _get_workspace_id()
    box   = Box.query.filter_by(id=box_id, workspace_id=ws_id).first_or_404()
    user_display = get_current_user_display_name()
    log_change("box", box.id, "deleted", user_display, ws_id)
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
    err = _check_role("manager", "admin")
    if err:
        return err
    ws_id = _get_workspace_id()
    box   = Box.query.filter_by(id=box_id, workspace_id=ws_id).first_or_404()
    if "file" not in request.files:
        abort(400, description="No file provided")
    file = request.files["file"]
    if not file.filename or not allowed_file(file.filename):
        abort(400, description="Invalid file type — use jpg, png, gif, or webp")
    remove_file(box.image)
    box.image = upload_to_s3(file, f"box_{box_id}")
    user_display = get_current_user_display_name()
    box.last_modified_by = user_display
    log_change("box", box.id, "updated", user_display, ws_id, {"image": (None, box.image)})
    db.session.commit()
    return jsonify(box.to_dict())


@app.route("/api/boxes/<int:box_id>/qr", methods=["GET"])
def get_box_qr(box_id):
    from PIL import Image, ImageDraw, ImageFont
    from bidi.algorithm import get_display

    err = _check_workspace_access()
    if err:
        return err
    ws_id = _get_workspace_id()
    box   = Box.query.filter_by(id=box_id, workspace_id=ws_id).first_or_404()

    qr_data = f"{FRONTEND_BASE_URL.rstrip('/')}/box/{box.id}"
    qr_img  = qrcode.make(qr_data).convert("RGB")

    qr_w, qr_h = qr_img.size
    font     = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", size=20)
    label    = get_display(f"{box.code} | {box.name}")
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
# Boxes — public endpoint & visibility toggle
# ---------------------------------------------------------------------------

@app.route("/api/boxes/<int:box_id>/public", methods=["GET"])
def get_box_public(box_id):
    box = Box.query.filter_by(id=box_id).first_or_404()
    if not box.is_public:
        return jsonify({"error": "This box is not public"}), 403
    data = box.to_dict()
    data["items"] = [i.to_dict() for i in box.items]
    return jsonify(data)


@app.route("/api/boxes/<int:box_id>/visibility", methods=["PATCH"])
def update_box_visibility(box_id):
    err = _check_role("manager", "admin")
    if err:
        return err
    ws_id = _get_workspace_id()
    box   = Box.query.filter_by(id=box_id, workspace_id=ws_id).first_or_404()
    data  = request.get_json(silent=True) or {}
    if "is_public" not in data:
        return jsonify({"error": "'is_public' is required"}), 400
    old_val   = box.is_public
    box.is_public = bool(data["is_public"])
    user_display  = get_current_user_display_name()
    box.last_modified_by = user_display
    if old_val != box.is_public:
        log_change("box", box.id, "updated", user_display, ws_id,
                   {"is_public": (old_val, box.is_public)})
    db.session.commit()
    return jsonify(box.to_dict())


# ---------------------------------------------------------------------------
# Items — CRUD
# ---------------------------------------------------------------------------

@app.route("/api/items", methods=["GET"])
def get_items():
    err = _check_workspace_access()
    if err:
        return err
    ws_id = _get_workspace_id()
    if not ws_id:
        return jsonify([])
    return jsonify([i.to_dict() for i in Item.query.filter_by(workspace_id=ws_id).all()])


@app.route("/api/items", methods=["POST"])
def create_item():
    err = _check_role("contributor", "manager", "admin")
    if err:
        return err
    ws_id = _get_workspace_id()
    if not ws_id:
        abort(401, description="X-Workspace-ID header required")
    data = request.get_json(silent=True) or {}
    name = data.get("name")
    if not name:
        abort(400, description="'name' is required")

    box_id = data.get("box_id")
    if box_id is not None:
        Box.query.filter_by(id=box_id, workspace_id=ws_id).first_or_404()

    try:
        quantity = max(1, int(data.get("quantity") or 1))
    except (ValueError, TypeError):
        quantity = 1

    user_display = get_current_user_display_name()
    item = Item(
        name             = name,
        category         = data.get("category"),
        location         = data.get("location"),
        box_id           = box_id,
        quantity         = quantity,
        workspace_id     = ws_id,
        last_modified_by = user_display,
    )
    db.session.add(item)
    db.session.flush()

    for tag_name in data.get("tags", []):
        db.session.add(Tag(name=tag_name, item_id=item.id))

    log_change("item", item.id, "created", user_display, ws_id)
    db.session.commit()
    return jsonify(item.to_dict()), 201


@app.route("/api/items/search", methods=["GET"])
def search_items():
    err = _check_workspace_access()
    if err:
        return err
    ws_id = _get_workspace_id()
    q     = request.args.get("q", "").strip()
    if not q:
        abort(400, description="Query parameter 'q' is required")

    pattern = f"%{q}%"
    query   = (
        Item.query
        .outerjoin(Tag)
        .filter(db.or_(
            Item.name.ilike(pattern),
            Item.category.ilike(pattern),
            Item.location.ilike(pattern),
            Tag.name.ilike(pattern),
        ))
    )
    if ws_id:
        query = query.filter(Item.workspace_id == ws_id)
    return jsonify([i.to_dict() for i in query.distinct().all()])


@app.route("/api/items/<int:item_id>", methods=["GET"])
def get_item(item_id):
    err = _check_workspace_access()
    if err:
        return err
    ws_id = _get_workspace_id()
    item  = Item.query.filter_by(id=item_id, workspace_id=ws_id).first_or_404()
    return jsonify(item.to_dict())


@app.route("/api/items/<int:item_id>", methods=["PUT"])
def update_item(item_id):
    err = _check_role("manager", "admin")
    if err:
        return err
    ws_id = _get_workspace_id()
    item  = Item.query.filter_by(id=item_id, workspace_id=ws_id).first_or_404()
    data  = request.get_json(silent=True) or {}

    changes = {}
    if data.get("name") and data["name"] != item.name:
        changes["name"] = (item.name, data["name"])
        item.name = data["name"]
    if "category" in data:
        new_cat = data["category"] or None
        if new_cat != item.category:
            changes["category"] = (item.category, new_cat)
        item.category = new_cat
    if "location" in data:
        new_loc = data["location"] or None
        if new_loc != item.location:
            changes["location"] = (item.location, new_loc)
        item.location = new_loc
    if "box_id" in data:
        box_id = data["box_id"]
        if box_id is not None:
            Box.query.filter_by(id=box_id, workspace_id=ws_id).first_or_404()
        if box_id != item.box_id:
            changes["box_id"] = (item.box_id, box_id)
        item.box_id = box_id
    if "quantity" in data:
        try:
            new_qty = max(1, int(data["quantity"]))
            if new_qty != item.quantity:
                changes["quantity"] = (item.quantity, new_qty)
            item.quantity = new_qty
        except (ValueError, TypeError):
            pass
    if "tags" in data:
        old_tags = sorted([t.name for t in item.tags])
        new_tags = data["tags"]
        for tag in list(item.tags):
            db.session.delete(tag)
        db.session.flush()
        for tag_name in new_tags:
            db.session.add(Tag(name=tag_name, item_id=item.id))
        if old_tags != sorted(new_tags):
            changes["tags"] = (", ".join(old_tags), ", ".join(sorted(new_tags)))

    user_display = get_current_user_display_name()
    item.last_modified_by = user_display
    if changes:
        log_change("item", item.id, "updated", user_display, ws_id, changes)
    db.session.commit()
    return jsonify(item.to_dict())


@app.route("/api/items/<int:item_id>", methods=["DELETE"])
def delete_item(item_id):
    err = _check_role("manager", "admin")
    if err:
        return err
    ws_id = _get_workspace_id()
    item  = Item.query.filter_by(id=item_id, workspace_id=ws_id).first_or_404()
    user_display = get_current_user_display_name()
    log_change("item", item.id, "deleted", user_display, ws_id)
    remove_file(item.image)
    db.session.delete(item)
    db.session.commit()
    return "", 204


# ---------------------------------------------------------------------------
# Items — image
# ---------------------------------------------------------------------------

@app.route("/api/items/<int:item_id>/image", methods=["POST"])
def upload_item_image(item_id):
    err = _check_role("manager", "admin")
    if err:
        return err
    ws_id = _get_workspace_id()
    item  = Item.query.filter_by(id=item_id, workspace_id=ws_id).first_or_404()
    if "file" not in request.files:
        abort(400, description="No file provided")
    file = request.files["file"]
    if not file.filename or not allowed_file(file.filename):
        abort(400, description="Invalid file type — use jpg, png, gif, or webp")
    remove_file(item.image)
    item.image = upload_to_s3(file, f"item_{item_id}")
    user_display = get_current_user_display_name()
    item.last_modified_by = user_display
    log_change("item", item.id, "updated", user_display, ws_id, {"image": (None, item.image)})
    db.session.commit()
    return jsonify(item.to_dict())


# ---------------------------------------------------------------------------
# Locations — stats (box/item counts per location name)
# ---------------------------------------------------------------------------

@app.route("/api/locations/stats", methods=["GET"])
def get_location_stats():
    err = _check_workspace_access()
    if err:
        return err
    ws_id = _get_workspace_id()
    if not ws_id:
        return jsonify([])
    box_rows  = db.session.query(Box.location,  db.func.count(Box.id)).filter(
        Box.workspace_id  == ws_id, Box.location  != None).group_by(Box.location).all()
    item_rows = db.session.query(Item.location, db.func.count(Item.id)).filter(
        Item.workspace_id == ws_id, Item.location != None).group_by(Item.location).all()
    box_counts  = {loc: cnt for loc, cnt in box_rows}
    item_counts = {loc: cnt for loc, cnt in item_rows}
    all_names   = set(box_counts) | set(item_counts)
    return jsonify([
        {"name": name, "box_count": box_counts.get(name, 0), "item_count": item_counts.get(name, 0)}
        for name in sorted(all_names)
    ])


# ---------------------------------------------------------------------------
# Locations — clear by name (called when a location is deleted)
# ---------------------------------------------------------------------------

@app.route("/api/locations/clear", methods=["POST"])
def clear_location():
    err = _check_role("contributor", "manager", "admin")
    if err:
        return err
    ws_id = _get_workspace_id()
    if not ws_id:
        abort(401, description="X-Workspace-ID header required")
    data = request.get_json(silent=True) or {}
    name = data.get("name")
    if not name:
        return jsonify({"error": "name is required"}), 400
    Box.query.filter_by(workspace_id=ws_id, location=name).update({"location": None})
    Item.query.filter_by(workspace_id=ws_id, location=name).update({"location": None})
    db.session.commit()
    return jsonify({"cleared": True})


# ---------------------------------------------------------------------------
# History
# ---------------------------------------------------------------------------

@app.route("/api/boxes/<int:box_id>/history", methods=["GET"])
def get_box_history(box_id):
    err = _check_workspace_access()
    if err:
        return err
    ws_id = _get_workspace_id()
    logs  = ChangeLog.query.filter_by(entity_type="box", entity_id=box_id, workspace_id=ws_id)\
        .order_by(ChangeLog.created_at.desc()).all()
    return jsonify([l.to_dict() for l in logs])


@app.route("/api/items/<int:item_id>/history", methods=["GET"])
def get_item_history(item_id):
    err = _check_workspace_access()
    if err:
        return err
    ws_id = _get_workspace_id()
    logs  = ChangeLog.query.filter_by(entity_type="item", entity_id=item_id, workspace_id=ws_id)\
        .order_by(ChangeLog.created_at.desc()).all()
    return jsonify([l.to_dict() for l in logs])


# ---------------------------------------------------------------------------
# Export
# ---------------------------------------------------------------------------

@app.route("/api/export/csv", methods=["GET"])
def export_csv():
    import csv
    err = _check_workspace_access()
    if err:
        return err
    ws_id = _get_workspace_id()
    if not ws_id:
        abort(401, description="X-Workspace-ID header required")
    boxes = Box.query.filter_by(workspace_id=ws_id).order_by(Box.id).all()
    items = Item.query.filter_by(workspace_id=ws_id).order_by(Item.id).all()
    box_code_map = {b.id: b.code for b in boxes}

    output = io.StringIO()
    writer = csv.writer(output)

    writer.writerow(["BOXES"])
    writer.writerow(["code", "name", "location", "created_at"])
    for b in boxes:
        writer.writerow([
            b.code or "",
            b.name or "",
            b.location or "",
            b.created_at.isoformat() if b.created_at else "",
        ])

    writer.writerow([])

    writer.writerow(["ITEMS"])
    writer.writerow(["code", "name", "category", "location", "quantity", "tags", "box_code", "created_at"])
    for item in items:
        writer.writerow([
            item.code or "",
            item.name or "",
            item.category or "",
            item.location or "",
            item.quantity if item.quantity is not None else 1,
            "|".join(t.name for t in item.tags),
            box_code_map.get(item.box_id, "") if item.box_id else "",
            item.created_at.isoformat() if item.created_at else "",
        ])

    return Response(
        output.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": "attachment; filename=warehouse_export.csv"},
    )


@app.route("/api/export/excel", methods=["GET"])
def export_excel():
    import openpyxl
    from openpyxl.styles import Font
    err = _check_workspace_access()
    if err:
        return err
    ws_id = _get_workspace_id()
    if not ws_id:
        abort(401, description="X-Workspace-ID header required")
    boxes = Box.query.filter_by(workspace_id=ws_id).order_by(Box.id).all()
    items = Item.query.filter_by(workspace_id=ws_id).order_by(Item.id).all()
    box_code_map = {b.id: b.code for b in boxes}

    wb = openpyxl.Workbook()

    ws_boxes = wb.active
    ws_boxes.title = "Boxes"
    box_headers = ["code", "name", "location", "created_at"]
    ws_boxes.append(box_headers)
    for cell in ws_boxes[1]:
        cell.font = Font(bold=True)
    for b in boxes:
        ws_boxes.append([
            b.code or "",
            b.name or "",
            b.location or "",
            b.created_at.isoformat() if b.created_at else "",
        ])

    ws_items = wb.create_sheet("Items")
    item_headers = ["code", "name", "category", "location", "quantity", "tags", "box_code", "created_at"]
    ws_items.append(item_headers)
    for cell in ws_items[1]:
        cell.font = Font(bold=True)
    for item in items:
        ws_items.append([
            item.code or "",
            item.name or "",
            item.category or "",
            item.location or "",
            item.quantity if item.quantity is not None else 1,
            "|".join(t.name for t in item.tags),
            box_code_map.get(item.box_id, "") if item.box_id else "",
            item.created_at.isoformat() if item.created_at else "",
        ])

    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return send_file(
        buf,
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        as_attachment=True,
        download_name="warehouse_export.xlsx",
    )


# ---------------------------------------------------------------------------
# Error handlers
# ---------------------------------------------------------------------------

@app.errorhandler(400)
def bad_request(e):
    return jsonify({"error": str(e.description)}), 400


@app.errorhandler(401)
def unauthorized(e):
    return jsonify({"error": str(e.description)}), 401


@app.errorhandler(404)
def not_found(e):
    return jsonify({"error": "not found"}), 404


@app.errorhandler(413)
def payload_too_large(e):
    return jsonify({"error": "File too large"}), 413


@app.errorhandler(500)
def internal_error(e):
    db.session.rollback()
    return jsonify({"error": "Internal server error"}), 500


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080)
