from datetime import date, timedelta

from dateutil.relativedelta import FR, MO, SA, SU, TH, TU, WE, relativedelta
from dateutil.relativedelta import weekday as Weekday

WEEKDAYS: dict[str, Weekday] = {
    "mon": MO,
    "tue": TU,
    "wed": WE,
    "thu": TH,
    "fri": FR,
    "sat": SA,
    "sun": SU,
}


def next_occurrence(due_date: str, recurrence_rule: str) -> date:
    base: date = date.fromisoformat(due_date)
    rule: str = recurrence_rule.strip().lower()
    if rule == "daily":
        return base + timedelta(days=1)
    if rule.startswith("weekly:"):
        token: str = rule.split(":", 1)[1]
        if token not in WEEKDAYS:
            raise ValueError(f"unsupported weekday in recurrence_rule: {recurrence_rule}")
        return (base + timedelta(days=1)) + relativedelta(weekday=WEEKDAYS[token](+1))
    if rule.startswith("monthly:"):
        day_of_month: int = int(rule.split(":", 1)[1])
        return base + relativedelta(months=1, day=day_of_month)
    raise ValueError(f"unsupported recurrence_rule: {recurrence_rule}")
