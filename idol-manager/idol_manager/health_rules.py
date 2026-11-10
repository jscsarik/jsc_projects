"""Permanent health is separate from all eight CA/PA abilities."""
MAX_HEALTH = 90


def cap_health(value):
    return max(0, min(MAX_HEALTH, value))


def health_after_age(value, age_increase):
    # Only the actual forward age change, never the person's existing age.
    return max(0, cap_health(value) - max(0, age_increase))


V15_STATEMENTS = (
    # No age/history backfill. Keep parent tables and all existing references.
    'UPDATE idols SET health=90 WHERE health>90',
    """CREATE TRIGGER health_range_insert BEFORE INSERT ON idols
       WHEN typeof(NEW.health)!='integer' OR NEW.health NOT BETWEEN 0 AND 90
       BEGIN SELECT RAISE(ABORT,'Health must be an integer between 0 and 90'); END""",
    """CREATE TRIGGER health_range_update BEFORE UPDATE OF health ON idols
       WHEN typeof(NEW.health)!='integer' OR NEW.health NOT BETWEEN 0 AND 90
       BEGIN SELECT RAISE(ABORT,'Health must be an integer between 0 and 90'); END""",
)
