import json
import os

from src.negotiation_state import (
    NegotiationState,
    create_session,
    load_state,
    save_state,
    session_file_path,
    state_to_prompt_context,
    update_state,
)


def test_store_location_comes_from_environment(isolated_env):
    assert session_file_path() == str(isolated_env / "sessions.json")


def test_create_update_and_reload_round_trip():
    state = create_session("s1")
    assert state.started_at.endswith("+00:00")  # timezone-aware UTC

    update_state(state, {"opening_ask": 150.0, "current_offer": 105.0, "not_a_field": 1})
    loaded = load_state("s1")

    assert loaded is not None
    assert loaded.opening_ask == 150.0
    assert loaded.current_offer == 105.0
    assert not hasattr(loaded, "not_a_field")


def test_unknown_session_returns_none():
    create_session("s1")
    assert load_state("missing") is None


def test_missing_store_returns_none():
    assert load_state("anything") is None


def test_several_sessions_share_one_store():
    create_session("a")
    create_session("b")
    with open(session_file_path(), encoding="utf-8") as f:
        assert set(json.load(f)) == {"a", "b"}


def test_corrupt_store_is_moved_aside_and_saving_recovers():
    path = session_file_path()
    with open(path, "w", encoding="utf-8") as f:
        f.write('{"truncated": ')

    assert load_state("x") is None  # does not raise
    assert os.path.exists(path + ".corrupt")

    save_state(NegotiationState(session_id="fresh"))
    assert load_state("fresh") is not None


def test_failed_write_leaves_existing_store_intact(monkeypatch):
    create_session("keep")

    def boom(*args, **kwargs):
        raise OSError("disk full")

    with monkeypatch.context() as m:
        m.setattr(json, "dump", boom)
        save_state(NegotiationState(session_id="lost"))  # logged, not raised

    assert load_state("keep") is not None
    assert load_state("lost") is None
    leftovers = [p for p in os.listdir(os.path.dirname(session_file_path())) if p.endswith(".tmp")]
    assert leftovers == []


def test_records_from_older_versions_with_extra_keys_still_load():
    with open(session_file_path(), "w", encoding="utf-8") as f:
        json.dump({"old": {"session_id": "old", "opening_ask": 10.0, "legacy_field": True}}, f)
    loaded = load_state("old")
    assert loaded is not None and loaded.opening_ask == 10.0


def test_prompt_context_lists_state():
    state = NegotiationState(session_id="s", opening_ask=150.0, current_offer=105.0,
                             clauses_seen=["Annual commitment"], red_flags=["Budget freeze"])
    context = state_to_prompt_context(state)
    assert "OPENING ASK: $150.0 | CURRENT OFFER: $105.0" in context
    assert "CLAUSES SEEN: Annual commitment" in context
    assert "LEVERAGE: none" in context
    assert "RED FLAGS: Budget freeze" in context


def test_prompt_context_tolerates_non_string_entries():
    state = NegotiationState(session_id="s", red_flags=[None, 3])
    assert "RED FLAGS: None, 3" in state_to_prompt_context(state)
