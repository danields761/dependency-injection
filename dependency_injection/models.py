from __future__ import annotations

from dataclasses import dataclass
from typing import (
    Optional,
    Generic,
    Type,
    Mapping,
    TypeVar,
    Union,
    Callable,
    Awaitable,
    ContextManager,
    AsyncContextManager,
)


T = TypeVar('T')

AnyFactory = Union[
    Callable[..., T],
    Callable[..., Awaitable[T]],
    Callable[..., ContextManager[T]],
    Callable[..., AsyncContextManager[T]],
]


@dataclass(frozen=True, unsafe_hash=True)
class Scope:
    name: str
    parent: Optional[Scope] = None

    def is_outer_for(self, scope: Scope) -> bool:
        curr: Optional[Scope] = scope
        while curr and (curr := curr.parent):
            if curr == self:
                return True
        return False

    def is_child_of(self, scope: Scope) -> bool:
        return scope.parent == self


class Dependency(Generic[T]):
    name: str
    requires_type: Type[T]
    depends_on: Mapping[str, Dependency]
    factory: AnyFactory[T]
