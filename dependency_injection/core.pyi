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
AnyAsyncFactory = Union[
    AnySyncFactory[T],
    Callable[..., Awaitable[T]],
    Callable[..., AsyncContextManager[T]],
    Callable[..., Awaitable[AsyncContextManager[T]]],
]

class Dependency(Protocol[T]):
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

class AsyncDependency(Protocol[T]):
    def __init__(
        self,
        name: str,
        provides_type: Type[T],
        requires: Mapping[str, Tuple[str, Type]],
        factory: AnyAsyncFactory[T],
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
    def factory(self) -> AnyAsyncFactory[T]: ...
    @property
    def context_manager(self) -> bool: ...
    @property
    def async_(self) -> bool: ...

class Container(Protocol):
    provides: Mapping[str, Dependency[Any]]
    types_matcher: TypesMatcher

class AsyncContainer(Protocol):
    provides: Mapping[str, AsyncDependency[Any]]
    types_matcher: TypesMatcher

class ImmutableContainer(Container):
    def __init__(
        self,
        provides: Mapping[str, Dependency[Any]],
        types_matcher: TypesMatcher = ...,
    ): ...

class AsyncImmutableContainer(AsyncContainer):
    def __init__(
        self,
        provides: Mapping[str, AsyncDependency[Any]],
        types_matcher: TypesMatcher = ...,
    ): ...

class Resolver(Protocol):
    def resolve(self, look_name: str, look_type: Type[T]) -> T: ...

class AsyncResolver(Protocol):
    def resolve(self, look_name: str, look_type: Type[T]) -> Awaitable[T]: ...

def resolver_scope(
    container: Container,
) -> ContextManager[Resolver]: ...
def async_resolver_scope(
    container: AsyncContainer,
) -> AsyncContextManager[AsyncResolver]: ...
