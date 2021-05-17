from __future__ import annotations

from contextlib import (
    AsyncExitStack,
    ExitStack,
    asynccontextmanager,
    contextmanager,
)
from dataclasses import dataclass
from typing import (
    Any,
    AsyncContextManager,
    AsyncIterator,
    Awaitable,
    Callable,
    ContextManager,
    Generic,
    Iterator,
    Mapping,
    Protocol,
    Type,
    TypeVar,
    Union,
    cast,
)

from dependency_injection.types_match import (
    TypesMatcher,
    is_type_acceptable_in_place_of,
)
from dependency_injection.utils import EagerValueAwaitable

T = TypeVar('T', covariant=True)

AnySyncFactory = Union[
    Callable[..., T],
    Callable[..., ContextManager[T]],
]
AnyAsyncFactory = Union[
    AnySyncFactory[T],
    Callable[..., Awaitable[T]],
    Callable[..., AsyncContextManager[T]],
]

#: `Eager` is antonym to `Awaitable`
Eager = Union[T]
#: AF - is shortcut for "Allowed Factories", one of
#: `AnySyncFactory` or `AnyFactory`
AF = TypeVar('AF', bound=Callable)
#: VW - is shortcut for "Value Wrapper", one of `Eager` or `Awaitable`
VW = TypeVar('VW')
#: GT - is shortcut for "Guard Type"
GT = TypeVar('GT', ContextManager, AsyncContextManager)


@dataclass(frozen=True, unsafe_hash=True)
class BaseDependency(Generic[T, AF]):
    name: str
    provides_type: Type[T]
    requires: Mapping[str, tuple[str, Type]]
    factory: AF[T]
    context_manager: bool = False
    async_: bool = False


Dependency = BaseDependency[T, AnySyncFactory]
AsyncDependency = BaseDependency[T, AnyAsyncFactory]


DT = TypeVar('DT', bound=BaseDependency)


class BaseContainer(Protocol[DT]):
    provides: Mapping[str, DT]
    types_matcher: TypesMatcher


Container = BaseContainer[Dependency]
AsyncContainer = BaseContainer[AsyncDependency]


@dataclass(frozen=True)
class BaseImmutableContainer(Generic[DT]):
    provides: Mapping[str, DT]
    types_matcher: TypesMatcher = is_type_acceptable_in_place_of


ImmutableContainer = BaseImmutableContainer[Dependency]
AsyncImmutableContainer = BaseImmutableContainer[AsyncDependency]


class _HasEnterContextManagerMethod(Protocol):
    def enter_context(self, cm: ContextManager[T]) -> T:
        raise NotImplementedError


class _HasEnterAsyncContextManager(_HasEnterContextManagerMethod, Protocol):
    def enter_async_context(self, cm: AsyncContextManager[T]) -> Awaitable[T]:
        raise NotImplementedError


class BaseResolver(Generic[VW, DT, GT]):
    guard: GT
    finalizers_stack: _HasEnterContextManagerMethod

    def __init__(self, container: BaseContainer[DT]):
        self._container = container
        self._resolved: dict[str, VW] = {}

    def resolve(self, look_name: str, look_type: Type[T]) -> VW[T]:
        dep = self._lookup_dep(look_name, look_type)
        try:
            return self._resolve_cached(dep)
        except LookupError:
            pass

        # TODO check for cyclic dependencies
        dep_args = {
            arg_name: self.resolve(sub_dep_name, sub_dep_type)
            for arg_name, (sub_dep_name, sub_dep_type) in dep.requires.items()
        }
        return self._create(dep, **dep_args)

    def _lookup_dep(self, look_name: str, look_type: Type[T]) -> DT[T]:
        not_found = look_name not in self._container.provides
        if not_found:
            raise LookupError(
                f'Dependency `{look_name}: {look_type}` not found'
            )

        maybe_dep = self._container.provides[look_name]
        if not self._container.types_matcher(
            maybe_dep.provides_type, look_type
        ):
            raise LookupError(
                f"Requested dependency `{look_name}: {look_type}` doesn't "
                f'matches provided type {maybe_dep.provides_type}'
            )
        dep: DT[T] = maybe_dep
        return dep

    def _resolve_cached(self, dep: DT[T]) -> VW[T]:
        memoized_value: VW[T] = self._resolved[dep.name]
        return memoized_value

    def _create(self, dep: DT[T], **dep_args: VW) -> VW[T]:
        raise NotImplementedError


def _create_sync_dependency(
    resolver: BaseResolver[Any, Any, Any],
    dep: Dependency[T],
    **dep_args: Any,
) -> T:
    value: Union[T, ContextManager[T]] = dep.factory(**dep_args)
    if not dep.context_manager:
        return cast(T, value)

    if not isinstance(value, ContextManager):
        raise TypeError(
            f'Dependency {dep.name} expected to be context manager, '
            f'but factory returned {value}'
        )
    return resolver.finalizers_stack.enter_context(value)


class Resolver(BaseResolver[Eager, Dependency, ContextManager[None]]):
    def __init__(self, container: Container):
        super().__init__(container)
        self.guard = self.finalizers_stack = ExitStack()

    def _create(self, dep: Dependency[T], **dep_args: Any) -> Eager[T]:
        created = _create_sync_dependency(self, dep, **dep_args)
        self._resolved[dep.name] = created
        return created


class AsyncResolver(
    BaseResolver[Awaitable, AsyncDependency, AsyncContextManager[None]]
):
    finalizers_stack: _HasEnterAsyncContextManager

    def __init__(self, container: AsyncContainer):
        super().__init__(container)
        self.guard = self.finalizers_stack = AsyncExitStack()

    def _create(
        self, dep: AsyncDependency[T], **dep_args: Awaitable
    ) -> Awaitable[T]:
        async def create_inner():
            ready_sub_deps = {
                sub_dep_name: await sub_dep_awaitable
                for sub_dep_name, sub_dep_awaitable in dep_args.items()
            }

            if not dep.async_:
                ready_value = _create_sync_dependency(
                    self, dep, **ready_sub_deps
                )
                self._resolved[dep.name] = EagerValueAwaitable(ready_value)
                return ready_value

            value: Union[
                Awaitable[T],
                AsyncContextManager[T],
            ] = dep.factory(**ready_sub_deps)

            if dep.context_manager:
                if not isinstance(value, AsyncContextManager):
                    raise TypeError(
                        f'Dependency {dep} marked as '
                        '`async_` and `context_manager` have to return '
                        '`AsyncContextManager` from it factory'
                    )
                ready_value = await self.finalizers_stack.enter_async_context(
                    value
                )
            else:
                ready_value = await value

            self._resolved[dep.name] = EagerValueAwaitable(ready_value)
            return ready_value

        return create_inner()


@contextmanager
def resolver_scope(container: Container) -> Iterator[Resolver]:
    resolver = Resolver(container)
    with resolver.guard:
        yield resolver


@asynccontextmanager
async def async_resolver_scope(
    container: AsyncContainer,
) -> AsyncIterator[AsyncResolver]:
    resolver = AsyncResolver(container)
    async with resolver.guard:
        yield resolver
