"""A/B closure guards execute inside the domain command transaction."""


class ClosureRegistry:
    def __init__(self, guards=()):
        self._guards = list(guards)

    def register(self, guard):
        if guard in self._guards:
            raise ValueError("Closure guard already registered")
        self._guards.append(guard)

    def check_closure(self, db, actor, case_id):
        blockers = []
        for guard in self._guards:
            blockers.extend(guard(db, actor, case_id))
        return blockers
