from typing import (
    Any,
    AsyncContextManager,
    Awaitable,
    Callable,
    ContextManager,
    Generic,
    Hashable,
    Literal,
    Mapping,
    Protocol,
    Sequence,
    Tuple,
    Type,
    TypeVar,
    Union,
    overload,
)

from dependency_injection.types_match import TypesMatcher

T = TypeVar('T', covariant=True)
ST = TypeVar('ST', bound=Hashable)

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

class ScopedContainers(Generic[ST]):
    def __init__(
        self, scopes_order: Sequence[ST], scopes: Mapping[ST, Container]
    ): ...
    def scopes_order(self) -> Sequence[ST]: ...
    def scopes(self) -> Mapping[ST, Container]: ...

class ScopedAsyncContainers(Generic[ST]):
    def __init__(
        self, scopes_order: Sequence[ST], scopes: Mapping[ST, AsyncContainer]
    ): ...
    def scopes_order(self) -> Sequence[ST]: ...
    def scopes(self) -> Mapping[ST, AsyncContainer]: ...

class Resolver(Protocol):
    def resolve(self, look_name: str, look_type: Type[T]) -> T: ...

class AsyncResolver(Protocol):
    async def resolve(self, look_name: str, look_type: Type[T]) -> T: ...

class ScopedResolver(Resolver, Protocol[ST]):
    @overload
    def next_scope(self) -> ContextManager[ScopedResolver[ST]]: ...
    @overload
    def next_scope(self, scope: ST) -> ContextManager[ScopedResolver[ST]]: ...
    @property
    def scope(self) -> ST: ...

class ScopedAsyncResolver(AsyncResolver, Protocol[ST]):
    @overload
    def next_scope(self) -> AsyncContextManager[ScopedAsyncResolver]: ...
    @overload
    def next_scope(
        self, scope: ST
    ) -> AsyncContextManager[ScopedAsyncResolver]: ...
    @property
    def scope(self) -> ST: ...

def create_resolver(
    container: Container,
) -> ContextManager[Resolver]: ...
def create_scoped_resolver(
    scoped_containers: ScopedContainers[ST],
) -> ContextManager[ScopedResolver[ST]]: ...
def create_async_resolver(
    container: AsyncContainer,
) -> AsyncContextManager[AsyncResolver]: ...
def create_scoped_async_resolver(
    scoped_containers: ScopedAsyncContainers[ST],
) -> AsyncContextManager[ScopedAsyncResolver[ST]]: ...
