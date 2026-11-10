"""Recruitment scoring uses only explicit public candidate/roster projections."""
from .recruitment_philosophy import FIELDS

# Pure evaluation weights, no ability/contract/lottery bonuses.
WEIGHTS={'early':(.9,.07,.35),'middle':(.60,.30,1.0),'annual':(.35,.45,1.8),'trainee':(.25,.55,2.0)}

def public_view(p):
    known=p.get('exact') or (p.get('ranges') and all(p['ranges']))
    return dict(id=p['id'],age=p['age'],skills=list(p['skills']) if known else None)

def quality(p):
    s=p['skills']
    return .8*sum(s)/8+.2*sum(sorted(s,reverse=True)[:3])/3 if s else 0

def fit(p,identity):
    s=p['skills'];kind=identity['philosophy'];young=max(0,100-(p['age']-14)*5)
    if not s:return young*.35 if kind=='development' else young*.08
    if kind=='balanced':return .65*sum(s)/8+.35*min(s)
    if kind=='development':return .7*quality(p)+.3*young
    values=[s[i] for i in FIELDS[identity['field']]]
    return .6*sum(values)/len(values)+.4*min(values)

def coverage_gain(p,own):
    s=p['skills'];known=[x['skills'] for x in own if x.get('skills')]
    if not s or not known:return 0
    # Top-two coverage preserves specialists instead of flattening the roster.
    before=[sum(sorted((v[i] for v in known),reverse=True)[:2])/2 for i in range(8)]
    after=[sum(sorted([s[i]]+[v[i] for v in known],reverse=True)[:2])/2 for i in range(8)]
    gain=sum((b-a)*(1+(max(before)-a)/100) for a,b in zip(before,after))/8
    # Content combinations reward filling a whole usable role, not one stat.
    for group in FIELDS.values():
        old=max(min(v[i] for i in group) for v in known)
        gain+=max(0,min(s[i] for i in group)-old)/len(FIELDS)
    return gain

def decide(candidates,own,identity,*,context='annual',round_number=1):
    candidates=list(candidates)
    if not candidates:raise ValueError('지명 가능한 후보가 없습니다.')
    known=[quality(p) for p in candidates if p.get('skills')]
    floor=max(known,default=0)-(7 if context=='founding' and round_number<=3 else 14 if context=='founding' and round_number<=6 else 18)
    legal=[p for p in candidates if not p.get('skills') or quality(p)>=floor]
    def best(score):return min(legal,key=lambda p:(-score(p),p['age'],p['id']))
    if context=='founding' and round_number>=7:
        philosophy=best(lambda p:.35*quality(p)+.65*fit(p,identity))
        supplement=best(lambda p:.65*quality(p)+1.8*coverage_gain(p,own))
        baseline=sum(fit(p,identity) for p in own)/len(own) if own else 0
        benefit=max(0,fit(philosophy,identity)-baseline)
        if coverage_gain(supplement,own)*1.5>benefit:
            return supplement,'coverage'
        return philosophy,'philosophy'
    key='early' if context=='founding' and round_number<=3 else 'middle' if context=='founding' else context
    q,f,c=WEIGHTS[key]
    if key=='middle':f+=(round_number-4)*.05
    return best(lambda p:q*quality(p)+f*fit(p,identity)+c*coverage_gain(p,own)),key

def applications(candidates,own,identity):
    remaining=list(candidates);own=list(own);chosen=[]
    for _ in range(min(2,len(remaining))):
        person,_=decide(remaining,own,identity,context='trainee')
        chosen.append(person['id']);own.append(person);remaining=[p for p in remaining if p['id']!=person['id']]
    return tuple(chosen)
