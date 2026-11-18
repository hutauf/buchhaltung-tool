"""Version-1 compatibility and bounded serialization during full history replay."""
import copy

import pytest

import autobookkeeping.audit_trail as audit
from autobookkeeping.archive import encoded, sha


def legacy_catalog(states):
    """Build historical hashes with the original whole-state byte encoding."""
    trail = {"version": 1, "baseline_kind": "existing_state",
             "baseline": copy.deepcopy(states[0]), "events": []}
    for sequence, (before, after) in enumerate(zip(states, states[1:]), 1):
        event = {"sequence": sequence, "at": "2011-01-01T00:00:00+00:00",
                 "writer": "local-helper", "tool_commit": "a" * 40,
                 "previous_sha256": trail["events"][-1]["sha256"] if trail["events"] else None,
                 "before_sha256": sha(encoded(before)), "after_sha256": sha(encoded(after)),
                 "changes": audit.changes(before, after)}
        event["sha256"] = sha(encoded(event))
        trail["events"].append(event)
    return dict(copy.deepcopy(states[-1]), audit_trail=trail)


def test_existing_hashes_cover_nested_changes_replacements_and_escaped_keys():
    special = 'SYNTHETIC \u00e4\n"quoted" \\ / ~'
    first = {"records": {"one": {"text": special, "items": [False, 0, None, -0.0, 1e-20]},
                         "two": {"unchanged": True}}, "flag": False}
    second = copy.deepcopy(first)
    second["records"]["one"]["text"] = "SYNTHETIC UPDATED"
    second["records"]["three"] = {"empty": {}}
    second["flag"] = 0
    third = copy.deepcopy(second)
    del third["records"]["two"]
    third["records"]["one"] = ["SYNTHETIC LIST", {special: 12.5}]
    states = [{}, first, second, third, {"records": []}, {"records": {}},
              {"records": {special: {"active": True}}}, {}]
    catalog = legacy_catalog(states)
    original = encoded(catalog)
    result = audit.validate(catalog)
    assert result["events"] == len(states) - 1
    assert result["head_sha256"] == catalog["audit_trail"]["events"][-1]["sha256"]
    assert encoded(catalog) == original


def test_non_string_legacy_dictionary_keys_keep_original_encoding():
    states = [{7: {"value": "SYNTHETIC"}}, {7: {"value": "SYNTHETIC"}}]
    assert audit.validate(legacy_catalog(states))["events"] == 1
    states = [{"records": {7: "SYNTHETIC"}, "counter": 0},
              {"records": {7: "SYNTHETIC"}, "counter": 1}]
    assert audit.validate(legacy_catalog(states))["events"] == 1


@pytest.mark.parametrize("target", ["before_hash", "after_hash", "before_value", "after_value", "time"])
def test_rehashed_event_still_requires_valid_state_and_change_preconditions(target):
    catalog = legacy_catalog([{"control": {"counter": 0}}, {"control": {"counter": 1}}])
    event = catalog["audit_trail"]["events"][-1]
    if target == "before_hash":
        event["before_sha256"] = "0" * 64
    elif target == "after_hash":
        event["after_sha256"] = "0" * 64
    elif target == "before_value":
        event["changes"][0]["before"] = 99
    elif target == "after_value":
        event["changes"][0]["after"] = 99
    else:
        event["at"] = "2011-01-01T00:00:00"
    event["sha256"] = sha(encoded({k: v for k, v in event.items() if k != "sha256"}))
    with pytest.raises(ValueError):
        audit.validate(catalog)


def test_new_verification_does_not_trust_fragments_from_a_previous_call():
    catalog = legacy_catalog([{"records": {"one": {"flag": True}}},
                              {"records": {"one": {"flag": False}}}])
    assert audit.validate(catalog)["status"] == "verified"
    catalog["records"]["one"]["flag"] = 0
    with pytest.raises(ValueError, match="Datenbank"):
        audit.validate(catalog)


def test_altered_baseline_and_earlier_history_are_not_skipped():
    catalog = legacy_catalog([{"counter": 0}, {"counter": 1}, {"counter": 2}])
    # A valid last event cannot conceal a changed earlier event/baseline.
    broken = copy.deepcopy(catalog)
    broken["audit_trail"]["baseline"]["counter"] = 10
    with pytest.raises(ValueError):
        audit.validate(broken)
    broken = copy.deepcopy(catalog)
    broken["audit_trail"]["events"][0]["writer"] = "SYNTHETIC ALTERED"
    with pytest.raises(ValueError):
        audit.validate(broken)


def test_unchanged_payload_is_not_reserialized_for_every_historical_state(monkeypatch):
    initial = {"records": {f"synthetic-{i}": {"payload": "SYNTHETIC " * 80}
                           for i in range(30)}, "controls": {}}
    states = [initial]
    for i in range(60):
        successor = copy.deepcopy(states[-1])
        successor["controls"][str(i)] = {"checked": True}
        states.append(successor)
    catalog = legacy_catalog(states)
    serialized_bytes = 0

    def counted(value):
        nonlocal serialized_bytes
        result = encoded(value)
        serialized_bytes += len(result)
        return result

    monkeypatch.setattr(audit, "encoded", counted)
    assert audit.validate(catalog)["events"] == 60
    # A workload bound, independent of machine speed: replay must not serialize
    # the unchanged records sixty times. Historical hashes remain mandatory.
    assert serialized_bytes < 5 * len(encoded(catalog))


def test_operation_cache_reuses_only_successful_exact_catalog_bytes_and_is_discarded(monkeypatch):
    catalog = legacy_catalog([{'records': {'one': {'flag': True}}},
                              {'records': {'one': {'flag': False}}}])
    calls = []; original = audit._validate
    def counted(value):
        calls.append(True)
        return original(value)
    monkeypatch.setattr(audit, '_validate', counted)
    with audit.verification_session():
        first = audit.validate(catalog)
        first['status'] = 'tampered returned result'
        assert audit.validate(copy.deepcopy(catalog))['status'] == 'verified'
        assert len(calls) == 1
        with audit.verification_session():
            assert audit.validate(catalog)['status'] == 'verified'
        assert len(calls) == 1
        # False and 0 compare equal in Python, but have different canonical bytes.
        broken = copy.deepcopy(catalog); broken['records']['one']['flag'] = 0
        for _ in range(2):
            with pytest.raises(ValueError, match='Datenbank'):
                audit.validate(broken)
        assert len(calls) == 3
    assert audit.validate(catalog)['status'] == 'verified'
    assert len(calls) == 4


@pytest.mark.parametrize('part', ['baseline', 'early_event', 'current', 'last_hash'])
def test_operation_cache_does_not_conceal_any_history_or_current_state_change(part):
    catalog = legacy_catalog([{'counter': 0}, {'counter': 1}, {'counter': 2}])
    with audit.verification_session():
        assert audit.validate(catalog)['status'] == 'verified'
        if part == 'baseline': catalog['audit_trail']['baseline']['counter'] = 99
        elif part == 'early_event': catalog['audit_trail']['events'][0]['writer'] = 'SYNTHETIC ALTERED'
        elif part == 'current': catalog['counter'] = 99
        else: catalog['audit_trail']['events'][-1]['sha256'] = '0' * 64
        with pytest.raises(ValueError):
            audit.validate(catalog)


def test_operation_cache_is_cleared_on_error(monkeypatch):
    catalog = legacy_catalog([{'counter': 0}, {'counter': 1}])
    with pytest.raises(OSError):
        with audit.verification_session():
            audit.validate(catalog)
            raise OSError('Synthetic interrupted operation')
    monkeypatch.setattr(audit, '_validate', lambda value: pytest.fail('A later operation must verify again'))
    with pytest.raises(pytest.fail.Exception):
        audit.validate(catalog)
