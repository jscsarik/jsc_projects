"""AI sees public identity/age/photos only. No CA, PA or secret prospect flag."""
def choose_applications(candidates,rng):
    return tuple(p.id for p in rng.sample(list(candidates),min(2,len(candidates))))
