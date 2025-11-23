"""
Decision storage for predictive mode.
Stores tariff decisions made during decision phase for execution during switch phase.
"""
import json
import os
from datetime import date, datetime
from pathlib import Path

# Use /tmp on Unix-like systems, or current directory as fallback
if os.name == 'nt':  # Windows
    DECISION_FILE = Path(os.path.expanduser("~")) / "octopus_minmax_decision.json"
else:  # Unix-like (Linux, macOS, Docker)
    DECISION_FILE = Path("/tmp/octopus_minmax_decision.json")

def save_decision(decision_data):
    """
    Save a tariff decision to file.
    
    Args:
        decision_data: Dict with keys: 'target_date', 'chosen_tariff', 'reasoning', 'timestamp'
    """
    try:
        decision_data['timestamp'] = datetime.now().isoformat()
        with open(DECISION_FILE, 'w') as f:
            json.dump(decision_data, f, indent=2)
    except Exception as e:
        print(f"Error saving decision: {e}")

def load_decision():
    """
    Load the most recent tariff decision from file.
    
    Returns:
        Dict with decision data, or None if no decision found
    """
    try:
        if not DECISION_FILE.exists():
            return None
        
        with open(DECISION_FILE, 'r') as f:
            decision = json.load(f)
        
        # Check if decision is for today or tomorrow
        target_date_str = decision.get('target_date')
        if target_date_str:
            target_date = datetime.fromisoformat(target_date_str).date()
            today = date.today()
            # Decision is valid if it's for today or tomorrow
            if target_date >= today:
                return decision
        
        # Decision is stale, remove it
        DECISION_FILE.unlink(missing_ok=True)
        return None
    except Exception as e:
        print(f"Error loading decision: {e}")
        return None

def clear_decision():
    """Clear the stored decision."""
    try:
        if DECISION_FILE.exists():
            DECISION_FILE.unlink()
    except Exception as e:
        print(f"Error clearing decision: {e}")

