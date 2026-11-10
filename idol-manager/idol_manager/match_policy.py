"""Replaceable policies restricted to public first-team data."""
from .config import SKILLS


class NoInjuryAvailability:
    def available(self, player):
        # Additional availability hook; persisted injury flags are checked
        # independently by MatchService. Health alone is not an injury flag.
        return True


class NoMatchEffects:
    def probability(self, player, skill):
        return player.value(skill) / 100


class ExpectedSuccessLineup:
    def select(self, players, required, main_skills, leader_id):
        support = tuple(s for s in SKILLS if s not in main_skills)

        def score(player):
            return (30 * sum(player.value(s) for s in main_skills) / len(main_skills)
                    + 30 * sum(player.value(s) for s in support) / len(support)
                    + (2 * player.value('leadership') if player.id == leader_id else 0))

        return tuple(sorted(players, key=lambda p: (-score(p), -p.health, p.id))[:required])


def choose_representative(players, main_skills, required, leader_id, *, penalties=None):
    if required == 5 and any(p.id == leader_id for p in players):
        return leader_id
    return min(players, key=lambda p: (-sum(p.value(s) for s in main_skills)*(1-(penalties or {}).get(p.id,0)), -p.health, p.id)).id if players else None


def choose_award(identities, rng):
    """Unspecified tie rule: seeded uniform draw among tied IDs, in stable order."""
    return rng.choice(sorted(identities)) if identities else None
