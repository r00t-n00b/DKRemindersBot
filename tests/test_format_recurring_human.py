def test_format_recurring_human_daily(main_module):
    assert main_module.format_recurring_human("daily", {}) == "daily"

def test_format_recurring_human_weekly(main_module):
    assert main_module.format_recurring_human("weekly", {"weekday": 0}) == "weekly (Mon)"

def test_format_recurring_human_weekdays(main_module):
    assert main_module.format_recurring_human("weekly_multi", {"days": [0,1,2,3,4]}) == "weekdays"

def test_format_recurring_human_weekends(main_module):
    assert main_module.format_recurring_human("weekly_multi", {"days": [5,6]}) == "weekends"

def test_format_recurring_human_monthly(main_module):
    assert main_module.format_recurring_human("monthly", {"day": 15}) == "monthly (day 15)"

def test_format_recurring_human_yearly(main_module):
    assert main_module.format_recurring_human("yearly", {"month": 12, "day": 25}) == "yearly (Dec 25)"