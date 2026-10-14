"""Multiple independent institution-owned AI credentials (admin SQL Server ONLY).

No client LIS connection or table is ever opened here. Key material never leaves
server endpoints. Existing single-key institutions are read as a legacy slot
until an administrator explicitly saves the new multi-provider form.
"""
from datetime import datetime
from database.license_db import get_conn
from auth.secrets_crypto import encrypt_secret, decrypt_secret

MAX_SLOTS = 25


def _dict(row):
    if row is None:
        return None
    if hasattr(row, "items"):
        return dict(row.items())
    raise TypeError("institution DB adapter must return DictRow")


def _get_inst(cur, institution_id):
    r = cur.execute("SELECT * FROM institutions WHERE id = ?", (institution_id,)).fetchone()
    if not r:
        raise ValueError("Institution not found")
    return _dict(r)


def _raw_slots(cur, institution_id):
    rows = cur.execute(
        "SELECT position, enabled, provider, model, api_key, base_url, key_status, checked_at "
        "FROM institution_ai_slots WHERE institution_id = ? ORDER BY position ASC",
        (institution_id,)
    ).fetchall()
    return [_dict(r) for r in rows]


def _legacy(inst):
    if not inst.get("llm_api_key"):
        return []
    return [{"position": 1, "enabled": True,
             "provider": inst.get("llm_provider") or "",
             "model": inst.get("llm_model") or "",
             "api_key": inst["llm_api_key"],
             "base_url": inst.get("llm_base_url") or "",
             "key_status": inst.get("llm_key_status") or "not_checked",
             "checked_at": inst.get("llm_key_checked_at"), "legacy": True}]


def public_slots(institution_id):
    conn = get_conn()
    try:
        cur = conn.cursor()
        inst = _get_inst(cur, institution_id)
        slots = _raw_slots(cur, institution_id) or _legacy(inst)
        return {
            "institution_id": institution_id,
            "allow_athentech_fallback": bool(inst.get("allow_athentech_fallback")),
            "slots": [{"position": int(s["position"]), "enabled": bool(s["enabled"]),
                       "provider": s.get("provider") or "", "model": s.get("model") or "",
                       "base_url": s.get("base_url") or "", "has_key": bool(s.get("api_key")),
                       "key_status": s.get("key_status") or "not_checked",
                       "checked_at": s.get("checked_at"), "legacy": bool(s.get("legacy"))}
                      for s in slots],
        }
    finally:
        conn.close()


def runtime_slots(client_prefix, provider_tier=None):
    """Return enabled owned credentials or [] for none. Never return plaintext to API clients."""
    conn = get_conn()
    try:
        cur = conn.cursor()
        row = cur.execute("SELECT * FROM institutions WHERE client_prefix = ?", (str(client_prefix).upper(),)).fetchone()
        if not row:
            raise ValueError("Institution not found")
        inst = _dict(row)
        slots = _raw_slots(cur, inst["id"])
        if not slots:
            slots = _legacy(inst)
        configured = []
        has_any_own_slot = any(
            bool(s["enabled"]) and bool(s.get("provider")) and
            (bool(s.get("api_key")) or s.get("provider") == "ollama_local")
            for s in slots
        )
        for s in slots:
            if not s["enabled"]:
                continue
            # Choose the requested tier BEFORE constructing or validating the
            # model. A disconnected local model must not disable an unrelated,
            # explicitly configured institution cloud model for complex work.
            if provider_tier == "complex" and s.get("provider") == "ollama_local":
                continue
            if provider_tier == "routine" and s.get("provider") != "ollama_local":
                continue
            encrypted = s.get("api_key")
            if not encrypted and s.get("provider") == "ollama_local":
                from agent.ollama_local import assert_allowed
                chosen_model = s.get("model") or "qwen3:4b"
                assert_allowed(str(client_prefix), chosen_model)
                configured.append({"position": int(s["position"]), "provider": "ollama_local",
                                   "model": chosen_model, "base_url": None, "api_key": "local-no-external-key"})
                continue
            if not encrypted:
                continue
            if not s.get("provider"):
                raise ValueError("Enabled institution provider is missing")
            secret = decrypt_secret(encrypted)
            if not secret:
                raise ValueError("Institution AI key cannot be decrypted")
            configured.append({"position": int(s["position"]), "provider": s["provider"],
                               "model": s.get("model"), "base_url": s.get("base_url"),
                               "api_key": secret})
        response = {"providers": configured,
                    "allow_athentech_fallback": bool(inst.get("allow_athentech_fallback"))}
        if provider_tier is not None:
            response["had_active_slots"] = has_any_own_slot
        return response
    finally:
        conn.close()


def save_slots(institution_id, slot_payload, allow_fallback, validate_key):
    """Atomic replace. Validate fresh keys before altering ANY records.

    Existing encrypted keys are retained only if provider, model and URL match.
    This prevents silently assigning a key to a different API host/model.
    """
    if not isinstance(slot_payload, list) or not (1 <= len(slot_payload) <= MAX_SLOTS):
        raise ValueError("Enter 1 to 25 provider slots")
    positions = [s.get("position") for s in slot_payload if isinstance(s, dict)]
    if len(positions) != len(slot_payload) or positions != list(range(1, len(slot_payload) + 1)):
        raise ValueError("Provider slots must be numbered consecutively starting at 1")
    if slot_payload[0].get("enabled") is not True:
        raise ValueError("Provider 1 must remain enabled (its key can be left blank)")
    if not isinstance(allow_fallback, bool):
        raise ValueError("Fallback consent must be an explicit checkbox value")

    conn = get_conn()
    try:
        cur = conn.cursor()
        inst = _get_inst(cur, institution_id)
        old_slots = _raw_slots(cur, institution_id) or _legacy(inst)
        old_by_pos = {int(x["position"]): x for x in old_slots}
        prepared = []
        now = datetime.utcnow().isoformat()
        from agent.llm_providers import provider_info

        for s in slot_payload:
            pos = s["position"]
            provider = (s.get("provider") or "").strip().lower()
            model = (s.get("model") or "").strip()
            url = (s.get("base_url") or "").strip()
            key = (s.get("api_key") or "").strip()
            enabled = bool(s.get("enabled"))
            old = old_by_pos.get(pos, {})
            if provider and not provider_info(provider):
                raise ValueError(f"Provider {pos}: unknown provider")
            if provider == "github":
                raise ValueError(f"Provider {pos}: this provider is retired")
            if len(provider) > 50 or len(model) > 150 or len(url) > 350 or len(key) > 1600:
                raise ValueError(f"Provider {pos}: one or more fields exceed maximum size")
            if not provider and (key or model or url):
                raise ValueError(f"Provider {pos}: select the provider first")
            if s.get("clear_key"):
                # Explicitly remove this slot's saved credential without touching
                # the other providers or their priority.
                key = ""
                old = {}
            if provider == "ollama_local":
                from agent.ollama_local import assert_allowed
                if key or url:
                    raise ValueError(f"Provider {pos}: local Ollama needs no API key or URL")
                model = model or "qwen3:4b"
                assert_allowed(inst.get("client_prefix"), model)
                encrypted, status, checked_at = None, "local_configured", None
            elif key:
                if not provider:
                    raise ValueError(f"Provider {pos}: select the provider first")
                check = validate_key(provider, key, model or None, url or None)
                if not check.get("ok"):
                    # Error is safe provider diagnostic, not a secret.
                    raise ValueError(f"Provider {pos}: {check.get('message', 'Key verification failed')}")
                encrypted = encrypt_secret(key)
                status = "valid"
                checked_at = now
            else:
                old_provider = (old.get("provider") or "").lower()
                old_model = old.get("model") or ""
                old_url = old.get("base_url") or ""
                if old.get("api_key") and provider == old_provider and url == old_url:
                    encrypted = old["api_key"]
                    if model != old_model:
                        # Revalidate a model-only edit using the existing saved
                        # key server-side; do not make an admin retype secrets.
                        previous_secret = decrypt_secret(encrypted)
                        if not previous_secret:
                            raise ValueError(f"Provider {pos}: saved API key unavailable")
                        check = validate_key(provider, previous_secret, model or None, url or None)
                        if not check.get("ok"):
                            raise ValueError(f"Provider {pos}: {check.get('message', 'Model validation failed')}")
                        status, checked_at = "valid", now
                    else:
                        status = old.get("key_status") or "not_checked"
                        checked_at = old.get("checked_at")
                else:
                    if old.get("api_key") and provider:
                        raise ValueError(f"Provider {pos}: enter a new key when changing provider or API URL")
                    encrypted, status, checked_at = None, "not_configured", None
            if enabled and pos > 1 and not encrypted and provider != "ollama_local":
                raise ValueError(f"Provider {pos}: add and validate a key before enabling this provider")
            prepared.append((pos, enabled, provider or None, model or None, encrypted, url or None, status, checked_at))

        # Single database transaction: keys, enabled state, priority, consent and
        # legacy mirror succeed together or not at all.
        cur.execute("DELETE FROM institution_ai_slots WHERE institution_id = ?", (institution_id,))
        for pos, enabled, provider, model, encrypted, url, status, checked_at in prepared:
            cur.execute(
                "INSERT INTO institution_ai_slots "
                "(institution_id, position, enabled, provider, model, api_key, base_url, key_status, checked_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (institution_id, pos, int(enabled), provider, model, encrypted, url, status, checked_at)
            )
        # Mirror primary for any untouched legacy callers; still encrypted.
        first = prepared[0]
        cur.execute(
            "UPDATE institutions SET llm_provider=?,llm_model=?,llm_api_key=?,llm_base_url=?, "
            "llm_key_status=?,llm_key_checked_at=?,allow_athentech_fallback=? WHERE id=?",
            (first[2] if first[4] else None, first[3] if first[4] else None, first[4],
             first[5] if first[4] else None, first[6] if first[4] else None,
             first[7] if first[4] else None, int(allow_fallback), institution_id)
        )
        conn.commit()
    except Exception:
        try:
            # The production DictConn wrapper does not expose rollback(),
            # but its underlying pyodbc connection does. Never commit a
            # partially replaced credential list.
            raw = getattr(conn, "rollback", None)
            if callable(raw):
                raw()
            elif hasattr(conn, "_conn"):
                conn._conn.rollback()
        except Exception:
            pass
        raise
    finally:
        conn.close()
    from agent.llm_providers import invalidate
    invalidate()
    return public_slots(institution_id)


def revalidate_slot(institution_id, position, validate_key):
    conn = get_conn()
    try:
        cur = conn.cursor()
        inst = _get_inst(cur, institution_id)
        rows = _raw_slots(cur, institution_id) or _legacy(inst)
        slot = next((x for x in rows if int(x["position"]) == position), None)
        if slot and slot.get("provider") == "ollama_local":
            from agent.ollama_local import check_health
            return check_health(inst.get("client_prefix"), slot.get("model") or "qwen3:4b")
        if not slot or not slot.get("api_key"):
            raise ValueError("No saved key for this provider")
        key = decrypt_secret(slot["api_key"])
        if not key:
            raise ValueError("Could not decrypt the saved key")
        result = validate_key(slot["provider"], key, slot.get("model"), slot.get("base_url"))
        code = "valid" if result["ok"] else result.get("code", "invalid")
        now = datetime.utcnow().isoformat()
        if slot.get("legacy"):
            cur.execute("UPDATE institutions SET llm_key_status=?,llm_key_checked_at=? WHERE id=?", (code, now, institution_id))
        else:
            cur.execute("UPDATE institution_ai_slots SET key_status=?,checked_at=? WHERE institution_id=? AND position=?", (code, now, institution_id, position))
            if position == 1:
                cur.execute("UPDATE institutions SET llm_key_status=?,llm_key_checked_at=? WHERE id=?", (code, now, institution_id))
        conn.commit()
        return result
    finally:
        conn.close()
