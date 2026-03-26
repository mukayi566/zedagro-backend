"""
ZEDAGRO Support Chat Module
────────────────────────────
• SQLite-backed (reuses the existing zedagro.db via SQLAlchemy)
• Socket.io WebSocket server mounted on FastAPI
• Role-based permission enforcement on every message
• SMS fallback placeholder via Africa's Talking stub
• Redis is optional — falls back to in-memory state if Redis is not running
"""

from __future__ import annotations

import datetime
import uuid
import asyncio
from typing import Dict, List, Optional, Set

import jwt
import socketio
from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel
from sqlalchemy import Column, String, DateTime, Text, Boolean, Enum as SAEnum
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker, DeclarativeBase
from sqlalchemy.pool import StaticPool

# ─── Re-use the shared engine from database.py ───────────────────────────────
from database import Base, engine, get_db
import models as app_models
import integrations

# ─── Optional Redis ───────────────────────────────────────────────────────────
try:
    import redis as _redis_lib
    _r = _redis_lib.Redis(host="localhost", port=6379, db=0, socket_connect_timeout=1)
    _r.ping()
    REDIS_AVAILABLE = True
    print("[Chat] Redis connected.")
except Exception:
    _r = None
    REDIS_AVAILABLE = False
    print("[Chat] Redis not available — using in-memory presence store.")

# ─── JWT secret (mirrors the main app; keep in sync) ─────────────────────────
JWT_SECRET = "zedagro-secret-key"
JWT_ALGORITHM = "HS256"

# ─── In-memory fallback presence stores ──────────────────────────────────────
_online_users: Dict[str, str] = {}   # user_id → status
_unread_counts: Dict[str, int] = {}  # user_id → count
_sid_to_user: Dict[str, str] = {}    # socket_id → user_id
_user_to_sid: Dict[str, str] = {}    # user_id → socket_id

# ═══════════════════════════════════════════════════════════════════════════════
#  DATABASE MODEL
# ═══════════════════════════════════════════════════════════════════════════════

class ChatMessage(Base):
    __tablename__ = "chat_messages"

    id            = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    sender_id     = Column(String, index=True, nullable=False)
    recipient_id  = Column(String, index=True, nullable=False)
    sender_role   = Column(String, nullable=False)
    recipient_role= Column(String, nullable=True)
    content       = Column(Text, nullable=False)
    message_type  = Column(String, default="text")   # text | system | broadcast
    read_at       = Column(DateTime, nullable=True)
    created_at    = Column(DateTime, default=datetime.datetime.utcnow)
    trip_id       = Column(String, nullable=True)
    region        = Column(String, nullable=True)
    is_deleted    = Column(Boolean, default=False)

# Create the table if it doesn't exist yet
Base.metadata.create_all(bind=engine)

# ═══════════════════════════════════════════════════════════════════════════════
#  PERMISSION ENGINE
# ═══════════════════════════════════════════════════════════════════════════════

def get_user_by_id(db: Session, user_id: str) -> Optional[Dict]:
    """Return a lightweight user dict from the users table."""
    try:
        row = db.execute(
            db.bind.execute.__class__,  # type: ignore
        )
    except Exception:
        pass
    # We query the raw table because we don't have a User ORM model in models.py
    result = db.execute(
        __import__("sqlalchemy").text("SELECT id, role, first_name, last_name, phone, region FROM users WHERE id = :uid"),
        {"uid": user_id}
    ).fetchone()
    if result:
        return dict(result._mapping)
    return None


ROLE_PERMISSIONS: Dict[str, List[str]] = {
    "admin":         ["admin", "field_agent", "driver", "depot_officer"],
    "field_agent":   ["admin"],
    "driver":        ["admin"],
    "depot_officer": ["admin"],
}


def can_message(sender_role: str, recipient_role: str) -> bool:
    """Base role-level permission check."""
    return recipient_role in ROLE_PERMISSIONS.get(sender_role, [])


def build_permitted_contacts(sender_id: str, sender_role: str, db: Session) -> List[str]:
    """
    Return list of user_ids this sender is currently allowed to message.
    For non-admin roles this is constrained beyond the role grid.
    """
    if sender_role == "admin":
        # Admin sees everyone
        rows = db.execute(
            __import__("sqlalchemy").text(
                "SELECT id FROM users WHERE id != :sid"
            ),
            {"sid": sender_id}
        ).fetchall()
        return [r[0] for r in rows]

    if sender_role == "field_agent":
        # Can message Admin + their assigned Driver(s)
        admin_ids = db.execute(
            __import__("sqlalchemy").text("SELECT id FROM users WHERE role='admin'")
        ).fetchall()
        # Find drivers assigned to farmer trips where this agent is the fieldAgentId
        driver_ids = db.execute(
            __import__("sqlalchemy").text(
                "SELECT DISTINCT driverId FROM logistics_trips WHERE fieldAgentId=:aid AND driverId IS NOT NULL"
            ),
            {"aid": sender_id}
        ).fetchall()
        return [r[0] for r in admin_ids] + [r[0] for r in driver_ids]

    if sender_role == "driver":
        # Can message Admin + their destination Depot Officer
        admin_ids = db.execute(
            __import__("sqlalchemy").text("SELECT id FROM users WHERE role='admin'")
        ).fetchall()
        # Find depot officers for depots this driver is heading to
        depot_officer_ids = db.execute(
            __import__("sqlalchemy").text(
                """SELECT DISTINCT u.id FROM users u
                   JOIN logistics_trips lt ON lt.destination LIKE '%' || u.depot_name || '%'
                   WHERE lt.driverId=:did AND u.role='depot_officer'"""
            ),
            {"did": sender_id}
        ).fetchall()
        return [r[0] for r in admin_ids] + [r[0] for r in depot_officer_ids]

    if sender_role == "depot_officer":
        # Can message Admin + incoming drivers
        admin_ids = db.execute(
            __import__("sqlalchemy").text("SELECT id FROM users WHERE role='admin'")
        ).fetchall()
        incoming_driver_ids = db.execute(
            __import__("sqlalchemy").text(
                """SELECT DISTINCT u.id FROM users u
                   JOIN logistics_trips lt ON lt.driverId = u.id
                   WHERE u.role='driver' AND lt.status IN ('in_transit','assigned','loading')"""
            )
        ).fetchall()
        return [r[0] for r in admin_ids] + [r[0] for r in incoming_driver_ids]

    return []


# ═══════════════════════════════════════════════════════════════════════════════
#  PRESENCE HELPERS
# ═══════════════════════════════════════════════════════════════════════════════

def set_user_online(user_id: str, status_val: str = "online"):
    if REDIS_AVAILABLE and _r:
        _r.setex(f"chat:online:{user_id}", 65, status_val)
    else:
        _online_users[user_id] = status_val


def set_user_offline(user_id: str):
    if REDIS_AVAILABLE and _r:
        _r.delete(f"chat:online:{user_id}")
    else:
        _online_users.pop(user_id, None)


def get_user_status(user_id: str) -> str:
    if REDIS_AVAILABLE and _r:
        val = _r.get(f"chat:online:{user_id}")
        return val.decode() if val else "offline"
    return _online_users.get(user_id, "offline")


def increment_unread(user_id: str):
    if REDIS_AVAILABLE and _r:
        _r.incr(f"chat:unread:{user_id}")
    else:
        _unread_counts[user_id] = _unread_counts.get(user_id, 0) + 1


def clear_unread(user_id: str):
    if REDIS_AVAILABLE and _r:
        _r.delete(f"chat:unread:{user_id}")
    else:
        _unread_counts.pop(user_id, None)


def get_unread(user_id: str) -> int:
    if REDIS_AVAILABLE and _r:
        val = _r.get(f"chat:unread:{user_id}")
        return int(val) if val else 0
    return _unread_counts.get(user_id, 0)


# ═══════════════════════════════════════════════════════════════════════════════
#  SMS FALLBACK (Africa's Talking stub)
# ═══════════════════════════════════════════════════════════════════════════════

async def send_sms_fallback(phone: str, sender_name: str):
    """Africa's Talking SMS fallback for offline users."""
    message = f"ZEDAGRO: New message from {sender_name}. Open the app to reply."
    # Use the shared integration module
    integrations.ExternalIntegrations.send_sms_africastalking(phone, message)


# ═══════════════════════════════════════════════════════════════════════════════
#  PYDANTIC SCHEMAS
# ═══════════════════════════════════════════════════════════════════════════════

class SendMessagePayload(BaseModel):
    recipient_id: str
    content: str
    message_type: str = "text"


class BroadcastPayload(BaseModel):
    region: str
    content: str


class ReadPayload(BaseModel):
    conversation_id: str   # "sender_id:recipient_id" canonical form


# ═══════════════════════════════════════════════════════════════════════════════
#  FASTAPI ROUTER
# ═══════════════════════════════════════════════════════════════════════════════

router = APIRouter(prefix="/v1/chat", tags=["support-chat"])


def decode_token(request: Request) -> dict:
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing token")
    token = auth[7:]
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        return payload
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")


def get_session() -> Session:
    from database import SessionLocal
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def conversation_id(a: str, b: str) -> str:
    """Canonical conversation id — order-independent."""
    return ":".join(sorted([a, b]))


@router.post("/message")
def send_message(payload: SendMessagePayload, request: Request, db: Session = Depends(get_session)):
    claims = decode_token(request)
    sender_id = str(claims.get("sub") or claims.get("user_id"))
    sender_role = claims.get("role", "")

    # Server-side permission check
    permitted = build_permitted_contacts(sender_id, sender_role, db)
    if payload.recipient_id not in permitted:
        raise HTTPException(status_code=403, detail="You are not permitted to message this user.")

    # Recipient role
    recipient = get_user_by_id(db, payload.recipient_id)
    recipient_role = recipient["role"] if recipient else ""

    msg = ChatMessage(
        sender_id=sender_id,
        recipient_id=payload.recipient_id,
        sender_role=sender_role,
        recipient_role=recipient_role,
        content=payload.content,
        message_type=payload.message_type,
    )
    db.add(msg)
    db.commit()
    db.refresh(msg)

    delivered = False
    recipient_sid = _user_to_sid.get(payload.recipient_id)
    if recipient_sid:
        delivered = True
        # Emit via Socket.io (called from async context in real usage)
    else:
        # SMS fallback
        if recipient and recipient.get("phone"):
            sender_info = get_user_by_id(db, sender_id)
            sender_name = f"{sender_info.get('first_name','')} {sender_info.get('last_name','')}".strip() if sender_info else "ZEDAGRO"
            asyncio.create_task(send_sms_fallback(recipient["phone"], sender_name))
        increment_unread(payload.recipient_id)

    return {
        "message_id": msg.id,
        "timestamp": msg.created_at.isoformat(),
        "delivered": delivered
    }


@router.get("/conversations/{user_id}")
def get_conversations(user_id: str, request: Request, db: Session = Depends(get_session)):
    decode_token(request)
    import sqlalchemy as sa

    rows = db.execute(
        sa.text("""
            SELECT * FROM chat_messages
            WHERE (sender_id = :uid OR recipient_id = :uid)
              AND is_deleted = 0
            ORDER BY created_at DESC
        """),
        {"uid": user_id}
    ).fetchall()

    convs: Dict[str, dict] = {}
    for row in rows:
        r = dict(row._mapping)
        other = r["recipient_id"] if r["sender_id"] == user_id else r["sender_id"]
        cid = conversation_id(user_id, other)
        if cid not in convs:
            convs[cid] = {
                "conversation_id": cid,
                "other_user_id": other,
                "last_message": r["content"][:35],
                "last_timestamp": r["created_at"],
                "unread_count": 0,
                "status": get_user_status(other),
            }

    return list(convs.values())


@router.get("/messages/{conversation_id}")
def get_messages(conversation_id: str, request: Request, page: int = 1, limit: int = 50, db: Session = Depends(get_session)):
    decode_token(request)
    parts = conversation_id.split(":")
    if len(parts) != 2:
        raise HTTPException(status_code=400, detail="Invalid conversation_id")
    uid_a, uid_b = parts
    import sqlalchemy as sa
    offset = (page - 1) * limit
    rows = db.execute(
        sa.text("""
            SELECT * FROM chat_messages
            WHERE ((sender_id=:a AND recipient_id=:b) OR (sender_id=:b AND recipient_id=:a))
              AND is_deleted=0
            ORDER BY created_at DESC
            LIMIT :lim OFFSET :off
        """),
        {"a": uid_a, "b": uid_b, "lim": limit, "off": offset}
    ).fetchall()
    return [dict(r._mapping) for r in rows]


@router.post("/broadcast")
def broadcast(payload: BroadcastPayload, request: Request, db: Session = Depends(get_session)):
    claims = decode_token(request)
    if claims.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin only.")
    sender_id = str(claims.get("sub") or claims.get("user_id"))

    import sqlalchemy as sa
    agents = db.execute(
        sa.text("SELECT id FROM users WHERE role='field_agent' AND region=:r"),
        {"r": payload.region}
    ).fetchall()
    agent_ids = [r[0] for r in agents]

    for agent_id in agent_ids:
        msg = ChatMessage(
            sender_id=sender_id,
            recipient_id=agent_id,
            sender_role="admin",
            recipient_role="field_agent",
            content=payload.content,
            message_type="broadcast",
            region=payload.region,
        )
        db.add(msg)

    db.commit()
    return {"sent_to": len(agent_ids), "agent_ids": agent_ids}


@router.patch("/read/{conv_id}")
def mark_read(conv_id: str, request: Request, db: Session = Depends(get_session)):
    claims = decode_token(request)
    user_id = str(claims.get("sub") or claims.get("user_id"))
    import sqlalchemy as sa
    now = datetime.datetime.utcnow()
    parts = conv_id.split(":")
    if len(parts) != 2:
        raise HTTPException(status_code=400, detail="Invalid conv_id")
    uid_a, uid_b = parts
    other = uid_b if uid_a == user_id else uid_a
    db.execute(
        sa.text("""
            UPDATE chat_messages SET read_at=:now
            WHERE sender_id=:other AND recipient_id=:me AND read_at IS NULL
        """),
        {"now": now, "other": other, "me": user_id}
    )
    db.commit()
    clear_unread(user_id)
    return {"ok": True}


@router.get("/context/{target_user_id}")
def get_context(target_user_id: str, request: Request, db: Session = Depends(get_session)):
    """Returns live context bar data for the given contact."""
    decode_token(request)
    import sqlalchemy as sa
    user = get_user_by_id(db, target_user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    role = user.get("role")
    if role == "driver":
        trip = db.execute(
            sa.text("SELECT * FROM logistics_trips WHERE driverId=:did AND status='in_transit' LIMIT 1"),
            {"did": target_user_id}
        ).fetchone()
        if trip:
            t = dict(trip._mapping)
            return {
                "role": "driver",
                "truck_plate": t.get("truckId"),
                "route": f"{t.get('origin')} → {t.get('destination')}",
                "progress": t.get("progress", 0),
                "eta": t.get("eta"),
                "produce": t.get("produce"),
                "weight": t.get("weight"),
            }
    elif role == "field_agent":
        farmers_count = db.execute(
            sa.text("SELECT COUNT(*) FROM farmers"),
        ).scalar()
        return {
            "role": "field_agent",
            "assigned_farmers": farmers_count,
            "completed_surveys_week": 5,
            "pending_surveys": 3,
            "field_status": get_user_status(target_user_id) or "available",
        }
    elif role == "depot_officer":
        depot = db.execute(
            sa.text("SELECT * FROM storage_depots LIMIT 1")
        ).fetchone()
        incoming = db.execute(
            sa.text("SELECT COUNT(*) FROM logistics_trips WHERE status IN ('in_transit','assigned')"),
        ).scalar()
        if depot:
            d = dict(depot._mapping)
            pct = round((d["used"] / d["capacity"]) * 100) if d["capacity"] else 0
            return {
                "role": "depot_officer",
                "depot_name": d["name"],
                "location": d["location"],
                "capacity_pct": pct,
                "trucks_incoming_today": incoming,
                "last_qr_scan": "2026-03-23T11:42:00Z",
            }
    return {"role": role}


@router.get("/contacts/{user_id}")
def get_contacts(user_id: str, request: Request, db: Session = Depends(get_session)):
    """Returns the contact list visible to this user."""
    decode_token(request)
    permitted_ids = build_permitted_contacts(user_id, "", db)
    import sqlalchemy as sa
    if not permitted_ids:
        return []
    placeholders = ",".join([f"'{i}'" for i in permitted_ids])
    rows = db.execute(
        sa.text(f"SELECT id, first_name, last_name, role, region, phone FROM users WHERE id IN ({placeholders})")
    ).fetchall()
    return [
        {**dict(r._mapping), "status": get_user_status(r[0])}
        for r in rows
    ]


# ═══════════════════════════════════════════════════════════════════════════════
#  SOCKET.IO SERVER
# ═══════════════════════════════════════════════════════════════════════════════

sio = socketio.AsyncServer(async_mode="asgi", cors_allowed_origins="*")


def _decode_ws_token(token: str) -> Optional[dict]:
    try:
        return jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
    except Exception:
        return None


@sio.event
async def connect(sid, environ, auth):
    token = (auth or {}).get("token", "")
    claims = _decode_ws_token(token)
    if not claims:
        raise socketio.exceptions.ConnectionRefusedError("Unauthorized")

    user_id = str(claims.get("sub") or claims.get("user_id"))
    role = claims.get("role", "")

    _sid_to_user[sid] = user_id
    _user_to_sid[user_id] = sid

    status_val = "driving" if role == "driver" else "online"
    set_user_online(user_id, status_val)

    await sio.emit("chat:status", {"userId": user_id, "status": status_val}, skip_sid=sid)
    print(f"[WS] {user_id} ({role}) connected as {sid}")


@sio.event
async def disconnect(sid):
    user_id = _sid_to_user.pop(sid, None)
    if user_id:
        _user_to_sid.pop(user_id, None)
        set_user_offline(user_id)
        await sio.emit("chat:status", {"userId": user_id, "status": "offline"})
        print(f"[WS] {user_id} disconnected")


@sio.event
async def connect_error(sid, data):
    print(f"[WS] Connection error: {data}")


@sio.on("chat:send")
async def on_chat_send(sid, data):
    """
    data: { to: str, content: str, type: 'text'|'system'|'broadcast' }
    Validated by JWT claims stored at connect time.
    """
    from database import SessionLocal
    db = SessionLocal()
    try:
        sender_id = _sid_to_user.get(sid)
        if not sender_id:
            return

        # Look up sender from DB
        import sqlalchemy as sa
        sender_row = db.execute(
            sa.text("SELECT id, role, first_name, last_name FROM users WHERE id=:uid"),
            {"uid": sender_id}
        ).fetchone()
        if not sender_row:
            return

        sender_role = sender_row[1]
        permitted = build_permitted_contacts(sender_id, sender_role, db)
        recipient_id = data.get("to")

        if recipient_id not in permitted:
            await sio.emit("chat:error", {"error": "Not permitted to message this user."}, to=sid)
            return

        # Persist
        msg = ChatMessage(
            sender_id=sender_id,
            recipient_id=recipient_id,
            sender_role=sender_role,
            content=data.get("content", ""),
            message_type=data.get("type", "text"),
        )
        db.add(msg)
        db.commit()
        db.refresh(msg)

        payload = {
            "id": msg.id,
            "from": sender_id,
            "content": msg.content,
            "type": msg.message_type,
            "timestamp": msg.created_at.strftime("%H:%M"),
            "created_at": msg.created_at.isoformat(),
        }

        # Deliver to recipient
        recipient_sid = _user_to_sid.get(recipient_id)
        if recipient_sid:
            await sio.emit("chat:receive", payload, to=recipient_sid)
        else:
            increment_unread(recipient_id)
            # SMS fallback
            recipient_row = db.execute(
                sa.text("SELECT phone FROM users WHERE id=:uid"), {"uid": recipient_id}
            ).fetchone()
            if recipient_row and recipient_row[0]:
                name = f"{sender_row[2] or ''} {sender_row[3] or ''}".strip()
                asyncio.create_task(send_sms_fallback(recipient_row[0], name))

        # Echo back to sender with message id
        await sio.emit("chat:sent", payload, to=sid)

    finally:
        db.close()


@sio.on("chat:heartbeat")
async def on_heartbeat(sid, data):
    user_id = _sid_to_user.get(sid)
    if user_id:
        current = get_user_status(user_id)
        if current == "offline":
            current = "online"
        set_user_online(user_id, current)


@sio.on("chat:typing")
async def on_typing(sid, data):
    sender_id = _sid_to_user.get(sid)
    recipient_id = data.get("to")
    if sender_id and recipient_id:
        recipient_sid = _user_to_sid.get(recipient_id)
        if recipient_sid:
            await sio.emit("chat:typing", {"from": sender_id}, to=recipient_sid)


# ASGI app wrapping Socket.io
socket_app = socketio.ASGIApp(sio)
