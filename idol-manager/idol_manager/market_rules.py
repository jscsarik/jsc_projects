"""Public-only market formulas, deterministic trade policy, no UI or PA."""
from fractions import Fraction
from .finance_service import round_10000

def market_salary(values,age):
    if len(values)!=8 or any(type(v) is not int or not 0<=v<=100 for v in values):raise ValueError('공개 능력치 8개가 필요합니다.')
    a=Fraction(sum(values),8);s=Fraction(sum(sorted(values)[-2:]),2)
    y=0 if age<=18 else 200 if age<=22 else -100 if age<=26 else -200
    score=max(Fraction(3000),min(Fraction(6000),3000+60*(a-50)+20*(s-a)+y))
    return int((score+50)//100)*1000000

def acceptance(offered,market):
    if type(offered) is not int or offered<=0 or market<=0:raise ValueError('제안 연봉을 확인해 주세요.')
    ratio=Fraction(offered,market)
    anchors=((Fraction(90,100),Fraction(30,100)),(Fraction(95,100),Fraction(50,100)),(Fraction(1),Fraction(80,100)),(Fraction(105,100),Fraction(90,100)),(Fraction(110,100),Fraction(1)))
    if ratio<=anchors[0][0]:return float(anchors[0][1])
    for (left,p),(right,q) in zip(anchors,anchors[1:]):
        if ratio<=right:return float(p+(q-p)*(ratio-left)/(right-left))
    return 1.0

def raised_offer(previous):return round_10000(previous*105,100)
def player_value(p,team_skills):
    skills=p['skills'];average=sum(skills)/8
    health=100 if p['health'] is None else p['health']
    recent=p.get('past_success_rate')
    demonstrated=average if recent is None else .8*average+.2*recent*100
    performance=demonstrated*(.75 if p['injured'] else 1)*(.9+.1*health/100)
    youth=max(0,min(100,100-(p['age']-17)*5+p.get('observed_growth',0)))
    term_bonus=10*(max(1,min(2,p.get('remaining_seasons') or 1))-1)
    contract=max(0,min(100,100-p['annual']/1000000+term_bonus))
    fit=sum(v*(100-team_skills[i]) for i,v in enumerate(skills))/max(1,sum(100-v for v in team_skills))
    return .50*performance+.15*youth+.20*contract+.15*fit

def trade_response(ratio,*,salary_relief=False,need=False,round_number=1):
    # No unconfirmed probability tables or hidden outcome boosts.
    if ratio>=1.10:return 'accept'
    if ratio>=1:return 'accept' if round_number>=3 else 'counter'
    if ratio>=.90 and salary_relief and need:return 'counter' if round_number<3 else 'accept'
    return 'reject'
