#!/usr/bin/env python3
"""Test timezone conversion for occurrence times.

This verifies that occurrence times (seconds from midnight in server local
timezone) are correctly converted to UTC.
"""

import sys
from datetime import UTC, datetime
from zoneinfo import ZoneInfo

sys.path.insert(0, '/home/user/py-webdav')

from py_webdav.inform_api_client import InformConfig
from py_webdav.caldav import InformCalDAVBackend


def test_timezone_conversion():
    """Test occurrence time to UTC conversion."""
    print("=" * 80)
    print("TEST: Timezone Conversion for Occurrence Times")
    print("=" * 80)

    # Create config with Europe/Berlin timezone
    config = InformConfig(server_timezone="Europe/Berlin")
    backend = InformCalDAVBackend(owner_key="INFO", debug=False)
    backend.api_client.config.server_timezone = "Europe/Berlin"

    print(f"\nServer timezone: {config.server_timezone}")

    # Test Case 1: Winter time (CET = UTC+1)
    # January 10, 2026 16:00 local = 15:00 UTC
    print("\n" + "-" * 60)
    print("Test Case 1: Winter (CET = UTC+1)")
    print("-" * 60)

    date_str = "2026-01-10"
    seconds = 57600.0  # 16:00 in local time

    result = backend._occurrence_time_to_utc(date_str, seconds)

    print(f"Input: {date_str} + {seconds}s ({seconds/3600:.0f}:00 local)")
    print(f"Expected UTC: 15:00 (16:00 - 1 hour)")
    print(f"Actual UTC: {result.strftime('%H:%M')}")
    print(f"Full result: {result.isoformat()}")

    assert result.hour == 15, f"Expected 15:00 UTC, got {result.hour}:00"
    assert result.tzinfo == UTC, "Result should be in UTC"
    print("✅ PASS: Winter time conversion correct")

    # Test Case 2: Summer time (CEST = UTC+2)
    # July 10, 2026 16:00 local = 14:00 UTC
    print("\n" + "-" * 60)
    print("Test Case 2: Summer (CEST = UTC+2)")
    print("-" * 60)

    date_str = "2026-07-10"
    seconds = 57600.0  # 16:00 in local time

    result = backend._occurrence_time_to_utc(date_str, seconds)

    print(f"Input: {date_str} + {seconds}s ({seconds/3600:.0f}:00 local)")
    print(f"Expected UTC: 14:00 (16:00 - 2 hours)")
    print(f"Actual UTC: {result.strftime('%H:%M')}")
    print(f"Full result: {result.isoformat()}")

    assert result.hour == 14, f"Expected 14:00 UTC, got {result.hour}:00"
    assert result.tzinfo == UTC, "Result should be in UTC"
    print("✅ PASS: Summer time conversion correct")

    # Test Case 3: Edge case - midnight
    print("\n" + "-" * 60)
    print("Test Case 3: Midnight (0:00 local)")
    print("-" * 60)

    date_str = "2026-01-10"
    seconds = 0.0  # 00:00 local

    result = backend._occurrence_time_to_utc(date_str, seconds)

    print(f"Input: {date_str} + {seconds}s (00:00 local)")
    print(f"Expected UTC: 23:00 previous day (00:00 - 1 hour)")
    print(f"Actual UTC: {result.isoformat()}")

    # In winter (CET), 00:00 local = 23:00 previous day UTC
    assert result.hour == 23, f"Expected 23:00 UTC, got {result.hour}:00"
    assert result.day == 9, f"Expected day 9, got {result.day}"
    print("✅ PASS: Midnight conversion correct (crosses day boundary)")

    # Test Case 4: End of day
    print("\n" + "-" * 60)
    print("Test Case 4: End of day (23:59 local)")
    print("-" * 60)

    date_str = "2026-01-10"
    seconds = 86340.0  # 23:59 local

    result = backend._occurrence_time_to_utc(date_str, seconds)

    print(f"Input: {date_str} + {seconds}s (23:59 local)")
    print(f"Expected UTC: 22:59 (23:59 - 1 hour)")
    print(f"Actual UTC: {result.isoformat()}")

    assert result.hour == 22, f"Expected 22:00 UTC, got {result.hour}:00"
    assert result.minute == 59, f"Expected :59, got :{result.minute}"
    print("✅ PASS: End of day conversion correct")

    print("\n" + "=" * 80)
    print("✅ ALL TESTS PASSED")
    print("=" * 80)


if __name__ == "__main__":
    test_timezone_conversion()
