#!/usr/bin/env python3
"""Swiggy API helpers — login, delete, offers (LN / BF / PYO / Diya)."""
from __future__ import annotations

import asyncio
import base64
import json
import logging
import re
import secrets
import time
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional, Tuple

import aiohttp

log = logging.getLogger("sj.swiggy")

PROFILE_BASE_URL = "https://profile.swiggy.com"
SPNS_BASE_URL = "https://spns.swiggy.com"
NOTIFY_URL = "https://events.swiggy.com/api/notify"
EVENTS_BASE = "https://events.swiggy.com"

SWIGGY_APP_HEADERS = {
    "user-agent": "Swiggy-Android",
    "content-type": "application/json; charset=utf-8",
    "accept": "application/json; charset=utf-8",
    "version-code": "1795",
    "app-version": "4.113.0",
    "manufacturer": "MOTOROLA",
    "model-name": "MOTO G(60)",
}

CASHLOOT_CREATE_OFFERS_PATH = "/api/v1/proximity-offer/create-offers"
CASHLOOT_TRANSACTIONS_PATH = "/api/v1/proximity-offer/campaigns/{campaign_id}/transactions"
DEFAULT_CAMPAIGN_ID = "ydiHi75"

# ── Late Night ──────────────────────────────────────────────────────────────
LN_CAMPAIGN_PREFIX = "byo-ln-v6-"
LN_PAGE_URL = "https://events.swiggy.com/pick-your-late-night-offer"
LN_OFFERS = {
    1: "₹50 Free Cash (min ₹199)",
    2: "₹150 OFF Coupon (min ₹249)",
    3: "₹100 OFF Coupon (min ₹149)",
    4: "Offer 4",
}

# ── Breakfast ───────────────────────────────────────────────────────────────
BF_CAMPAIGN_PREFIX = "byo-bf-v11-"
BF_PAGE_URL = "https://events.swiggy.com/book-your-offer"
BF_OFFERS = {
    1: "₹50 FREE Cash (breakfast ≥ ₹199)",
    2: "₹150 OFF Coupon (breakfast ≥ ₹249)",
    3: "₹100 OFF + ₹50 Free Cash (≥ ₹249)",
    4: "₹100 OFF Coupon (breakfast ≥ ₹149)",
}

# ── Pick Your Offer ─────────────────────────────────────────────────────────
PYO_PAGE_URL = "https://events.swiggy.com/pick-your-offer"
PYO_CAMPAIGN_ID = "pyo-v1-2"
PYO_OFFERS = {
    1: "₹50 FREE Cash (min ₹199)",
    2: "₹150 OFF Coupon (min ₹249)",
    3: "₹130 OFF Coupon (min ₹199)",
    4: "₹100 OFF Coupon (min ₹149)",
}

# ── Light Diya ──────────────────────────────────────────────────────────────
DIYA_CAMPAIGN_ID = "aWPhpVsRkD"
DIYA_PER_LIGHT = 5
DIYA_MAX_CASH = 75
DIYA_DEFAULT_LINKS: List[str] = [
    "https://r.swiggy.com/light-diya/aWPhpVsRkD-hYhN1HkDmEv",
    "https://r.swiggy.com/light-diya/aWPhpVsRkD-hYhN1G1pmfp",
    "https://r.swiggy.com/light-diya/aWPhpVsRkD-hYhN1HmdCjh",
    "https://r.swiggy.com/light-diya/aWPhpVsRkD-hYhN1HmgWNR",
    "https://r.swiggy.com/light-diya/aWPhpVsRkD-hYhN1HpjYt0",
    "https://r.swiggy.com/light-diya/aWPhpVsRkD-hYhN1G15y9y",
    "https://r.swiggy.com/light-diya/aWPhpVsRkD-hYhN1G10maM",
    "https://r.swiggy.com/light-diya/aWPhpVsRkD-hYhN1HugYOn",
    "https://r.swiggy.com/light-diya/aWPhpVsRkD-hYhN1G2cDqs",
    "https://r.swiggy.com/light-diya/aWPhpVsRkD-hYhN1G12ucD",
    "https://r.swiggy.com/light-diya/aWPhpVsRkD-hYhN1G12Q04",
    "https://r.swiggy.com/light-diya/aWPhpVsRkD-hYhN1G1XXhN",
    "https://r.swiggy.com/light-diya/aWPhpVsRkD-hYhN1Hr2pN4",
    "https://r.swiggy.com/light-diya/aWPhpVsRkD-hYhN1HkUHGw",
    "https://r.swiggy.com/light-diya/aWPhpVsRkD-hYhN1G10maM",
]
_DIYA_URL_RE = re.compile(r"r\.swiggy\.com/light-diya/([A-Za-z0-9_-]+)", re.I)


# ─────────────────────────────────────────────────────────────────────────────
# Utils
# ─────────────────────────────────────────────────────────────────────────────

def _random_device_id() -> str:
    return secrets.token_hex(8)


def _decode_tid_payload(tid: str) -> Dict[str, Any]:
    try:
        parts = tid.split(".")
        if len(parts) < 2:
            return {}
        payload = parts[1]
        pad = "=" * (-len(payload) % 4)
        raw = base64.urlsafe_b64decode(payload + pad)
        return json.loads(raw.decode("utf-8", errors="ignore"))
    except Exception:
        return {}


def _userid_from_tid(tid: str) -> str:
    data = _decode_tid_payload(tid)
    uid = data.get("user_id") or data.get("userId") or data.get("sub") or ""
    return str(uid) if uid and str(uid) != "0" else ""


def _account_user_id(session: Dict) -> str:
    for k in ("customerId", "userid", "userId", "user_id"):
        v = session.get(k)
        if v and str(v) not in ("0", ""):
            return str(v)
    return _userid_from_tid(str(session.get("tid") or ""))


def build_headers(session: Dict) -> Dict[str, str]:
    return {
        "Content-Type": "application/json",
        "user-agent": SWIGGY_APP_HEADERS["user-agent"],
        "userAgent": SWIGGY_APP_HEADERS["user-agent"],
        "platform": "Swiggy-Android",
        "versionCode": SWIGGY_APP_HEADERS["version-code"],
        "tid": str(session.get("tid") or ""),
        "token": str(session.get("token") or ""),
        "userId": _account_user_id(session),
        "deviceid": str(session.get("deviceId") or ""),
        "swuid": str(session.get("deviceId") or ""),
        "sid": str(session.get("sid") or ""),
    }


def profile_headers(session: Dict) -> Dict[str, str]:
    h = dict(SWIGGY_APP_HEADERS)
    h.update({
        "tid": str(session.get("tid") or ""),
        "token": str(session.get("token") or ""),
        "sid": str(session.get("sid") or ""),
        "deviceid": str(session.get("deviceId") or ""),
        "swuid": str(session.get("deviceId") or ""),
        "deviceId": str(session.get("deviceId") or ""),
        "os-version": "12",
        "accessibility_enabled": "false",
        "pl-version": "138",
        "latitude": str(session.get("lat") or "28.5561437"),
        "longitude": str(session.get("lng") or "77.0999623"),
        "x-network-quality": "GOOD",
        "faw-flags": "1354",
        "cache-control": "no-store",
    })
    return h


def normalize_session(raw: Dict[str, Any], phone: str = "", name: str = "") -> Dict[str, Any]:
    """Always return complete JSON with no empty critical fields."""
    tid = str(raw.get("tid") or "")
    sid = str(raw.get("sid") or "")
    token = str(raw.get("token") or "")
    device = str(raw.get("deviceId") or raw.get("deviceid") or raw.get("swuid") or _random_device_id())
    payload = _decode_tid_payload(tid) if tid else {}
    if not sid:
        sid = str(payload.get("sid") or "")
    customer = (
        str(raw.get("customerId") or raw.get("userid") or raw.get("userId") or raw.get("user_id") or "")
        or str(payload.get("user_id") or payload.get("userId") or "")
    )
    mobile = str(raw.get("mobile") or raw.get("phone") or phone or "")
    display_name = str(raw.get("name") or name or f"SJ User {customer[-4:] if customer else 'X'}")
    out = {
        "mobile": mobile,
        "name": display_name,
        "token": token,
        "sid": sid,
        "tid": tid,
        "deviceId": device,
        "customerId": customer,
        "userid": customer,
        "lat": float(raw.get("lat") or 28.5561437),
        "lng": float(raw.get("lng") or 77.0999623),
        "saved_at": datetime.now(timezone.utc).isoformat(),
    }
    return out


# ─────────────────────────────────────────────────────────────────────────────
# Login / OTP
# ─────────────────────────────────────────────────────────────────────────────

async def request_otp(phone: str) -> Dict[str, Any]:
    phone = re.sub(r"\D", "", str(phone or ""))
    if phone.startswith("91") and len(phone) == 12:
        phone = phone[2:]
    if len(phone) != 10:
        return {"ok": False, "msg": "Invalid phone — 10 digit required"}
    device_id = _random_device_id()
    headers = dict(SWIGGY_APP_HEADERS)
    headers.update({
        "swuid": device_id, "deviceid": device_id, "deviceId": device_id,
        "accessibility_enabled": "false", "screen-name": "LOGIN",
        "os-version": "13", "requestId": secrets.token_hex(8),
    })
    endpoints = [
        (f"{PROFILE_BASE_URL}/api/v3/app/sms_otp", {"mobile": phone}),
        (f"{PROFILE_BASE_URL}/api/v1/user/sms-otp", {"mobile": phone, "countryCode": "91"}),
    ]
    last_msg = "OTP request failed"
    async with aiohttp.ClientSession(
        cookie_jar=aiohttp.CookieJar(unsafe=True),
        connector=aiohttp.TCPConnector(ssl=False),
    ) as http:
        for url, params in endpoints:
            try:
                async with http.get(url, params=params, headers=headers, timeout=aiohttp.ClientTimeout(total=18)) as resp:
                    try:
                        data = await resp.json(content_type=None)
                    except Exception:
                        data = {}
                    if resp.status == 200 and (
                        data.get("statusCode") in (0, "0", None) or data.get("tid") or data.get("data")
                    ):
                        inner = data.get("data") if isinstance(data.get("data"), dict) else data
                        tid = inner.get("tid") or data.get("tid")
                        sid = inner.get("sid") or data.get("sid")
                        device = str(inner.get("deviceId") or data.get("deviceId") or device_id)
                        if not sid and tid:
                            sid = _decode_tid_payload(str(tid)).get("sid") or ""
                        if tid:
                            return {
                                "ok": True, "tid": tid, "sid": sid,
                                "deviceId": device, "phone": phone,
                            }
                    last_msg = data.get("statusMessage") or data.get("message") or f"HTTP {resp.status}"
            except Exception as e:
                last_msg = str(e)
    return {"ok": False, "msg": last_msg}


async def verify_otp(pending: Dict, otp: str, preferred_name: str = "") -> Dict[str, Any]:
    otp = re.sub(r"\D", "", str(otp or ""))
    headers = dict(SWIGGY_APP_HEADERS)
    headers.update({
        "swuid": pending["deviceId"], "deviceid": pending["deviceId"], "deviceId": pending["deviceId"],
        "accessibility_enabled": "false", "screen-name": "LOGIN", "os-version": "13",
        "requestId": secrets.token_hex(8),
    })
    if pending.get("tid"):
        headers["tid"] = str(pending["tid"])
    if pending.get("sid"):
        headers["sid"] = str(pending["sid"])
    bodies = [
        {
            "cloningSignalsData": {
                "appFilesDirPathInvalid": 0, "developerModeEnabled": 0,
                "deviceModelVmos": 0, "emulatorStatus": 0,
                "packageName": "in.swiggy.android", "workProfileEnabled": 0,
            },
            "otp": otp,
        },
        {"otp": otp, "otp_source": "Sms-manual"},
    ]
    urls = [
        (f"{PROFILE_BASE_URL}/api/v3/app/login/verify", {"otp_source": "Sms-manual"}),
        (f"{PROFILE_BASE_URL}/api/v1/user/login/otp-verify", {}),
    ]
    last_msg = "OTP verify failed"
    async with aiohttp.ClientSession(
        cookie_jar=aiohttp.CookieJar(unsafe=True),
        connector=aiohttp.TCPConnector(ssl=False),
    ) as http:
        for url, params in urls:
            for body in bodies:
                try:
                    async with http.post(
                        url, params=params or None, json=body,
                        headers=headers, timeout=aiohttp.ClientTimeout(total=18),
                    ) as resp:
                        try:
                            data = await resp.json(content_type=None)
                        except Exception:
                            data = {}
                        inner = data.get("data") if isinstance(data.get("data"), dict) else {}
                        has_token = bool(
                            inner.get("token") or data.get("token") or inner.get("tid") or data.get("tid")
                        )
                        status_ok = resp.status == 200 and data.get("statusCode") in (0, "0", None)
                        if not (status_ok or (resp.status == 200 and has_token)):
                            last_msg = data.get("statusMessage") or data.get("message") or f"HTTP {resp.status}"
                            continue
                        session: Dict[str, Any] = {}
                        for key in ("token", "tid", "sid"):
                            if inner.get(key):
                                session[key] = inner[key]
                            elif data.get(key):
                                session[key] = data[key]
                        try:
                            for c in http.cookie_jar:
                                n = (getattr(c, "key", None) or getattr(c, "name", "") or "").lower()
                                if n in ("token", "tid", "sid") and n not in session:
                                    session[n] = c.value
                        except Exception:
                            pass
                        session["deviceId"] = str(
                            data.get("deviceId") or inner.get("deviceId") or pending["deviceId"]
                        )
                        user_id = _userid_from_tid(str(session.get("tid") or ""))
                        if not user_id or user_id == "0":
                            user_id = str(inner.get("customerId") or inner.get("userId") or data.get("customerId") or "")
                        session["customerId"] = user_id
                        session["userid"] = user_id
                        session["mobile"] = pending.get("phone") or ""
                        session["name"] = preferred_name or f"SJ {user_id[-4:] if user_id else 'User'}"
                        # Enrich profile if possible
                        session = await enrich_profile(session, http)
                        full = normalize_session(session, phone=session.get("mobile", ""), name=session.get("name", ""))
                        return {"ok": True, "session": full}
                except Exception as e:
                    last_msg = str(e)
                    continue
    return {"ok": False, "msg": last_msg}


async def enrich_profile(session: Dict, http: Optional[aiohttp.ClientSession] = None) -> Dict:
    """Fill missing customerId / name from profile APIs."""
    owns = http is None
    if owns:
        http = aiohttp.ClientSession(
            cookie_jar=aiohttp.CookieJar(unsafe=True),
            connector=aiohttp.TCPConnector(ssl=False),
        )
    try:
        h = profile_headers(session)
        for path in ("/api/v1/user", "/api/v1/user/profile", "/api/v2/user"):
            try:
                async with http.get(
                    PROFILE_BASE_URL + path, headers=h, timeout=aiohttp.ClientTimeout(total=12)
                ) as resp:
                    if resp.status != 200:
                        continue
                    data = await resp.json(content_type=None)
                    inner = data.get("data") if isinstance(data.get("data"), dict) else data
                    if not isinstance(inner, dict):
                        continue
                    for k_src, k_dst in (
                        ("customerId", "customerId"), ("id", "customerId"),
                        ("userId", "customerId"), ("user_id", "customerId"),
                        ("name", "name"), ("userName", "name"), ("fullName", "name"),
                        ("mobile", "mobile"), ("phoneNumber", "mobile"),
                    ):
                        if inner.get(k_src) and not session.get(k_dst):
                            session[k_dst] = str(inner[k_src])
                    if session.get("customerId"):
                        break
            except Exception:
                continue
    finally:
        if owns and http:
            await http.close()
    if not session.get("customerId"):
        session["customerId"] = _userid_from_tid(str(session.get("tid") or ""))
    if not session.get("name"):
        cid = session.get("customerId") or "X"
        session["name"] = f"SJ {str(cid)[-4:]}"
    return session


# ─────────────────────────────────────────────────────────────────────────────
# Account delete + recreate
# ─────────────────────────────────────────────────────────────────────────────

async def delete_account_request_otp(session: Dict) -> Dict[str, Any]:
    """GET /api/v1/delete/user_check → Archive OTP Sent."""
    h = profile_headers(session)
    try:
        async with aiohttp.ClientSession(connector=aiohttp.TCPConnector(ssl=False)) as http:
            async with http.get(
                f"{PROFILE_BASE_URL}/api/v1/delete/user_check",
                headers=h,
                timeout=aiohttp.ClientTimeout(total=20),
            ) as resp:
                data = await resp.json(content_type=None)
                ok = resp.status == 200 and (
                    data.get("statusCode") in (28, "28", 0, "0")
                    or "otp" in str(data.get("statusMessage", "")).lower()
                )
                # refresh tid/sid if returned
                if data.get("tid"):
                    session["tid"] = data["tid"]
                if data.get("sid"):
                    session["sid"] = data["sid"]
                return {"ok": ok, "data": data, "msg": data.get("statusMessage") or ""}
    except Exception as e:
        return {"ok": False, "msg": str(e)}


async def delete_account_confirm(session: Dict, otp: str) -> Dict[str, Any]:
    """POST /api/v1/delete/user with otp."""
    h = profile_headers(session)
    try:
        async with aiohttp.ClientSession(connector=aiohttp.TCPConnector(ssl=False)) as http:
            async with http.post(
                f"{PROFILE_BASE_URL}/api/v1/delete/user",
                headers=h,
                json={"otp": str(otp).strip()},
                timeout=aiohttp.ClientTimeout(total=20),
            ) as resp:
                data = await resp.json(content_type=None)
                ok = resp.status == 200 and (
                    data.get("statusCode") in (33, "33", 0, "0")
                    or "archiv" in str(data.get("statusMessage", "")).lower()
                    or "success" in str(data.get("statusMessage", "")).lower()
                )
                return {"ok": ok, "data": data, "msg": data.get("statusMessage") or ""}
    except Exception as e:
        return {"ok": False, "msg": str(e)}


async def recreate_account(phone: str, preferred_name: str = "SJ User") -> Dict[str, Any]:
    """After delete: request OTP → user verifies → full session JSON returned."""
    otp_res = await request_otp(phone)
    if not otp_res.get("ok"):
        return otp_res
    return {
        "ok": True,
        "pending": otp_res,
        "msg": "OTP sent. Verify to create new account.",
        "preferred_name": preferred_name or f"SJ {phone[-4:]}",
    }


# ─────────────────────────────────────────────────────────────────────────────
# Offers — Late Night / Breakfast / PYO
# ─────────────────────────────────────────────────────────────────────────────

def _current_ln_day() -> int:
    now = datetime.now(timezone(timedelta(hours=5, minutes=30)))
    # simple day index from Nov 1 2026
    base = datetime(2026, 11, 1, 11, 0, tzinfo=timezone(timedelta(hours=5, minutes=30)))
    if now < base:
        return 1
    delta = (now - base).days + 1
    return max(1, min(30, delta))


def _current_bf_day() -> int:
    return _current_ln_day()


async def ln_claim_offer(session: Dict, day: int, offer_id: int) -> Dict[str, Any]:
    campaign = f"{LN_CAMPAIGN_PREFIX}{day}"
    headers = {
        "Content-Type": "application/json",
        "token": str(session.get("token") or ""),
        "tid": str(session.get("tid") or ""),
        "User-Agent": "Mozilla/5.0 (Linux; Android 13) AppleWebKit/537.36 Chrome/120.0.0.0 Mobile Safari/537.36",
        "Origin": "https://events.swiggy.com",
        "Referer": LN_PAGE_URL,
    }
    body = {"campaign": campaign, "value": offer_id}
    try:
        async with aiohttp.ClientSession(connector=aiohttp.TCPConnector(ssl=False)) as http:
            async with http.post(NOTIFY_URL, headers=headers, json=body, timeout=aiohttp.ClientTimeout(total=18)) as resp:
                data = await resp.json(content_type=None)
                ok = resp.status == 200 and not (isinstance(data, dict) and data.get("error"))
                return {"ok": ok, "status": resp.status, "data": data, "campaign": campaign}
    except Exception as e:
        return {"ok": False, "msg": str(e)}


async def bf_claim_offer(session: Dict, day: int, offer_id: int) -> Dict[str, Any]:
    campaign = f"{BF_CAMPAIGN_PREFIX}{day}"
    headers = {
        "Content-Type": "application/json",
        "token": str(session.get("token") or ""),
        "tid": str(session.get("tid") or ""),
        "User-Agent": "Mozilla/5.0 (Linux; Android 13) AppleWebKit/537.36 Chrome/120.0.0.0 Mobile Safari/537.36",
        "Origin": "https://events.swiggy.com",
        "Referer": BF_PAGE_URL,
    }
    body = {"campaign": campaign, "value": offer_id}
    try:
        async with aiohttp.ClientSession(connector=aiohttp.TCPConnector(ssl=False)) as http:
            async with http.post(NOTIFY_URL, headers=headers, json=body, timeout=aiohttp.ClientTimeout(total=18)) as resp:
                data = await resp.json(content_type=None)
                ok = resp.status == 200 and not (isinstance(data, dict) and data.get("error"))
                return {"ok": ok, "status": resp.status, "data": data, "campaign": campaign}
    except Exception as e:
        return {"ok": False, "msg": str(e)}


async def _fetch_pyo_campaign_id() -> str:
    global PYO_CAMPAIGN_ID
    try:
        async with aiohttp.ClientSession(connector=aiohttp.TCPConnector(ssl=False)) as http:
            async with http.get(
                PYO_PAGE_URL,
                headers={"User-Agent": "Mozilla/5.0", "Accept-Language": "en-IN"},
                timeout=aiohttp.ClientTimeout(total=12),
            ) as resp:
                html = await resp.text()
        m = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', html)
        if m:
            nd = json.loads(m.group(1)).get("props", {}).get("pageProps", {}).get("nexusData") or {}
            cid = str(nd.get("notifyCampaignId") or "").strip()
            if cid:
                PYO_CAMPAIGN_ID = cid
    except Exception as e:
        log.warning("PYO campaign fetch failed: %s", e)
    return PYO_CAMPAIGN_ID


async def pyo_claim_offer(session: Dict, offer_id: int) -> Dict[str, Any]:
    campaign = await _fetch_pyo_campaign_id()
    token = str(session.get("token") or "")
    tid = str(session.get("tid") or "")
    headers_base = {
        "Content-Type": "application/json",
        "token": token, "tid": tid,
        "User-Agent": "Mozilla/5.0 (Linux; Android 13) AppleWebKit/537.36 Chrome/120.0.0.0 Mobile Safari/537.36",
        "Accept-Language": "en-IN,en;q=0.9",
        "Origin": "https://events.swiggy.com",
        "Referer": PYO_PAGE_URL,
    }
    steps: Dict[str, Any] = {"campaign": campaign, "offer_id": offer_id}
    try:
        async with aiohttp.ClientSession(connector=aiohttp.TCPConnector(ssl=False)) as http:
            coupon_headers = dict(headers_base)
            coupon_headers["offerindex"] = str(offer_id)
            async with http.post(
                f"{EVENTS_BASE}/api/pick-your-offer-coupon",
                headers=coupon_headers, json={},
                timeout=aiohttp.ClientTimeout(total=20),
            ) as resp:
                try:
                    coupon_data = await resp.json(content_type=None)
                except Exception:
                    coupon_data = {"raw": (await resp.text())[:400]}
                steps["coupon_status"] = resp.status
                steps["coupon"] = coupon_data
                coupon_ok = resp.status in (200, 201) and not (
                    isinstance(coupon_data, dict) and coupon_data.get("error")
                )
            if not coupon_ok:
                return {
                    "ok": False, "status": steps.get("coupon_status", 0),
                    "data": coupon_data if isinstance(coupon_data, dict) else {},
                    "msg": f"coupon create failed: {coupon_data}", "campaign": campaign, "steps": steps,
                }
            end_date = None
            if isinstance(coupon_data, dict):
                inner = coupon_data.get("data") if isinstance(coupon_data.get("data"), dict) else coupon_data
                if isinstance(inner, dict):
                    end_date = inner.get("end_date") or inner.get("endDate") or inner.get("offerEndTime")
                    steps["coupon_code"] = inner.get("coupon_code") or inner.get("couponCode") or inner.get("code")
            note = json.dumps({"offerEndTime": end_date}) if end_date is not None else None
            already_claimed = False
            async with http.get(f"{NOTIFY_URL}?campaign={campaign}", headers=headers_base, timeout=aiohttp.ClientTimeout(total=15)) as resp:
                try:
                    st_data = await resp.json(content_type=None)
                except Exception:
                    st_data = {}
                if isinstance(st_data, dict) and st_data.get("value") not in (None, "", 0, "0"):
                    already_claimed = True
            notify_body: Dict[str, Any] = {"campaign": campaign, "value": offer_id}
            if note:
                notify_body["note"] = note
            method = "PATCH" if already_claimed else "POST"
            async with http.request(method, NOTIFY_URL, headers=headers_base, json=notify_body, timeout=aiohttp.ClientTimeout(total=15)) as resp:
                try:
                    notify_data = await resp.json(content_type=None)
                except Exception:
                    notify_data = {"raw": (await resp.text())[:300]}
                steps["notify_status"] = resp.status
                notify_ok = resp.status == 200 and not (isinstance(notify_data, dict) and notify_data.get("error"))
            return {
                "ok": bool(coupon_ok),
                "status": steps.get("coupon_status", 0),
                "data": coupon_data if isinstance(coupon_data, dict) else {},
                "notify_ok": notify_ok, "campaign": campaign, "steps": steps,
                "coupon_code": steps.get("coupon_code"), "end_date": end_date,
            }
    except Exception as e:
        log.exception("pyo_claim_offer failed")
        return {"ok": False, "status": 0, "data": {}, "msg": str(e), "campaign": campaign, "steps": steps}


# ─────────────────────────────────────────────────────────────────────────────
# Diya
# ─────────────────────────────────────────────────────────────────────────────

def parse_diya_link(raw: str) -> Tuple[str, str]:
    value = (raw or "").strip()
    match = _DIYA_URL_RE.search(value)
    if match:
        value = match.group(1)
    if not re.fullmatch(r"[A-Za-z0-9_-]+", value):
        return "", ""
    parts = [p for p in value.split("-") if p]
    if not parts:
        return "", ""
    return parts[0], parts[1] if len(parts) > 1 else ""


def _unique_diya_links() -> List[Dict[str, str]]:
    out: List[Dict[str, str]] = []
    for url in DIYA_DEFAULT_LINKS:
        camp, ref = parse_diya_link(url)
        if not camp or not ref:
            continue
        out.append({
            "label": f"Diya {len(out)+1}",
            "url": url.strip(),
            "campaign_id": camp,
            "referrer_id": ref,
        })
    return out


async def _request(session: Dict, http: aiohttp.ClientSession, method: str, path: str,
                   body: Optional[Dict] = None) -> Dict[str, Any]:
    kwargs: Dict[str, Any] = {
        "headers": build_headers(session),
        "timeout": aiohttp.ClientTimeout(total=20),
    }
    if body is not None:
        kwargs["json"] = body
    try:
        async with http.request(method, SPNS_BASE_URL + path, **kwargs) as resp:
            raw_text = await resp.text()
            try:
                data = json.loads(raw_text) if raw_text else {}
            except (TypeError, ValueError):
                data = {}
            if not isinstance(data, dict):
                data = {}
            status_code = data.get("statusCode")
            ok = 200 <= resp.status < 300 and status_code in (None, 0, "0")
            return {
                "ok": ok, "status": resp.status,
                "msg": str(data.get("statusMessage") or ("OK" if ok else f"HTTP {resp.status}")),
                "data": data.get("data") if isinstance(data.get("data"), dict) else {},
            }
    except asyncio.TimeoutError:
        return {"ok": False, "status": 0, "msg": "Request timed out", "data": {}}
    except Exception as exc:
        return {"ok": False, "status": 0, "msg": str(exc), "data": {}}


async def diya_light_one(session: Dict, campaign_id: str, referrer_id: str,
                         http: aiohttp.ClientSession) -> Dict[str, Any]:
    result = await _request(session, http, "POST", CASHLOOT_CREATE_OFFERS_PATH, body={
        "campaignId": campaign_id,
        "senderUserId": referrer_id,
        "isReferralFlow": True,
        "receivers": [{"userId": _account_user_id(session)}],
    })
    msg_l = (result.get("msg") or "").lower()
    joined = any(w in msg_l for w in ("success", "credited", "earned", "lit", "lighted", "already", "ok"))
    already = any(w in msg_l for w in ("already", "duplicate"))
    result["joined"] = joined
    result["already_joined"] = already
    return result


async def run_diya_collect(session: Dict, progress_callback=None) -> Dict[str, Any]:
    links = _unique_diya_links()
    total = len(links)
    ok_n = already_n = fail_n = 0
    details: List[str] = []
    async with aiohttp.ClientSession(
        cookie_jar=aiohttp.CookieJar(unsafe=True),
        connector=aiohttp.TCPConnector(ssl=False),
    ) as http:
        for idx, link in enumerate(links, 1):
            if progress_callback:
                try:
                    await progress_callback(idx, total, link["label"])
                except Exception:
                    pass
            r = await diya_light_one(session, link["campaign_id"], link["referrer_id"], http)
            if r.get("already_joined"):
                already_n += 1
                details.append(f"○ {link['label']}: already")
            elif r.get("joined") or r.get("ok"):
                ok_n += 1
                details.append(f"● {link['label']}: lit")
            else:
                fail_n += 1
                details.append(f"✗ {link['label']}: {r.get('msg','fail')}")
            await asyncio.sleep(0.35)
    return {
        "ok": True,
        "lit": ok_n, "already": already_n, "fail": fail_n, "total": total,
        "details": details,
        "earned_est": ok_n * DIYA_PER_LIGHT,
    }


# ─────────────────────────────────────────────────────────────────────────────
# Multi-account claim helper
# ─────────────────────────────────────────────────────────────────────────────

async def claim_on_sessions(
    sessions: List[Dict],
    kind: str,
    offer_id: int = 1,
    day: Optional[int] = None,
    progress=None,
) -> List[Dict[str, Any]]:
    """kind: ln | bf | pyo | diya"""
    results = []
    day = day or _current_ln_day()
    for i, sess in enumerate(sessions):
        label = sess.get("name") or sess.get("mobile") or sess.get("customerId") or f"acc{i+1}"
        try:
            if kind == "ln":
                r = await ln_claim_offer(sess, day, offer_id)
            elif kind == "bf":
                r = await bf_claim_offer(sess, day, offer_id)
            elif kind == "pyo":
                r = await pyo_claim_offer(sess, offer_id)
            elif kind == "diya":
                r = await run_diya_collect(sess)
            else:
                r = {"ok": False, "msg": "unknown kind"}
            results.append({"account": label, "customerId": sess.get("customerId"), "result": r})
        except Exception as e:
            results.append({"account": label, "customerId": sess.get("customerId"), "result": {"ok": False, "msg": str(e)}})
        if progress:
            try:
                await progress(i + 1, len(sessions), label)
            except Exception:
                pass
        await asyncio.sleep(0.4)
    return results
