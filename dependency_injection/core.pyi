from typing import (
    Any,
    AsyncContextManager,
    Awaitable,
    Callable,
    ContextManager,
    Literal,
    Mapping,
    Protocol,
    Tuple,
    Type,
    TypeVar,
    Union,
)

from dependency_injection.types_match import TypesMatcher

T = TypeVar('T', covariant=True)

AnySyncFactory = Union[
    Callable[..., T],
    Callable[..., ContextManager[T]],
]
AnyFactory = Union[
    AnySyncFactory[T],
    Callable[..., Awaitable[T]],
    Callable[..., AsyncContextManager[T]],
    Callable[..., Awaitable[AsyncContextManager[T]]],
]

class SyncDependency(Protocol[T]):
    def __init__(
        self,
        name: str,
        provides_type: Type[T],
        requires: Mapping[str, Tuple[str, Type]],
        factory: AnySyncFactory[T],
        context_manager: bool = False,
        async_: Literal[False] = False,
    ): ...
    @property
    def name(self) -> str: ...
    @property
    def provides_type(self) -> Type[T]: ...
    @property
    def requires(self) -> Mapping[str, Tuple[str, Type]]: ...
    @property
    def factory(self) -> AnySyncFactory[T]: ...
    @property
    def context_manager(self) -> bool: ...
    @property
    def async_(self) -> Literal[False]: ...

class Dependency(Protocol[T]):
    def __init__(
        self,
        name: str,
        provides_type: Type[T],
        requires: Mapping[str, Tuple[str, Type]],
        factory: AnyFactory[T],
        context_manager: bool = False,
        async_: bool = False,
    ): ...
    @property
    def name(self) -> str: ...
    @property
    def provides_type(self) -> Type[T]: ...
    @property
    def requires(self) -> Mapping[str, Tuple[str, Type]]: ...
    @property
    def factory(self) -> AnyFactory[T]: ...
    @property
    def context_manager(self) -> bool: ...
    @property
    def async_(self) -> bool: ...

class SyncContainer(Protocol):
    provides: Mapping[str, SyncDependency[Any]]
    types_matcher: TypesMatcher

class Container(Protocol):
    provides: Mapping[str, Dependency[Any]]
    types_matcher: TypesMatcher

class SyncImmutableContainer(SyncContainer):
    def __init__(
        self,
        provides: Mapping[str, SyncDependency[Any]],
        types_matcher: TypesMatcher = ...,
    ): ...

class ImmutableContainer(Container):
    def __init__(
        self,
        provides: Mapping[str, Dependency[Any]],
        types_matcher: TypesMatcher = ...,
    ): ...

class SyncResolver(Protocol):
    def resolve(self, look_name: str, look_type: Type[T]) -> T: ...

class Resolver(Protocol):
    def resolve(self, look_name: str, look_type: Type[T]) -> Awaitable[T]: ...

def sync_resolver_scope(
    container: SyncContainer,
) -> ContextManager[SyncResolver]: ...
def resolver_scope(container: Container) -> AsyncContextManager[Resolver]: ...
