import os
import uuid
import logging
import json
from datetime import datetime
from dataclasses import dataclass, field, asdict

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("negotiation_state")

SESSION_FILE = "session_store.json"

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
        started_at=datetime.utcnow().isoformat()
    )
    save_state(state)
    return state

def save_state(state: NegotiationState) -> None:
    """
    Saves the current NegotiationState to a local JSON file.
    """
    try:
        store = {}
        if os.path.exists(SESSION_FILE):
            with open(SESSION_FILE, "r") as f:
                store = json.load(f)
        
        store[state.session_id] = asdict(state)
        
        with open(SESSION_FILE, "w") as f:
            json.dump(store, f, indent=2)
    except Exception as e:
        print(f"LOCAL SAVE ERROR: {e}")

def load_state(session_id: str) -> NegotiationState | None:
    """
    Loads a NegotiationState from the local JSON file by session_id.
    """
    try:
        if not os.path.exists(SESSION_FILE):
            return None
            
        with open(SESSION_FILE, "r") as f:
            store = json.load(f)
            
        if session_id in store:
            return NegotiationState(**store[session_id])
        return None
    except Exception as e:
        print(f"LOCAL LOAD ERROR: {e}")
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
    clauses = ", ".join(state.clauses_seen) if state.clauses_seen else "none"
    leverage = ", ".join(state.leverage_signals) if state.leverage_signals else "none"
    red_flags = ", ".join(state.red_flags) if state.red_flags else "none"
    
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
