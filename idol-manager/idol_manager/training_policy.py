"""AI training decisions from public CA and roster roles only; no DB access."""
from .config import SKILLS
from .development_rules import second_probabilities

WEIGHTS={'stable':(1.6,.35),'balanced':(1.1,.8),'aggressive':(.7,1.5)}

def priorities(players,style='balanced'):
    if not players:return []
    weak_weight,special_weight=WEIGHTS.get(style,WEIGHTS['balanced'])
    means=[sum(p['skills'][i] for p in players)/len(players) for i in range(8)]
    coverage=[sum(sorted((p['skills'][i] for p in players),reverse=True)[:3])/min(3,len(players)) for i in range(8)]
    result=[]
    for p in players:
        if p['career_status']!='second_team':continue
        average=sum(p['skills'])/8;options=[]
        for i,value in enumerate(p['skills']):
            if value>=100:continue
            need=(100-means[i])/100+(max(coverage)-coverage[i])/100
            specialty=max(0,value-average)/100
            alternatives=sum(q['id']!=p['id'] and q['skills'][i]>=value-3 for q in players)
            rarity=1/(1+alternatives)
            chance=second_probabilities(value)[0]
            # Expected improvement combines weak team coverage, the player's
            # specialty and the scarcity of capable replacements.
            score=chance*(weak_weight*need*(.5+value/100)+special_weight*specialty+rarity*.6)
            options.append((score,rarity,value,-i))
        if options:
            score,_,_value,negative_index=max(options)
            result.append((score,p['id'],SKILLS[-negative_index]))
    return sorted(result,key=lambda x:(-x[0],x[1]))

def choose(players,budget,style='balanced',*,cost=150000):
    return {person:skill for _,person,skill in priorities(players,style)[:max(0,budget//cost)]}
