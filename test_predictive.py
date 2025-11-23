#!/usr/bin/env python3
"""
Test script for predictive mode.
Runs a one-off predictive decision with debug output.
"""
import config
import main
from query_service import QueryService

if __name__ == "__main__":
    print("=" * 60)
    print("OCTOPUS MINMAX BOT - PREDICTIVE MODE TEST")
    print("=" * 60)
    print(f"Debug mode: {config.DEBUG}")
    print(f"Predictive mode: {config.PREDICTIVE_MODE}")
    print(f"Dry run: {config.DRY_RUN}")
    print("=" * 60)
    print()
    
    # Initialize query service and tariffs
    main.query_service = QueryService(config.API_KEY, config.BASE_URL)
    main.load_tariffs_from_ids(config.TARIFFS)
    
    # Run predictive decision
    main.make_predictive_decision()
    
    print()
    print("=" * 60)
    print("TEST COMPLETE")
    print("=" * 60)


