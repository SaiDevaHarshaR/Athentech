import json, os
from agent import schema_ctx as s

def _pin(name, cfg):
    d = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "config", "clients")
    os.makedirs(d, exist_ok=True)
    fp = os.path.join(d, name + ".json"); json.dump(cfg, open(fp, "w")); return fp

def test_pins_are_per_client_and_validated():
    fa = _pin("ZZ_A", {"version": 2, "coll_metric": "total", "pat_name": "BAD", "coll_paid": "x;DROP"})
    try:
        pa, pb = dict(s._DEFAULTS), dict(s._DEFAULTS)
        t = {"pt": {"NAME": "NAME"}, "cc": {}}
        s._apply_client_config(pa, "ZZ_A", t); s._apply_client_config(pb, "ZZ_B", t)
        assert pa["coll_metric"] == "total" and pb["coll_metric"] == "paid"
        assert pa["coll_paid"] == "PAIDAMOUNT" and "coll_paid" in pa["client_config_rejected"]
    finally:
        os.remove(fa)

def test_invalidate_only_one_client():
    s._cache.clear(); s._cache["|A"] = (0, {}); s._cache["|B"] = (0, {})
    s.invalidate("A"); assert "|A" not in s._cache and "|B" in s._cache

def test_capabilities_need_confirmation():
    assert s.capabilities(dict(s._DEFAULTS))["doctors"] is False

def test_bom_pin_and_pinned_metric():
    d = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "config", "clients")
    fp = os.path.join(d, "ZZ_BOM.json")
    open(fp, "w", encoding="utf-8-sig").write('{"version":1,"coll_metric":"total"}')
    try:
        assert s.pinned_metric("ZZ_BOM") == "total"
        assert s.pinned_metric("../etc") is None
        p = dict(s._DEFAULTS); s._apply_client_config(p, "ZZ_BOM", {})
        assert p["coll_metric"] == "total"
    finally:
        os.remove(fp)
