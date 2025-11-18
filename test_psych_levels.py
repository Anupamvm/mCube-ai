#!/usr/bin/env python
"""Test psychological level detection for specific strikes"""

import os
import django

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from apps.strategies.services.psychological_levels import check_psychological_levels

# Test cases from user feedback
test_cases = [
    (27000, 24900, 25958.45, "CE 27000, PE 24900"),
    (27000, 24800, 25958.45, "CE 27000, PE 24800"),
    (25500, 24500, 25000.00, "CE 25500, PE 24500"),
]

print("=" * 80)
print("PSYCHOLOGICAL LEVEL DETECTION TEST")
print("=" * 80)

for call_strike, put_strike, spot_price, description in test_cases:
    print(f"\n{description} (Spot: {spot_price})")
    print("-" * 80)

    result = check_psychological_levels(call_strike, put_strike, spot_price)

    print(f"Original Call: {result['original_call']}")
    print(f"Adjusted Call: {result['adjusted_call']}")
    print(f"Adjustment:    {result['adjusted_call'] - result['original_call']:+d} points")

    print(f"\nOriginal Put:  {result['original_put']}")
    print(f"Adjusted Put:  {result['adjusted_put']}")
    print(f"Adjustment:    {result['adjusted_put'] - result['original_put']:+d} points")

    print(f"\nAny Adjustments: {result['any_adjustments']}")
    if result['any_adjustments']:
        print(f"Adjustments Made: {', '.join(result['adjustments_made'])}")

    print(f"Safety Verdict: {result['safety_verdict']}")

    # Show call analysis details
    if result['call_analysis']['should_adjust']:
        print(f"\nCall Analysis:")
        rec = result['call_analysis']['recommendation']
        print(f"  - Reason: {rec['reason']}")
        print(f"  - Critical Level: {rec['critical_level']} ({rec['level_type']})")
        print(f"  - Direction: {rec['direction']}")

    # Show put analysis details
    if result['put_analysis']['should_adjust']:
        print(f"\nPut Analysis:")
        rec = result['put_analysis']['recommendation']
        print(f"  - Reason: {rec['reason']}")
        print(f"  - Critical Level: {rec['critical_level']} ({rec['level_type']})")
        print(f"  - Direction: {rec['direction']}")

print("\n" + "=" * 80)
print("TEST COMPLETE")
print("=" * 80)
