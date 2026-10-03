import os
import uuid
import logging
import json
import tempfile
from datetime import datetime, timezone
from dataclasses import dataclass, field, asdict, fields

from src.config import get_settings

logger = logging.getLogger("negotiation_state")


def session_file_path() -> str:
    """Path of the JSON session store (DEALROOM_SESSION_FILE, default session_store.json)."""
    return get_settings().session_file

@dataclass
class NegotiationState:
    session_id: str = ""
    started_at: str = ""
    opening_ask: float = 0.0
    current_offer: float = 0.0
    last_concession: float = 0.0
    clauses_seen: list = field(default_factory=list)
    leverage_signals: list = field(default_factory=list)
    red_flags: list = field(default_factory=list)
    key_moments: list = field(default_factory=list)
    status: str = "active"

def create_session(session_id: str = None) -> NegotiationState:
    """
    Initializes a new negotiation session and saves it locally.
    """
    if session_id is None:
        session_id = str(uuid.uuid4())
    
    state = NegotiationState(
        session_id=session_id,
        started_at=datetime.now(timezone.utc).isoformat()
    )
    save_state(state)
    return state

def _read_store(path: str) -> dict:
    """Read the session store. A missing file is an empty store.

    A corrupt or unreadable file is moved aside (path + ".corrupt") rather
    than silently overwritten, so its data can still be recovered, and the
    store starts empty again instead of failing on every later save.
    """
    if not os.path.exists(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            store = json.load(f)
        if not isinstance(store, dict):
            raise ValueError("session store is not a JSON object")
        return store
    except (ValueError, UnicodeDecodeError) as e:
        backup = path + ".corrupt"
        logger.error("Session store %s is corrupt (%s); moving it to %s", path, e, backup)
        os.replace(path, backup)
        return {}


def _write_store(path: str, store: dict) -> None:
    """Write atomically: a crash mid-write must not leave a truncated file."""
    directory = os.path.dirname(os.path.abspath(path))
    fd, tmp_path = tempfile.mkstemp(dir=directory, prefix=".session_store.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(store, f, indent=2)
        os.replace(tmp_path, path)
    except BaseException:
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)
        raise


def save_state(state: NegotiationState) -> None:
    """
    Saves the current NegotiationState to the local JSON session store.
    Errors are logged, never raised: losing a save must not end a live call.
    """
    path = session_file_path()
    try:
        store = _read_store(path)
        store[state.session_id] = asdict(state)
        _write_store(path, store)
    except Exception as e:
        logger.error("Could not save session %s to %s: %s", state.session_id, path, e)


def load_state(session_id: str) -> NegotiationState | None:
    """
    Loads a NegotiationState from the local JSON session store by session_id.
    Returns None if the session is unknown or the store cannot be read.
    """
    path = session_file_path()
    try:
        record = _read_store(path).get(session_id)
        if not isinstance(record, dict):
            return None
        known = {f.name for f in fields(NegotiationState)}
        return NegotiationState(**{k: v for k, v in record.items() if k in known})
    except Exception as e:
        logger.error("Could not load session %s from %s: %s", session_id, path, e)
        return None

def update_state(state: NegotiationState, updates: dict) -> NegotiationState:
    """
    Updates the NegotiationState object and saves it locally.
    """
    for key, value in updates.items():
        if hasattr(state, key):
            setattr(state, key, value)
    
    save_state(state)
    return state

def state_to_prompt_context(state: NegotiationState) -> str:
    """
    Formats the negotiation state for use as prompt context.
    """
    def joined(items: list) -> str:
        # str() guards against non-string entries in a hand-edited or old store.
        return ", ".join(str(item) for item in items) if items else "none"

    clauses = joined(state.clauses_seen)
    leverage = joined(state.leverage_signals)
    red_flags = joined(state.red_flags)
    
    return (
        f"SESSION: {state.session_id}\n"
        f"OPENING ASK: ${state.opening_ask} | CURRENT OFFER: ${state.current_offer} | LAST CONCESSION: ${state.last_concession}\n"
        f"CLAUSES SEEN: {clauses}\n"
        f"LEVERAGE: {leverage}\n"
        f"RED FLAGS: {red_flags}"
    )

if __name__ == "__main__":
    try:
        # Create session
        test_id = "test-session-001"
        state = create_session(session_id=test_id)
        
        # Update state
        update_state(state, {
            "opening_ask": 150.0,
            "current_offer": 105.0
        })
        
        # Append to list
        current_clauses = list(state.clauses_seen)
        current_clauses.append("Annual commitment clause")
        update_state(state, {"clauses_seen": current_clauses})
        
        # Print context
        print(state_to_prompt_context(state))
        
        # Reload from local file
        loaded = load_state(test_id)
        
        if loaded and loaded.opening_ask == 150.0 and loaded.current_offer == 105.0:
            print("TEST PASSED")
        else:
            reason = "Data mismatch" if loaded else "Could not load state"
            print(f"TEST FAILED: {reason}")
            
    except Exception as e:
        print(f"TEST FAILED with exception: {e}")
