import os
import io
from datetime import datetime

import qrcode
from flask import Flask, jsonify, request, send_file, abort
from flask_sqlalchemy import SQLAlchemy

app = Flask(__name__)
app.config["SQLALCHEMY_DATABASE_URI"] = os.environ.get("DATABASE_URL", "mysql+pymysql://root:root@localhost/warehouse")
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

db = SQLAlchemy(app)


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------

class Box(db.Model):
    __tablename__ = "boxes"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(255), nullable=False)
    location = db.Column(db.String(255))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    items = db.relationship("Item", backref="box", lazy=True)

    def to_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "location": self.location,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class Item(db.Model):
    __tablename__ = "items"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(255), nullable=False)
    category = db.Column(db.String(255))
    box_id = db.Column(db.Integer, db.ForeignKey("boxes.id"), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    tags = db.relationship("Tag", backref="item", lazy=True, cascade="all, delete-orphan")

    def to_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "category": self.category,
            "box_id": self.box_id,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "tags": [t.name for t in self.tags],
        }


class Tag(db.Model):
    __tablename__ = "tags"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(255), nullable=False)
    item_id = db.Column(db.Integer, db.ForeignKey("items.id"), nullable=False)

    def to_dict(self):
        return {"id": self.id, "name": self.name, "item_id": self.item_id}


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------

@app.route("/health")
def health():
    return jsonify({"status": "ok"})


# ---------------------------------------------------------------------------
# Boxes
# ---------------------------------------------------------------------------

@app.route("/api/boxes", methods=["GET"])
def get_boxes():
    boxes = Box.query.all()
    return jsonify([b.to_dict() for b in boxes])


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
    box = db.get_or_404(Box, box_id)
    return jsonify(box.to_dict())


@app.route("/api/boxes/<int:box_id>/qr", methods=["GET"])
def get_box_qr(box_id):
    from PIL import Image, ImageDraw, ImageFont

    box = db.get_or_404(Box, box_id)
    qr_data = f"box:{box.id}:{box.name}"
    qr_img = qrcode.make(qr_data).convert("RGB")

    qr_w, qr_h = qr_img.size
    font = ImageFont.load_default(size=20)
    label = f"ID: {box.id} | {box.name}"
    banner_h = 40

    combined = Image.new("RGB", (qr_w, qr_h + banner_h), "white")
    combined.paste(qr_img, (0, 0))

    draw = ImageDraw.Draw(combined)
    bbox = draw.textbbox((0, 0), label, font=font)
    text_x = (qr_w - (bbox[2] - bbox[0])) // 2
    text_y = qr_h + (banner_h - (bbox[3] - bbox[1])) // 2
    draw.text((text_x, text_y), label, fill="black", font=font)

    buf = io.BytesIO()
    combined.save(buf, format="PNG")
    buf.seek(0)
    return send_file(buf, mimetype="image/png")


# ---------------------------------------------------------------------------
# Items
# ---------------------------------------------------------------------------

@app.route("/api/items", methods=["GET"])
def get_items():
    items = Item.query.all()
    return jsonify([i.to_dict() for i in items])


@app.route("/api/items", methods=["POST"])
def create_item():
    data = request.get_json(silent=True) or {}
    name = data.get("name")
    if not name:
        abort(400, description="'name' is required")

    box_id = data.get("box_id")
    if box_id is not None:
        db.get_or_404(Box, box_id)

    item = Item(name=name, category=data.get("category"), box_id=box_id)
    db.session.add(item)
    db.session.flush()  # get item.id before adding tags

    for tag_name in data.get("tags", []):
        db.session.add(Tag(name=tag_name, item_id=item.id))

    db.session.commit()
    return jsonify(item.to_dict()), 201


@app.route("/api/items/<int:item_id>", methods=["GET"])
def get_item(item_id):
    item = db.get_or_404(Item, item_id)
    return jsonify(item.to_dict())


@app.route("/api/items/search", methods=["GET"])
def search_items():
    q = request.args.get("q", "").strip()
    if not q:
        abort(400, description="Query parameter 'q' is required")

    pattern = f"%{q}%"
    items = (
        Item.query
        .outerjoin(Tag)
        .filter(
            db.or_(
                Item.name.ilike(pattern),
                Tag.name.ilike(pattern),
            )
        )
        .distinct()
        .all()
    )
    return jsonify([i.to_dict() for i in items])


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
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    with app.app_context():
        db.create_all()
    app.run(host="0.0.0.0", port=8080)
