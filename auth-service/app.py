import os
import secrets
import time
from datetime import datetime, timezone

from flask import Flask, jsonify, request
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import text
from flask_jwt_extended import (
    JWTManager, create_access_token, jwt_required,
    get_jwt_identity, get_jwt
)
from flask_bcrypt import Bcrypt

app = Flask(__name__)
app.config["SQLALCHEMY_DATABASE_URI"] = os.environ["DATABASE_URL"]
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.config["JWT_SECRET_KEY"] = os.environ["JWT_SECRET_KEY"]
app.config["JWT_BLACKLIST_ENABLED"] = True
app.config["JWT_BLACKLIST_TOKEN_CHECKS"] = ["access"]

db = SQLAlchemy(app)
jwt = JWTManager(app)
bcrypt = Bcrypt(app)

ROLES = ("admin", "manager", "contributor", "viewer")


# ── Models ────────────────────────────────────────────────────────────────────

class User(db.Model):
    __tablename__ = "users"
    id            = db.Column(db.Integer, primary_key=True)
    email         = db.Column(db.String(255), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    role          = db.Column(db.Enum(*ROLES), nullable=False, default="viewer")
    first_name    = db.Column(db.String(100), nullable=True)
    last_name     = db.Column(db.String(100), nullable=True)
    created_at    = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    locations     = db.relationship("UserLocation", backref="user",
                                    cascade="all, delete-orphan", lazy=True)
    workspace_memberships = db.relationship("UserWorkspace", back_populates="user",
                                            cascade="all, delete-orphan", lazy=True)

    def to_dict(self):
        return {
            "id":         self.id,
            "email":      self.email,
            "role":       self.role,
            "first_name": self.first_name,
            "last_name":  self.last_name,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "locations":  [loc.to_dict() for loc in self.locations],
            "workspaces": [uw.to_dict() for uw in self.workspace_memberships],
        }


class UserLocation(db.Model):
    __tablename__ = "user_locations"
    id            = db.Column(db.Integer, primary_key=True)
    user_id       = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    location_name = db.Column(db.String(255), nullable=False)
    access_type   = db.Column(db.Enum("all", "specific"), nullable=False, default="specific")

    def to_dict(self):
        return {
            "id":            self.id,
            "location_name": self.location_name,
            "access_type":   self.access_type,
        }


class Workspace(db.Model):
    __tablename__ = "workspaces"
    id          = db.Column(db.Integer, primary_key=True)
    name        = db.Column(db.String(255), nullable=False)
    owner_id    = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    invite_code = db.Column(db.String(8), unique=True, nullable=False)
    created_at  = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    members     = db.relationship("UserWorkspace", back_populates="workspace",
                                  cascade="all, delete-orphan", lazy=True)

    def to_dict(self):
        return {
            "id":          self.id,
            "name":        self.name,
            "owner_id":    self.owner_id,
            "invite_code": self.invite_code,
            "created_at":  self.created_at.isoformat() if self.created_at else None,
        }


class UserWorkspace(db.Model):
    __tablename__ = "user_workspaces"
    id           = db.Column(db.Integer, primary_key=True)
    user_id      = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    workspace_id = db.Column(db.Integer, db.ForeignKey("workspaces.id"), nullable=False)
    role         = db.Column(db.Enum(*ROLES), nullable=False, default="viewer")
    user         = db.relationship("User", back_populates="workspace_memberships")
    workspace    = db.relationship("Workspace", back_populates="members")

    def to_dict(self):
        ws = self.workspace
        return {
            "workspace_id":   self.workspace_id,
            "workspace_name": ws.name if ws else None,
            "invite_code":    ws.invite_code if ws else None,
            "role":           self.role,
        }


class WorkspaceInviteRequest(db.Model):
    __tablename__ = "workspace_invite_requests"
    id           = db.Column(db.Integer, primary_key=True)
    user_id      = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    workspace_id = db.Column(db.Integer, db.ForeignKey("workspaces.id"), nullable=False)
    status       = db.Column(db.Enum("pending", "approved", "rejected"),
                             nullable=False, default="pending")
    created_at   = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    user         = db.relationship("User")
    workspace    = db.relationship("Workspace")

    def to_dict(self):
        u = self.user
        first = (u.first_name or "").strip() if u else ""
        last  = (u.last_name  or "").strip() if u else ""
        display = " ".join(filter(None, [first, last])) or (u.email if u else None)
        return {
            "id":           self.id,
            "user_id":      self.user_id,
            "email":        u.email if u else None,
            "display_name": display,
            "workspace_id": self.workspace_id,
            "status":       self.status,
            "created_at":   self.created_at.isoformat() if self.created_at else None,
        }


class WorkspaceLocation(db.Model):
    __tablename__ = "workspace_locations"
    id           = db.Column(db.Integer, primary_key=True)
    name         = db.Column(db.String(255), nullable=False)
    workspace_id = db.Column(db.Integer, db.ForeignKey("workspaces.id"), nullable=False)
    created_at   = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    __table_args__ = (db.UniqueConstraint("name", "workspace_id", name="uq_loc_name_ws"),)

    def to_dict(self):
        return {
            "id":           self.id,
            "name":         self.name,
            "workspace_id": self.workspace_id,
            "created_at":   self.created_at.isoformat() if self.created_at else None,
        }


# ── Migrations ───────────────────────────────────────────────────────────────────

def _run_migrations():
    migrations = [
        ("users", "first_name", "VARCHAR(100)"),
        ("users", "last_name",  "VARCHAR(100)"),
    ]
    with db.engine.connect() as conn:
        for table, col, col_type in migrations:
            try:
                conn.execute(text(f"ALTER TABLE `{table}` ADD COLUMN `{col}` {col_type}"))
                conn.commit()
                print(f"[db] ALTER TABLE {table}: added column {col}", flush=True)
            except Exception:
                conn.rollback()


# In-memory JWT blocklist (single-instance)
_blocklist: set[str] = set()


@jwt.token_in_blocklist_loader
def check_blocklist(jwt_header, jwt_payload):
    return jwt_payload["jti"] in _blocklist


# ── Helpers ───────────────────────────────────────────────────────────────────

def _current_user():
    uid = get_jwt_identity()
    return db.session.get(User, int(uid))


def _require_admin():
    user = _current_user()
    if not user or user.role != "admin":
        return jsonify(error="Admin access required"), 403
    return user


def _require_workspace_admin(workspace_id):
    """Return (user, None) if current user is workspace admin, else (None, error_tuple)."""
    user = _current_user()
    if not user:
        return None, (jsonify(error="Unauthorized"), 401)
    uw = UserWorkspace.query.filter_by(user_id=user.id, workspace_id=workspace_id).first()
    if not uw or uw.role != "admin":
        return None, (jsonify(error="Workspace admin access required"), 403)
    return user, None


def _require_workspace_role(workspace_id, *allowed_roles):
    """Return (user, None) if current user has any of allowed_roles, else (None, error_tuple)."""
    user = _current_user()
    if not user:
        return None, (jsonify(error="Unauthorized"), 401)
    uw = UserWorkspace.query.filter_by(user_id=user.id, workspace_id=workspace_id).first()
    if not uw or uw.role not in allowed_roles:
        return None, (jsonify(error="Insufficient permissions"), 403)
    return user, None


# ── Auth routes ────────────────────────────────────────────────────────────────

@app.get("/health")
def health():
    return jsonify(status="ok")


@app.post("/auth/register")
def register():
    data       = request.get_json(silent=True) or {}
    email      = (data.get("email") or "").strip().lower()
    password   = data.get("password") or ""
    role       = (data.get("role") or "viewer").strip().lower()
    first_name = (data.get("first_name") or "").strip() or None
    last_name  = (data.get("last_name")  or "").strip() or None

    if not email or not password:
        return jsonify(error="email and password are required"), 400
    if role not in ROLES:
        return jsonify(error=f"role must be one of {ROLES}"), 400
    if User.query.filter_by(email=email).first():
        return jsonify(error="email already registered"), 409

    pw_hash = bcrypt.generate_password_hash(password).decode("utf-8")
    user = User(email=email, password_hash=pw_hash, role=role,
                first_name=first_name, last_name=last_name)
    db.session.add(user)
    db.session.commit()
    return jsonify(user.to_dict()), 201


@app.post("/auth/login")
def login():
    data     = request.get_json(silent=True) or {}
    email    = (data.get("email") or "").strip().lower()
    password = data.get("password") or ""

    user = User.query.filter_by(email=email).first()
    if not user or not bcrypt.check_password_hash(user.password_hash, password):
        return jsonify(error="invalid credentials"), 401

    token = create_access_token(identity=str(user.id))
    return jsonify(access_token=token, user=user.to_dict())


@app.post("/auth/logout")
@jwt_required()
def logout():
    _blocklist.add(get_jwt()["jti"])
    return jsonify(message="logged out")


@app.get("/auth/me")
@jwt_required()
def me():
    user = _current_user()
    if not user:
        return jsonify(error="user not found"), 404
    return jsonify(user.to_dict())


@app.get("/auth/users")
@jwt_required()
def list_users():
    result = _require_admin()
    if isinstance(result, tuple):
        return result
    users = User.query.order_by(User.created_at).all()
    return jsonify([u.to_dict() for u in users])


@app.delete("/auth/users/<int:uid>")
@jwt_required()
def delete_user(uid):
    result = _require_admin()
    if isinstance(result, tuple):
        return result
    user = db.session.get(User, uid)
    if not user:
        return jsonify(error="user not found"), 404
    db.session.delete(user)
    db.session.commit()
    return "", 204


@app.post("/auth/users/<int:uid>/locations")
@jwt_required()
def assign_locations(uid):
    result = _require_admin()
    if isinstance(result, tuple):
        return result

    user = db.session.get(User, uid)
    if not user:
        return jsonify(error="user not found"), 404

    data      = request.get_json(silent=True) or {}
    locations = data.get("locations")
    if not isinstance(locations, list):
        return jsonify(error="locations must be a list"), 400

    UserLocation.query.filter_by(user_id=uid).delete()
    for loc in locations:
        name        = (loc.get("location_name") or "").strip()
        access_type = (loc.get("access_type") or "specific").strip()
        if not name:
            continue
        if access_type not in ("all", "specific"):
            access_type = "specific"
        db.session.add(UserLocation(user_id=uid, location_name=name,
                                    access_type=access_type))
    db.session.commit()
    return jsonify(db.session.get(User, uid).to_dict())


# ── Workspace endpoints ────────────────────────────────────────────────────────

@app.post("/auth/workspaces")
@jwt_required()
def create_workspace():
    user = _current_user()
    if not user:
        return jsonify(error="Unauthorized"), 401
    data = request.get_json(silent=True) or {}
    name = (data.get("name") or "").strip()
    if not name:
        return jsonify(error="name is required"), 400

    workspace = Workspace(name=name, owner_id=user.id, invite_code=secrets.token_hex(4))
    db.session.add(workspace)
    db.session.flush()

    db.session.add(UserWorkspace(user_id=user.id, workspace_id=workspace.id, role="admin"))
    user.role = "admin"
    db.session.commit()

    result = workspace.to_dict()
    result["role"] = "admin"
    return jsonify(result), 201


@app.post("/auth/workspaces/join")
@jwt_required()
def join_workspace():
    user = _current_user()
    if not user:
        return jsonify(error="Unauthorized"), 401
    data        = request.get_json(silent=True) or {}
    invite_code = (data.get("invite_code") or "").strip()
    if not invite_code:
        return jsonify(error="invite_code is required"), 400

    workspace = Workspace.query.filter_by(invite_code=invite_code).first()
    if not workspace:
        return jsonify(error="Invalid invite code"), 404

    # Already a member — return current membership
    existing = UserWorkspace.query.filter_by(user_id=user.id,
                                             workspace_id=workspace.id).first()
    if existing:
        result = workspace.to_dict()
        result["role"] = existing.role
        return jsonify(result), 200

    # Already has a pending request
    pending = WorkspaceInviteRequest.query.filter_by(
        user_id=user.id, workspace_id=workspace.id, status="pending"
    ).first()
    if pending:
        return jsonify(status="pending",
                       message="Your request is already pending admin approval"), 200

    db.session.add(WorkspaceInviteRequest(user_id=user.id, workspace_id=workspace.id))
    db.session.commit()
    return jsonify(status="pending",
                   message="Your request has been sent to the admin for approval"), 200


@app.get("/auth/workspaces")
@jwt_required()
def list_workspaces():
    user = _current_user()
    if not user:
        return jsonify(error="Unauthorized"), 401
    result = []
    for uw in UserWorkspace.query.filter_by(user_id=user.id).all():
        d = uw.workspace.to_dict()
        d["role"] = uw.role
        result.append(d)
    return jsonify(result)


@app.get("/auth/workspaces/<int:workspace_id>/members")
@jwt_required()
def list_workspace_members(workspace_id):
    _, err = _require_workspace_admin(workspace_id)
    if err:
        return err
    workspace = db.session.get(Workspace, workspace_id)
    if not workspace:
        return jsonify(error="Workspace not found"), 404
    result = []
    for uw in UserWorkspace.query.filter_by(workspace_id=workspace_id).all():
        u = db.session.get(User, uw.user_id)
        first   = (u.first_name or "").strip() if u else ""
        last    = (u.last_name  or "").strip() if u else ""
        display = " ".join(filter(None, [first, last])) or (u.email if u else None)
        result.append({
            "user_id":      uw.user_id,
            "email":        u.email if u else None,
            "display_name": display,
            "role":         uw.role,
        })
    return jsonify(result)


@app.put("/auth/workspaces/<int:workspace_id>/members/<int:uid>")
@jwt_required()
def update_workspace_member(workspace_id, uid):
    _, err = _require_workspace_admin(workspace_id)
    if err:
        return err
    data     = request.get_json(silent=True) or {}
    new_role = (data.get("role") or "").strip().lower()
    if new_role not in ROLES:
        return jsonify(error=f"role must be one of {ROLES}"), 400
    uw = UserWorkspace.query.filter_by(user_id=uid, workspace_id=workspace_id).first()
    if not uw:
        return jsonify(error="Member not found"), 404
    uw.role = new_role
    db.session.commit()
    return jsonify({"user_id": uid, "workspace_id": workspace_id, "role": new_role})


@app.delete("/auth/workspaces/<int:workspace_id>/members/<int:uid>")
@jwt_required()
def remove_workspace_member(workspace_id, uid):
    _, err = _require_workspace_admin(workspace_id)
    if err:
        return err
    uw = UserWorkspace.query.filter_by(user_id=uid, workspace_id=workspace_id).first()
    if not uw:
        return jsonify(error="Member not found"), 404
    db.session.delete(uw)
    db.session.commit()
    return "", 204


@app.get("/auth/workspaces/<int:workspace_id>/requests")
@jwt_required()
def list_invite_requests(workspace_id):
    _, err = _require_workspace_admin(workspace_id)
    if err:
        return err
    requests = WorkspaceInviteRequest.query.filter_by(
        workspace_id=workspace_id, status="pending"
    ).order_by(WorkspaceInviteRequest.created_at).all()
    return jsonify([r.to_dict() for r in requests])


@app.put("/auth/workspaces/<int:workspace_id>")
@jwt_required()
def update_workspace(workspace_id):
    _, err = _require_workspace_admin(workspace_id)
    if err:
        return err
    workspace = db.session.get(Workspace, workspace_id)
    if not workspace:
        return jsonify(error="Workspace not found"), 404
    data = request.get_json(silent=True) or {}
    name = (data.get("name") or "").strip()
    if not name:
        return jsonify(error="name is required"), 400
    workspace.name = name
    db.session.commit()
    return jsonify(workspace.to_dict())


@app.post("/auth/workspaces/<int:workspace_id>/regenerate-invite")
@jwt_required()
def regenerate_invite(workspace_id):
    _, err = _require_workspace_admin(workspace_id)
    if err:
        return err
    workspace = db.session.get(Workspace, workspace_id)
    if not workspace:
        return jsonify(error="Workspace not found"), 404
    workspace.invite_code = secrets.token_hex(4)
    db.session.commit()
    return jsonify(workspace.to_dict())


@app.put("/auth/workspaces/<int:workspace_id>/requests/<int:request_id>")
@jwt_required()
def resolve_invite_request(workspace_id, request_id):
    _, err = _require_workspace_admin(workspace_id)
    if err:
        return err
    req = WorkspaceInviteRequest.query.filter_by(
        id=request_id, workspace_id=workspace_id
    ).first()
    if not req:
        return jsonify(error="Request not found"), 404

    data       = request.get_json(silent=True) or {}
    new_status = (data.get("status") or "").strip().lower()
    if new_status not in ("approved", "rejected"):
        return jsonify(error="status must be 'approved' or 'rejected'"), 400

    req.status = new_status
    if new_status == "approved":
        already = UserWorkspace.query.filter_by(
            user_id=req.user_id, workspace_id=workspace_id
        ).first()
        if not already:
            db.session.add(UserWorkspace(user_id=req.user_id,
                                         workspace_id=workspace_id, role="viewer"))
    db.session.commit()
    return jsonify(req.to_dict())


# ── Workspace Location endpoints ──────────────────────────────────────────────

@app.get("/auth/workspaces/<int:workspace_id>/locations")
@jwt_required()
def list_workspace_locations(workspace_id):
    user = _current_user()
    if not user:
        return jsonify(error="Unauthorized"), 401
    uw = UserWorkspace.query.filter_by(user_id=user.id, workspace_id=workspace_id).first()
    if not uw:
        return jsonify(error="Not a member of this workspace"), 403
    locs = WorkspaceLocation.query.filter_by(workspace_id=workspace_id).order_by(WorkspaceLocation.name).all()
    return jsonify([l.to_dict() for l in locs])


@app.post("/auth/workspaces/<int:workspace_id>/locations")
@jwt_required()
def create_workspace_location(workspace_id):
    _, err = _require_workspace_role(workspace_id, "admin", "manager")
    if err:
        return err
    data = request.get_json(silent=True) or {}
    name = (data.get("name") or "").strip()
    if not name:
        return jsonify(error="name is required"), 400
    existing = WorkspaceLocation.query.filter_by(name=name, workspace_id=workspace_id).first()
    if existing:
        return jsonify(existing.to_dict()), 200
    loc = WorkspaceLocation(name=name, workspace_id=workspace_id)
    db.session.add(loc)
    db.session.commit()
    return jsonify(loc.to_dict()), 201


@app.delete("/auth/workspaces/<int:workspace_id>/locations/<int:loc_id>")
@jwt_required()
def delete_workspace_location(workspace_id, loc_id):
    _, err = _require_workspace_role(workspace_id, "admin")
    if err:
        return err
    loc = WorkspaceLocation.query.filter_by(id=loc_id, workspace_id=workspace_id).first()
    if not loc:
        return jsonify(error="Location not found"), 404
    db.session.delete(loc)
    db.session.commit()
    return "", 204


# ── Startup ───────────────────────────────────────────────────────────────────

with app.app_context():
    for _attempt in range(12):
        try:
            db.create_all()
            _run_migrations()
            break
        except Exception as _exc:
            print(f"[db] attempt {_attempt + 1}/12 failed: {_exc}", flush=True)
            time.sleep(5)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080)
