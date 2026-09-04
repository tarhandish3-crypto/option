#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Test filter simple"""

import math

def _safe_float(value):
    try:
        if isinstance(value, (int, float)):
            return float(value)
        if isinstance(value, str):
            clean_str = str(value).strip().replace('%', '').replace(',', '').strip()
            if not clean_str:
                return float('nan')
            return float(clean_str)
        return float(value)
    except (ValueError, TypeError, AttributeError):
        return float('nan')

# Test
test_values = ["-45.5", "-1", "0", "1.5", "-50"]
value_threshold = -1

filter_func = lambda x, v=value_threshold: not math.isnan(_safe_float(x)) and _safe_float(x) < v

print(f"Testing filter 'less than {value_threshold}':")
for val in test_values:
    result = filter_func(val)
    float_val = _safe_float(val)
    expected = float_val < value_threshold and not math.isnan(float_val)
    status = "OK" if result == expected else "FAIL"
    print(f"  {val:>6} -> {result:5} (expected {expected:5}) [{status}]")
