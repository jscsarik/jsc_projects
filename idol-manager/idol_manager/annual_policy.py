"""Draft decisions use published DTOs only. No database or secret input."""
import json
from .market_rules import raised_offer
from .finance_policy import RESERVE_WEEKS


def style_for(root,agency):
    path=root/'config/annual_draft.json'
    settings=json.loads(path.read_text(encoding='utf8')) if path.is_file() else {}
    style=settings.get('agency_styles',{}).get(agency,settings.get('default_style','balanced'))
    if style not in RESERVE_WEEKS:raise ValueError('통합 드래프트 AI 성향은 stable/balanced/aggressive 중 하나여야 합니다.')
    return style


def choose(candidates,own,style='balanced'):
    def score(p):
        # Ranges are projected by the shared public DTO; hidden CA isn't here.
        skills=p['skills'];strength=sum(sorted(skills,reverse=True)[:3])/3
        own_pro=[x for x in own if x['career_status'] in ('first_team','second_team','pro_pending')]
        coverage=sum(max(0,skills[i]-max((x['skills'][i] for x in own_pro),default=0)) for i in range(8))/8
        youth=p['age']<=16;need=len(own_pro)<16
        preference=(4 if youth else 0) if style=='stable' else (4 if not youth and need else 0) if style=='aggressive' else 0
        return p['average']+.15*strength+.2*coverage+preference
    return min(candidates,key=lambda p:(-score(p),p['age'],p['id']))


def offer_amount(person,offers,style):
    # Same market salary / acceptance function as the player; no success bonus.
    baseline=person['market'] or 30000000
    if offers:return raised_offer(offers[-1]['annual'])
    return max(10000,round(baseline*({'stable':.95,'balanced':1.0,'aggressive':1.05}[style])/10000)*10000)
