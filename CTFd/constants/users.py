from dataclasses import dataclass, fields
from typing import Any


@dataclass(frozen=True)
class UserAttrs:
    id: Any = None
    oauth_id: Any = None
    name: Any = None
    email: Any = None
    type: Any = None
    secret: Any = None
    website: Any = None
    affiliation: Any = None
    country: Any = None
    bracket_id: Any = None
    hidden: Any = None
    banned: Any = None
    verified: Any = None
    language: Any = None
    team_id: Any = None
    created: Any = None
    change_password: Any = None


UserAttrsFields = [f.name for f in fields(UserAttrs)]


class _UserAttrsWrapper:
    def __getattr__(self, attr):
        from CTFd.utils.user import get_current_user_attrs

        attrs = get_current_user_attrs()
        return getattr(attrs, attr, None)

    @property
    def place(self):
        from CTFd.utils.user import get_user_place

        return get_user_place(user_id=self.id)

    @property
    def score(self):
        from CTFd.utils.user import get_user_score

        return get_user_score(user_id=self.id)


User = _UserAttrsWrapper()
