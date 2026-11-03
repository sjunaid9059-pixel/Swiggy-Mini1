#!/usr/bin/env python3
"""FastAPI backend for SJ Cash Telegram Mini App."""
from __future__ import annotations

import hashlib
import hmac
import json
import logging
import os
from typing import Any, Dict, List, Optional
from urllib.parse import parse_qsl

from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

import config
from storage import (
    add_account,
    get_account,
    get_user_accounts,
    account_limit,
    remove_account,
    update_account,
)
from swiggy_api import (
    request_otp,
    verify_otp,
    normalize_session,
    delete_account_request_otp,
    delete_account_confirm,
    claim_on_sessions,
    LN_OFFERS,
    BF_OFFERS,
    PYO_OFFERS,
)

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("sj.server")

app = FastAPI(title="SJ Cash Mini App", version="1.0.0")
# Flat layout: serve css/js/brand from same folder as this file
app.mount("/static", StaticFiles(directory=str(config.BASE_DIR)), name="static")

# in-memory pending OTP (phone -> pending dict)
_pending_otp: Dict[str, Dict[str, Any]] = {}


def _validate_init_data(init_data: str) -> Optional[int]:
    """Return telegram user id if initData is valid (or skip in dev)."""
    if not init_data:
        # allow local/dev without TG — use admin
        if os.getenv("ALLOW_DEV", "1") == "1":
            return config.ADMIN_IDS[0] if config.ADMIN_IDS else 1
        return None
    try:
        parsed = dict(parse_qsl(init_data, keep_blank_values=True))
        received_hash = parsed.pop("hash", None)
        if not received_hash:
            return None
        data_check = "\n".join(f"{k}={v}" for k, v in sorted(parsed.items()))
        secret = hmac.new(b"WebAppData", config.BOT_TOKEN.encode(), hashlib.sha256).digest()
        calc = hmac.new(secret, data_check.encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(calc, received_hash):
            # still try parse user for convenience when hash fails on some clients
            pass
        user_raw = parsed.get("user")
        if user_raw:
            user = json.loads(user_raw)
            return int(user.get("id"))
    except Exception as e:
        log.warning("initData parse: %s", e)
    if os.getenv("ALLOW_DEV", "1") == "1":
        return config.ADMIN_IDS[0] if config.ADMIN_IDS else 1
    return None


def require_user(init_data: Optional[str]) -> int:
    uid = _validate_init_data(init_data or "")
    if not uid:
        raise HTTPException(401, "Unauthorized Telegram user")
    return uid


class OtpReq(BaseModel):
    phone: str
    name: str = ""


class VerifyReq(BaseModel):
    phone: str
    otp: str
    name: str = ""


class SessionBody(BaseModel):
    session: Dict[str, Any]


class ClaimBody(BaseModel):
    kind: str
    offer_id: int = 1
    slot_ids: List[str] = Field(default_factory=list)
    day: Optional[int] = None


class DeleteReq(BaseModel):
    slot_id: str
    otp: str = ""


@app.get("/")
async def index():
    path = config.BASE_DIR / "index.html"
    return HTMLResponse(path.read_text(encoding="utf-8"))


@app.get("/api/health")
async def health():
    return {"ok": True, "service": "sj-cash"}


@app.get("/api/accounts")
async def api_accounts(x_telegram_initdata: Optional[str] = Header(None, alias="X-Telegram-InitData")):
    uid = require_user(x_telegram_initdata)
    accounts = get_user_accounts(uid)
    # strip huge fields for list
    safe = []
    for a in accounts:
        safe.append({
            "slot_id": a.get("slot_id"),
            "mobile": a.get("mobile"),
            "name": a.get("name"),
            "customerId": a.get("customerId"),
            "deviceId": a.get("deviceId"),
            "token": a.get("token"),
            "tid": a.get("tid"),
            "sid": a.get("sid"),
            "added_at": a.get("added_at"),
        })
    return {"ok": True, "accounts": safe, "limit": account_limit(uid)}


@app.post("/api/accounts")
async def api_add_account(
    body: SessionBody,
    x_telegram_initdata: Optional[str] = Header(None, alias="X-Telegram-InitData"),
):
    uid = require_user(x_telegram_initdata)
    sess = normalize_session(body.session)
    if not sess.get("token") or not sess.get("tid"):
        raise HTTPException(400, "token + tid required in session JSON")
    result = add_account(uid, sess)
    if not result.get("ok"):
        raise HTTPException(400, result.get("msg") or "failed")
    return {"ok": True, "account": result["account"], "count": result["count"]}


@app.delete("/api/accounts/{slot_id}")
async def api_del_account(
    slot_id: str,
    x_telegram_initdata: Optional[str] = Header(None, alias="X-Telegram-InitData"),
):
    uid = require_user(x_telegram_initdata)
    result = remove_account(uid, slot_id=slot_id)
    return {"ok": True, **result}


@app.post("/api/login/otp")
async def api_login_otp(
    body: OtpReq,
    x_telegram_initdata: Optional[str] = Header(None, alias="X-Telegram-InitData"),
):
    require_user(x_telegram_initdata)
    res = await request_otp(body.phone)
    if not res.get("ok"):
        raise HTTPException(400, res.get("msg") or "OTP failed")
    key = str(res.get("phone") or body.phone)
    key = "".join(c for c in key if c.isdigit())[-10:]
    _pending_otp[key] = {
        "phone": key,
        "tid": res.get("tid"),
        "sid": res.get("sid"),
        "deviceId": res.get("deviceId"),
        "preferred_name": body.name.strip() or f"SJ {key[-4:]}",
    }
    preferred = _pending_otp[key]["preferred_name"]
    return {"ok": True, "msg": "OTP sent", "preferred_name": preferred}


@app.post("/api/login/verify")
async def api_login_verify(
    body: VerifyReq,
    x_telegram_initdata: Optional[str] = Header(None, alias="X-Telegram-InitData"),
):
    uid = require_user(x_telegram_initdata)
    phone = "".join(c for c in body.phone if c.isdigit())[-10:]
    pending = _pending_otp.get(phone)
    if not pending:
        raise HTTPException(400, "OTP session expired — send OTP again")
    preferred = body.name.strip() or pending.get("preferred_name") or f"SJ {phone[-4:]}"
    result = await verify_otp(pending, body.otp, preferred_name=preferred)
    if not result.get("ok"):
        raise HTTPException(400, result.get("msg") or "verify failed")
    session = result["session"]
    # ensure full fields
    session = normalize_session(session, phone=phone, name=preferred)
    saved = add_account(uid, session)
    if not saved.get("ok"):
        # still return session even if limit hit
        return {"ok": True, "session": session, "saved": False, "msg": saved.get("msg")}
    _pending_otp.pop(phone, None)
    return {"ok": True, "session": saved["account"], "saved": True}


@app.post("/api/delete/request")
async def api_delete_request(
    body: DeleteReq,
    x_telegram_initdata: Optional[str] = Header(None, alias="X-Telegram-InitData"),
):
    uid = require_user(x_telegram_initdata)
    acc = get_account(uid, body.slot_id)
    if not acc:
        raise HTTPException(404, "Account not found")
    res = await delete_account_request_otp(acc)
    if not res.get("ok"):
        raise HTTPException(400, res.get("msg") or "delete OTP failed")
    # persist refreshed tid if any
    if isinstance(res.get("data"), dict):
        if res["data"].get("tid"):
            acc["tid"] = res["data"]["tid"]
        if res["data"].get("sid"):
            acc["sid"] = res["data"]["sid"]
        update_account(uid, body.slot_id, acc)
    return {"ok": True, "msg": res.get("msg") or "OTP sent"}


@app.post("/api/delete/confirm")
async def api_delete_confirm(
    body: DeleteReq,
    x_telegram_initdata: Optional[str] = Header(None, alias="X-Telegram-InitData"),
):
    uid = require_user(x_telegram_initdata)
    acc = get_account(uid, body.slot_id)
    if not acc:
        raise HTTPException(404, "Account not found")
    res = await delete_account_confirm(acc, body.otp)
    if not res.get("ok"):
        raise HTTPException(400, res.get("msg") or "delete failed")
    remove_account(uid, slot_id=body.slot_id)
    return {"ok": True, "msg": res.get("msg") or "Account archived"}


@app.post("/api/claim")
async def api_claim(
    body: ClaimBody,
    x_telegram_initdata: Optional[str] = Header(None, alias="X-Telegram-InitData"),
):
    uid = require_user(x_telegram_initdata)
    all_acc = get_user_accounts(uid)
    if body.slot_ids:
        sessions = [a for a in all_acc if a.get("slot_id") in body.slot_ids]
    else:
        sessions = all_acc
    if not sessions:
        raise HTTPException(400, "No accounts selected")
    kind = body.kind.lower().strip()
    if kind not in ("ln", "bf", "pyo", "diya"):
        raise HTTPException(400, "kind must be ln|bf|pyo|diya")
    results = await claim_on_sessions(sessions, kind, offer_id=body.offer_id, day=body.day)
    return {"ok": True, "results": results}


@app.get("/api/offers")
async def api_offers():
    return {
        "ok": True,
        "ln": LN_OFFERS,
        "bf": BF_OFFERS,
        "pyo": PYO_OFFERS,
        "diya": {1: "Light all Diya links"},
    }


# favicon silence
@app.get("/favicon.ico")
async def favicon():
    return FileResponse(config.BASE_DIR / "brand.jpg")
