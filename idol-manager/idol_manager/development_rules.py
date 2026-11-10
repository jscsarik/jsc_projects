"""Pure development math. Potential is internal; no Qt or database access."""
from dataclasses import dataclass
import json
from .config import ROOT,SKILLS

ROLES=('first_team','second_team','trainee')


def load_rules():
    return json.loads((ROOT/'config/development.json').read_text(encoding='utf-8'))


def phase(day):
    return 'regular' if day.is_regular else 'postseason' if day.is_postseason else 'offseason'


def primary_role(counts):
    available=[r for r in ROLES if counts.get(r,0)>0]
    return min(available,key=lambda r:(-counts[r],ROLES.index(r))) if available else None


def gap_chance(values,potentials,rules=None):
    gap=(sum(potentials)-sum(values))/8
    for threshold,chance in (rules or load_rules())['gap_chances']:
        if (gap>=threshold if threshold>=20 else gap>threshold):return chance
    return 0.0

def second_probabilities(value,settings=None):
    settings=settings or load_rules()['weekly_basic']
    up=(100-value)*(3 if value>=90 else settings['second_team_up_multiplier'])/100
    down=((100-value)*2 if value>=90 else value*settings['second_team_down_multiplier'])/100
    return min(1,max(0,up)),min(1,max(0,down))


class Development:
    def __init__(self,values,potentials,rng):
        if len(values)!=8 or len(potentials)!=8 or any(type(v) is not int or type(p) is not int or not 0<=v<=p<=100 for v,p in zip(values,potentials)):
            raise ValueError('현재 능력치와 개별 성장 상한의 저장 상태를 확인해 주세요.')
        self.values=list(values);self.potentials=tuple(potentials);self.rng=rng;self.trials=[]

    def change(self,index,delta,kind):
        before=self.values[index];self.values[index]=max(0,min(self.potentials[index],100,before+delta))
        applied=self.values[index]-before
        self.trials.append(dict(kind=kind,skill=SKILLS[index],requested=delta,applied=applied))
        return applied

    def roll(self,probability,kind,index):
        probability=max(0,min(1,probability));roll=self.rng.random();success=roll<probability
        self.trials.append(dict(kind=kind,skill=SKILLS[index] if index is not None else None,probability=probability,roll=roll,success=success))
        return success

    def ranked(self,values,*,least=False,exclude=()):
        indices=[i for i in range(8) if i not in exclude];self.rng.shuffle(indices)
        return sorted(indices,key=lambda i:values[i],reverse=not least)[:2]

    def first(self,success_counts,attempts,*,appeared,excluded=False,waiting=False,rules=None):
        settings=(rules or load_rules())['weekly_basic']
        if not appeared:
            if not waiting:
                for i in self.rng.sample(range(8),2):self.change(i,-1,'first_no_appearance')
            return
        rises=self.ranked(success_counts)
        falls=self.ranked(attempts,least=True,exclude=rises)
        if not excluded:
            for i,m in zip(rises,settings['first_team_up_multipliers']):
                if self.roll((100-self.values[i])*m/100,'first_up',i):self.change(i,1,'first_up')
        for i,m in zip(falls,settings['first_team_down_multipliers']):
            if self.roll(self.values[i]*m/100,'first_down',i):self.change(i,-1,'first_down')

    def second(self,*,rules=None,focus=None,hinted=False):
        settings=(rules or load_rules())['weekly_basic']
        for i in self.rng.sample(range(8),settings['second_team_skills']):
            value=self.values[i]
            up_probability,down_probability=second_probabilities(value,settings)
            up=self.roll(up_probability,'second_up',i)
            down=self.roll(down_probability,'second_down',i)
            protected=focus==SKILLS[i]
            self.change(i,int(up)-int(down and not protected),'second_net')
            self.trials[-1]['down_prevented']=bool(down and protected)
            self.trials[-1]['focus_protected']=protected
        if focus is not None:
            self.focus_training(focus,rules=rules)

    def focus_training(self,focus,*,rules=None):
        i=SKILLS.index(focus);value=self.values[i]
        probability=second_probabilities(value,(rules or load_rules())['weekly_basic'])[0]
        if self.roll(probability,'focus',i):self.change(i,1,'focus')

    def trainee(self,*,rules=None):
        settings=(rules or load_rules())['weekly_basic']
        for i in self.rng.sample(range(8),settings['trainee_skills']):
            if self.roll((100-self.values[i])*settings['trainee_up_multiplier']/100,'trainee_up',i):self.change(i,1,'trainee_up')

    def additional(self,*,rules=None):
        chance=gap_chance(self.values,self.potentials,rules)
        for _ in range((rules or load_rules())['additional_trials']):
            if self.roll(chance,'additional',None):
                eligible=[i for i in range(8) if self.values[i]<self.potentials[i]]
                if eligible:self.change(self.rng.choice(eligible),1,'additional')

    def aging(self,age,*,rules=None):
        count=next((n for threshold,n in (rules or load_rules())['aging_thresholds'] if age>=threshold),0)
        for i in self.rng.sample(range(8),count):self.change(i,-1,'aging')
