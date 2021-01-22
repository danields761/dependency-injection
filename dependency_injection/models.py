from __future__ import annotations

from dataclasses import dataclass
from typing import (
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
)

T = TypeVar('T')
S = TypeVar('S')
AF = TypeVar('AF', bound=Callable)

AnySyncFactory = Union[Callable[..., T], Callable[..., Awaitable[T]]]
AnyFactory = Union[
    AnySyncFactory,
    Callable[..., ContextManager[T]],
    Callable[..., AsyncContextManager[T]],
    Callable[..., Awaitable[AsyncContextManager[T]]],
]


@dataclass(frozen=True, unsafe_hash=True)
class Dependency(Generic[T, AF, S]):
    scope: S
    name: str
    provides_type: Type[T]
    requires: Mapping[str, Tuple[str, Type]]
    factory: AF[T]
    context_manager: bool = False
    async_factory: bool = False
