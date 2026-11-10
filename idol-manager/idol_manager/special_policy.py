"""Public-current-values-only special-event selection, including squad priority."""
from .config import SKILLS


def select_special(players,required,main,conditions,leaders,base_attempts):
    def rank(item):
        p,squad=item;factor=1-conditions[p.id].penalty
        support=tuple(s for s in SKILLS if s not in main);half=base_attempts/2
        expected=(half*sum(p.value(s) for s in main)/len(main)
                  +half*sum(p.value(s) for s in support)/len(support)
                  +leaders.get(p.id,0)*p.value('leadership'))/100*factor
        return (-expected,-p.health,p.id)
    first=sorted((x for x in players if x[1]=='first_team'),key=rank)
    second=sorted((x for x in players if x[1]=='second_team'),key=rank)
    return tuple(p for p,_ in (first+second)[:required])
