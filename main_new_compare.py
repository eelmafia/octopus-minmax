def compare_tariffs_for_battery(region_code, agile_rates, go_overnight_rate=None):
    """
    Compare Agile and Go tariffs for battery optimization.
    Simple comparison: find Agile periods <= 120% of Go's rate.
    If multiple cheap Agile periods exist, choose Agile. Otherwise compare costs.
    
    Args:
        region_code: Region code
        agile_rates: List of Agile rate periods for tomorrow (from API)
        go_overnight_rate: Go overnight rate in pence/kWh (optional, will fetch if None)
    
    Returns:
        Dict with keys: 'best_tariff' ('agile' or 'go'), 'reasoning', 'agile_cheap_periods', 'go_overnight_rate'
    """
    debug_print("=== Battery Tariff Comparison ===")
    debug_print(f"Battery Capacity: {config.BATTERY_CAPACITY_KWH} kWh")
    debug_print(f"Charge Rate: {config.BATTERY_CHARGE_RATE_KW} kW")
    debug_print(f"Charge Time Needed: {config.BATTERY_CAPACITY_KWH / config.BATTERY_CHARGE_RATE_KW:.2f} hours")
    
    # Get Go overnight rate from API if not provided
    if go_overnight_rate is None:
        tomorrow = date.today() + timedelta(days=1)
        debug_print(f"Fetching Go overnight rate for {tomorrow}...")
        go_overnight_rate = get_go_overnight_rate(region_code, tomorrow)
        if go_overnight_rate is None:
            raise Exception("Could not fetch Octopus Go overnight rate from API. Please ensure your API key has access to tariff rates.")
        debug_print(f"Fetched Go overnight rate: {go_overnight_rate}p/kWh")
    
    # Calculate cheap threshold: 120% of Go's rate
    cheap_threshold = go_overnight_rate * 1.2
    debug_print(f"\nGo Tariff:")
    debug_print(f"  Overnight rate: {go_overnight_rate:.2f}p/kWh")
    debug_print(f"  Cheap threshold (120%): {cheap_threshold:.2f}p/kWh")
    
    # Find Agile periods that are <= 120% of Go's rate
    debug_print(f"\nAgile Tariff Analysis:")
    debug_print(f"  Total rate periods: {len(agile_rates)}")
    
    cheap_periods = []
    for rate_period in agile_rates:
        rate_value = float(rate_period.get('value_inc_vat', 0))
        if rate_value <= cheap_threshold:
            valid_from = rate_period.get('valid_from', '')
            try:
                dt = datetime.fromisoformat(valid_from.replace('Z', '+00:00'))
                cheap_periods.append({
                    'rate': rate_value,
                    'datetime': dt,
                    'time': dt.strftime('%H:%M'),
                    'minutes': dt.hour * 60 + dt.minute
                })
            except:
                continue
    
    # Sort by time
    cheap_periods.sort(key=lambda x: x['minutes'])
    debug_print(f"  Cheap periods found (<= {cheap_threshold:.2f}p/kWh): {len(cheap_periods)}")
    
    if config.DEBUG and cheap_periods:
        debug_print("  Cheap periods:", indent=1)
        for p in cheap_periods[:20]:  # Show first 20
            debug_print(f"    {p['time']}: {p['rate']:.2f}p/kWh", indent=1)
        if len(cheap_periods) > 20:
            debug_print(f"    ... and {len(cheap_periods) - 20} more", indent=1)
    
    # Decision logic:
    # - If multiple cheap periods on Agile, choose Agile
    # - If one cheap period and it's cheaper than Go, choose Agile
    # - Otherwise, choose Go
    
    best_tariff = 'go'  # Default
    reasoning_parts = []
    reasoning_parts.append(f"Go: Overnight rate {go_overnight_rate:.2f}p/kWh")
    
    if len(cheap_periods) > 1:
        # Multiple cheap periods - choose Agile
        best_tariff = 'agile'
        avg_cheap_rate = sum(p['rate'] for p in cheap_periods) / len(cheap_periods)
        reasoning_parts.append(f"Agile: {len(cheap_periods)} cheap periods (<= {cheap_threshold:.2f}p/kWh), avg: {avg_cheap_rate:.2f}p/kWh")
        reasoning_parts.append(f"Decision: Agile (multiple cheap periods available)")
    elif len(cheap_periods) == 1:
        # One cheap period - compare with Go
        cheap_rate = cheap_periods[0]['rate']
        if cheap_rate < go_overnight_rate:
            best_tariff = 'agile'
            reasoning_parts.append(f"Agile: 1 cheap period at {cheap_rate:.2f}p/kWh (cheaper than Go)")
            reasoning_parts.append(f"Decision: Agile (cheaper than Go)")
        else:
            best_tariff = 'go'
            reasoning_parts.append(f"Agile: 1 cheap period at {cheap_rate:.2f}p/kWh (more expensive than Go)")
            reasoning_parts.append(f"Decision: Go (single Agile period more expensive)")
    else:
        # No cheap periods
        best_tariff = 'go'
        min_agile_rate = min(float(r.get('value_inc_vat', 999)) for r in agile_rates) if agile_rates else 999
        reasoning_parts.append(f"Agile: No cheap periods (minimum: {min_agile_rate:.2f}p/kWh)")
        reasoning_parts.append(f"Decision: Go (no cheap Agile periods)")
    
    reasoning = "\n".join(reasoning_parts)
    
    debug_print(f"\n=== Comparison Result ===")
    debug_print(f"Best tariff: {best_tariff.upper()}")
    debug_print(f"Cheap Agile periods: {len(cheap_periods)}")
    
    return {
        'best_tariff': best_tariff,
        'reasoning': reasoning,
        'agile_cheap_periods': len(cheap_periods),
        'go_overnight_rate': go_overnight_rate,
        'cheap_threshold': cheap_threshold,
        'cheap_periods': cheap_periods
    }




