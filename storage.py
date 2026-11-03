"""Multi-account storage — up to 15 per user, admin unlimited."""
from __future__ import annotations

import json
import os
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from config import SESSION_FILE, SETTINGS_FILE, MAX_ACCOUNTS_PER_USER, ADMIN_IDS, ADMIN_UNLIMITED

_lock = threading.RLock()


def _load(path: Path, default):
    if path.is_file():
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return default


def _save(path: Path, data):
    tmp = path.with_suffix(".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)


def load_all() -> Dict[str, Any]:
    with _lock:
        data = _load(SESSION_FILE, {"users": {}})
        data.setdefault("users", {})
        return data


def save_all(data: Dict[str, Any]):
    with _lock:
        _save(SESSION_FILE, data)


def get_user_accounts(tg_id: int) -> List[Dict[str, Any]]:
    data = load_all()
    entry = data["users"].get(str(tg_id)) or {}
    return list(entry.get("accounts") or [])


def account_limit(tg_id: int) -> int:
    if ADMIN_UNLIMITED and tg_id in ADMIN_IDS:
        return 999
    return MAX_ACCOUNTS_PER_USER


def add_account(tg_id: int, session: Dict[str, Any]) -> Dict[str, Any]:
    data = load_all()
    uid = str(tg_id)
    entry = data["users"].setdefault(uid, {"accounts": [], "created_at": datetime.now(timezone.utc).isoformat()})
    accounts: List[Dict] = entry.setdefault("accounts", [])
    limit = account_limit(tg_id)
    # dedupe by customerId or mobile
    cid = str(session.get("customerId") or "")
    mobile = str(session.get("mobile") or "")
    accounts = [
        a for a in accounts
        if str(a.get("customerId") or "") != cid or not cid
    ]
    if mobile:
        accounts = [a for a in accounts if str(a.get("mobile") or "") != mobile]
    if len(accounts) >= limit:
        return {"ok": False, "msg": f"Limit {limit} accounts reached. Delete one first."}
    session = dict(session)
    session["slot_id"] = secrets_id()
    session["added_at"] = datetime.now(timezone.utc).isoformat()
    accounts.append(session)
    entry["accounts"] = accounts
    data["users"][uid] = entry
    save_all(data)
    return {"ok": True, "account": session, "count": len(accounts)}


def secrets_id() -> str:
    import secrets
    return secrets.token_hex(6)


def remove_account(tg_id: int, slot_id: str = "", customer_id: str = "", mobile: str = "") -> Dict[str, Any]:
    data = load_all()
    uid = str(tg_id)
    entry = data["users"].get(uid) or {}
    accounts = list(entry.get("accounts") or [])
    before = len(accounts)
    if slot_id:
        accounts = [a for a in accounts if a.get("slot_id") != slot_id]
    elif customer_id:
        accounts = [a for a in accounts if str(a.get("customerId") or "") != str(customer_id)]
    elif mobile:
        accounts = [a for a in accounts if str(a.get("mobile") or "") != str(mobile)]
    else:
        return {"ok": False, "msg": "Need slot_id / customerId / mobile"}
    entry["accounts"] = accounts
    data["users"][uid] = entry
    save_all(data)
    return {"ok": True, "removed": before - len(accounts), "count": len(accounts)}


def update_account(tg_id: int, slot_id: str, session: Dict[str, Any]) -> Dict[str, Any]:
    data = load_all()
    uid = str(tg_id)
    entry = data["users"].get(uid) or {}
    accounts = list(entry.get("accounts") or [])
    found = False
    for i, a in enumerate(accounts):
        if a.get("slot_id") == slot_id:
            session = dict(session)
            session["slot_id"] = slot_id
            session["added_at"] = a.get("added_at") or datetime.now(timezone.utc).isoformat()
            accounts[i] = session
            found = True
            break
    if not found:
        return {"ok": False, "msg": "Account not found"}
    entry["accounts"] = accounts
    data["users"][uid] = entry
    save_all(data)
    return {"ok": True, "account": session}


def get_account(tg_id: int, slot_id: str) -> Optional[Dict]:
    for a in get_user_accounts(tg_id):
        if a.get("slot_id") == slot_id:
            return a
    return None


def load_settings() -> Dict:
    return _load(SETTINGS_FILE, {"force_join_enabled": False, "force_channels": []})


def save_settings(data: Dict):
    _save(SETTINGS_FILE, data)
