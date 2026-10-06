"""Encrypted catalog change history; external Git/OTS anchors remain necessary."""
from __future__ import annotations

import copy
from datetime import datetime, timezone

from autobookkeeping.archive import encoded, sha

FIELD = "audit_trail"


def state(catalog):
    return {key: value for key, value in catalog.items() if key != FIELD}


def changes(before, after, path=()):
    if isinstance(before, dict) and isinstance(after, dict):
        result = []
        for key in sorted(before.keys() | after.keys()):
            child = path + (key,)
            if key not in before or key not in after:
                result.append({"path": list(child), "before_exists": key in before,
                    "after_exists": key in after, "before": copy.deepcopy(before.get(key)),
                    "after": copy.deepcopy(after.get(key))})
            else:
                result.extend(changes(before[key], after[key], child))
        return result
    if encoded(before) == encoded(after):
        return []
    return [{"path": list(path), "before_exists": True, "after_exists": True,
             "before": copy.deepcopy(before), "after": copy.deepcopy(after)}]


def apply(snapshot, change):
    path = change["path"]
    if not path or not all(isinstance(key, str) for key in path):
        raise ValueError("Ungültiger Änderungsprotokoll-Pfad")
    parent = snapshot
    for key in path[:-1]:
        if not isinstance(parent, dict) or key not in parent:
            raise ValueError("Änderungsprotokoll verweist auf fehlenden Vorzustand")
        parent = parent[key]
    key = path[-1]
    if not isinstance(parent, dict) or (key in parent) != change["before_exists"]:
        raise ValueError("Änderungsprotokoll-Vorzustand stimmt nicht")
    if change["before_exists"] and parent[key] != change["before"]:
        raise ValueError("Änderungsprotokoll-Vorwert stimmt nicht")
    if change["after_exists"]:
        parent[key] = copy.deepcopy(change["after"])
    else:
        del parent[key]


def validate(catalog):
    trail = catalog.get(FIELD)
    if trail is None:
        return {"status": "legacy_without_trail", "events": 0}
    if (not isinstance(trail, dict) or trail.get("version") != 1
            or trail.get("baseline_kind") not in ("new_archive", "existing_state")
            or not isinstance(trail.get("events"), list) or not trail["events"]):
        raise ValueError("Unbekanntes Änderungsprotokoll")
    snapshot = copy.deepcopy(trail["baseline"])
    previous = None
    for sequence, event in enumerate(trail["events"], 1):
        body = {key: value for key, value in event.items() if key != "sha256"}
        if event["sequence"] != sequence or event["previous_sha256"] != previous or sha(encoded(body)) != event["sha256"]:
            raise ValueError("Änderungsprotokoll-Kette stimmt nicht")
        timestamp = datetime.fromisoformat(event["at"])
        if timestamp.tzinfo is None:
            raise ValueError("Änderungsprotokoll-Zeitpunkt benötigt Zeitzone")
        if sha(encoded(snapshot)) != event["before_sha256"]:
            raise ValueError("Änderungsprotokoll-Ausgangsstand stimmt nicht")
        for change in event["changes"]:
            apply(snapshot, change)
        if sha(encoded(snapshot)) != event["after_sha256"]:
            raise ValueError("Änderungsprotokoll-Ergebnis stimmt nicht")
        previous = event["sha256"]
    if encoded(snapshot) != encoded(state(catalog)):
        raise ValueError("Datenbank weicht vom Änderungsprotokoll ab")
    return {"status": "verified", "events": len(trail["events"]), "head_sha256": previous}


def prepare(before, after, tool_commit=None):
    """Populate the caller's after-state BEFORE serializing a recovery journal."""
    if before is not None:
        validate(before)
        for name, entry in before.get("documents", {}).items():
            successor = after.get("documents", {}).get(name)
            if successor is None or any(successor.get(k) != entry.get(k) for k in ("sha256_plaintext", "bytes_plaintext")):
                raise ValueError("Originalinventar darf nicht entfernt oder umgeschrieben werden")
    old = state(before) if before is not None else {}
    new = state(after)
    old_trail = before.get(FIELD) if before is not None else None
    supplied = after.get(FIELD)
    if supplied != old_trail and supplied is not None:
        # Recovery may already carry the prepared, exact next event.
        validate(after)
        prefix = old_trail["events"] if old_trail else []
        expected_header = {key: value for key, value in old_trail.items() if key != "events"} if old_trail else {
            "version": 1, "baseline": old, "baseline_kind": "existing_state" if before is not None else "new_archive"}
        if (len(supplied["events"]) != len(prefix) + 1
                or {key: value for key, value in supplied.items() if key != "events"} != expected_header
                or supplied["events"][:-1] != prefix):
            raise ValueError("Vorhandenes Änderungsprotokoll darf nicht ersetzt werden")
        if supplied["events"][-1]["before_sha256"] != sha(encoded(old)):
            raise ValueError("Änderungsprotokoll gehört zu einem anderen Ausgangsstand")
        return
    if old_trail is not None and supplied is None:
        raise ValueError("Änderungsprotokoll darf nicht entfernt werden")
    delta = changes(old, new)
    if not delta and old_trail is not None:
        return
    trail = copy.deepcopy(old_trail) if old_trail else {
        "version": 1, "baseline": copy.deepcopy(old), "events": [],
        "baseline_kind": "existing_state" if before is not None else "new_archive",
    }
    event = {"sequence": len(trail["events"]) + 1,
        "at": datetime.now(timezone.utc).isoformat(), "writer": "local-helper",
        "tool_commit": tool_commit, "previous_sha256": trail["events"][-1]["sha256"] if trail["events"] else None,
        "before_sha256": sha(encoded(old)), "after_sha256": sha(encoded(new)), "changes": delta}
    event["sha256"] = sha(encoded(event))
    trail["events"].append(event)
    after[FIELD] = trail
