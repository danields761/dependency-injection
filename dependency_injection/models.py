from __future__ import annotations

from dataclasses import dataclass
from functools import total_ordering
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
    Tuple,
    Any,
)
from uuid import UUID, uuid4

T = TypeVar('T')

AnyFactory = Union[
    Callable[..., T],
    Callable[..., Awaitable[T]],
    Callable[..., ContextManager[T]],
    Callable[..., AsyncContextManager[T]],
]


@dataclass(frozen=True, unsafe_hash=True)
class _Scope:
    idx: int
    name: str
    chain_id: UUID


@total_ordering
class Scope(_Scope):
    def __init__(self, name: str, parent: Optional[Scope] = None):
        super().__init__(
            parent.idx + 1 if parent else 0,
            parent.chain_id if parent else uuid4(),
            name,
        )

    def __eq__(self, other: Any) -> bool:
        if not isinstance(other, Scope):
            return NotImplemented
        return self.chain_id == other.chain_id and self.idx == other.idx

    def __gt__(self, other: Any) -> bool:
        if not isinstance(other, Scope):
            return NotImplemented
        if self.chain_id != other.chain_id:
            raise ValueError('Unrelated chains')
        return other.idx < self.idx


@dataclass(frozen=True, unsafe_hash=True)
class Dependency(Generic[T]):
    name: str
    requires_type: Type[T]
    depends_on: Mapping[str, Tuple[str, Type]]
    factory: AnyFactory[T]
