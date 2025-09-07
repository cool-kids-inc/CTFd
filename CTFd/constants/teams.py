from dataclasses import dataclass, fields
from typing import Any


@dataclass(frozen=True)
class TeamAttrs:
    id: Any = None
    oauth_id: Any = None
    name: Any = None
    email: Any = None
    secret: Any = None
    website: Any = None
    affiliation: Any = None
    country: Any = None
    bracket_id: Any = None
    hidden: Any = None
    banned: Any = None
    captain_id: Any = None
    created: Any = None


TeamAttrsFields = [f.name for f in fields(TeamAttrs)]


class _TeamAttrsWrapper:
    def __getattr__(self, attr):
        from CTFd.utils.user import get_current_team_attrs

        attrs = get_current_team_attrs()
        return getattr(attrs, attr, None)

    @property
    def place(self):
        from CTFd.utils.user import get_team_place

        return get_team_place(team_id=self.id)

    @property
    def score(self):
        from CTFd.utils.user import get_team_score

        return get_team_score(team_id=self.id)


Team = _TeamAttrsWrapper()
