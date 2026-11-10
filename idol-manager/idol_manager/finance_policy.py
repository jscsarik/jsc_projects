"""Public cash-only budget policy. No player ability, PA or RNG input."""
RESERVE_WEEKS={'stable':4,'balanced':2,'aggressive':1}
def discretionary_budget(cash,debt,next_payroll,weekly_cost,style='balanced'):
    if debt:return 0
    reserve=RESERVE_WEEKS.get(style,2)*weekly_cost+next_payroll
    return max(0,cash-reserve)
