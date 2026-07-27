#!/usr/bin/env python3
"""Shared origin config + baseline loading for the daily Instagram pipeline.

One place decides what "the origin we are posting for" means, so render_slides,
fetch_fares and publish_instagram can never disagree about it.
"""
import json, os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def origin_code():
    """The origin this run is posting for. Defaults to CLT so every existing
    invocation — including a manual `python pipeline/render_slides.py` — keeps
    doing exactly what it did before this became multi-city."""
    return (os.environ.get("ORIGIN") or "CLT").strip().upper()


def config(code=None):
    code = code or origin_code()
    with open(os.path.join(ROOT, "config", "origins.json"), encoding="utf-8") as fh:
        cfg = json.load(fh)
    if code not in cfg:
        raise SystemExit(f"FATAL: origin {code} is not in config/origins.json")
    out = dict(cfg[code])
    out["code"] = code
    return out


def baselines(code=None):
    """Typical-cheap-fare curves for the origin.

    Prefers state/baselines-<CODE>.json (written by scripts/seed_baselines.py).
    Falls back to the original flat state/baselines.json, which is Charlotte's
    hand-tuned file — so CLT keeps posting off the exact curves it always has.

    Returns {DEST: {"city": str, "m": [12 ints]}} for board-eligible routes only.
    A route benched by the seeder (ig_board false) is deliberately excluded: its
    "% below typical" could not be defended against real market fares.
    """
    code = code or origin_code()
    per_origin = os.path.join(ROOT, "state", f"baselines-{code}.json")
    if os.path.exists(per_origin):
        with open(per_origin, encoding="utf-8") as fh:
            doc = json.load(fh)
        routes = doc.get("routes", doc)
        return {k: {"city": v["city"], "m": v["m"]}
                for k, v in routes.items()
                if isinstance(v, dict) and "m" in v and v.get("ig_board", True)}

    legacy = os.path.join(ROOT, "state", "baselines.json")
    if code == "CLT" and os.path.exists(legacy):
        with open(legacy, encoding="utf-8") as fh:
            return json.load(fh)
    raise SystemExit(f"FATAL: no baselines for {code}. "
                     f"Run: python scripts/seed_baselines.py {code}")


def paths(code=None):
    """Per-origin file locations. CLT keeps the original unsuffixed paths so the
    live account's files, history and slide URLs do not move."""
    code = code or origin_code()
    if code == "CLT":
        return {"deals": "deals.json", "history": "state/history.json", "out": "out"}
    return {"deals": f"deals-{code}.json",
            "history": f"state/history-{code}.json",
            "out": f"out/{code}"}
