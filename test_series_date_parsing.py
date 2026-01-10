#!/usr/bin/env python3
"""Test series start date parsing."""

from datetime import datetime, UTC

# Simulate what INFORM API returns
series_start_date_str = "2026-01-10"
occ_start_time = 32400  # 9:00 AM in seconds

print(f"Input: seriesStartDate='{series_start_date_str}', occurrenceStartTime={occ_start_time}")

# Current code approach
try:
    series_start_date = datetime.fromisoformat(series_start_date_str)
    print(f"\n1. datetime.fromisoformat() result: {series_start_date}")
    print(f"   Type: {type(series_start_date)}")
    print(f"   Has tzinfo: {series_start_date.tzinfo}")

    hours = int(occ_start_time // 3600)
    minutes = int((occ_start_time % 3600) // 60)
    print(f"\n2. Calculated time: {hours:02d}:{minutes:02d}")

    start_dt = series_start_date.replace(hour=hours, minute=minutes, tzinfo=UTC)
    print(f"\n3. Final datetime: {start_dt}")
    print(f"   ISO format: {start_dt.isoformat()}")

except Exception as e:
    print(f"\nERROR with current approach: {e}")
    import traceback
    traceback.print_exc()

# Better approach
print("\n" + "=" * 60)
print("BETTER APPROACH:")
print("=" * 60)

from datetime import date

# Parse as date, then combine with time
series_date = date.fromisoformat(series_start_date_str)
print(f"\n1. date.fromisoformat() result: {series_date}")

hours = int(occ_start_time // 3600)
minutes = int((occ_start_time % 3600) // 60)

# Create datetime with time and timezone
start_dt = datetime.combine(series_date, datetime.min.time()).replace(
    hour=hours, minute=minutes, tzinfo=UTC
)
print(f"\n2. Final datetime: {start_dt}")
print(f"   ISO format: {start_dt.isoformat()}")
