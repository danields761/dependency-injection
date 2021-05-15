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
    Generator,
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

T = TypeVar('T')
#: `Eager` is antonym to `Awaitable`
Eager = Union
#: AF - is shortcut for "Allowed Factories", one of
#: `AnySyncFactory` or `AnyFactory`
AF = TypeVar('AF', bound=Callable)
#: VW - is shortcut for "Value Wrapper", one of `Eager` or `Awaitable`
VW = TypeVar('VW')

AnySyncFactory = Union[
    Callable[..., T],
    Callable[..., ContextManager[T]],
]
AnyFactory = Union[
    AnySyncFactory,
    Callable[..., Awaitable[T]],
    Callable[..., AsyncContextManager[T]],
]


@dataclass(frozen=True, unsafe_hash=True)
class BaseDependency(Generic[T, AF]):
    name: str
    provides_type: Type[T]
    requires: Mapping[str, tuple[str, Type]]
    factory: AF[T]
    context_manager: bool = False
    async_: bool = False


SyncDependency = BaseDependency[T, AnySyncFactory]
Dependency = BaseDependency[T, AnyFactory]


DT = TypeVar('DT', bound=BaseDependency)


class BaseContainer(Protocol[DT]):
    provides: Mapping[str, DT]
    types_matcher: TypesMatcher


SyncContainer = BaseContainer[SyncDependency]
Container = BaseContainer[Dependency]


@dataclass(frozen=True)
class BaseImmutableContainer(Generic[DT]):
    provides: Mapping[str, DT]
    types_matcher: TypesMatcher = is_type_acceptable_in_place_of


SyncImmutableContainer = BaseImmutableContainer[SyncDependency]
ImmutableContainer = BaseImmutableContainer[Dependency]


class BaseResolver(Generic[VW, DT]):
    def __init__(self, container: BaseContainer[DT]):
        self._container = container
        self._resolved: dict[str, Any] = {}
        self._finalizers_stack = ExitStack()

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


class EagerValueAwaitable(Awaitable[T]):
    """
    Always return value without suspending coroutine on
    `await EagerValueAwaitable(...)`.

    It is possible to achieve same functionality via `asyncio.Future` with
    instant `f.set_result(...)`, but this locks us on `asyncio` without
    actual reason.
    """

    def __init__(self, value: T):
        self._value = value

    def __await__(self) -> Generator[Any, None, T]:
        """
        Generator which instantly returns provided value without suspending
        anything.
        """
        # Makes this function generator, but never yields
        if False:
            yield 1
        return self._value


def _create_sync_dependency(
    resolver: BaseResolver[Any, Any], dep: SyncDependency[T], **dep_args: Any
) -> T:
    value: Union[T, ContextManager[T]] = dep.factory(**dep_args)
    if not dep.context_manager:
        return cast(T, value)

    if not isinstance(value, ContextManager):
        raise TypeError(
            f'Dependency {dep.name} expected to be context manager, '
            f'but factory returned {value}'
        )
    return resolver._finalizers_stack.enter_context(value)


class SyncResolver(
    BaseResolver[
        # Ugly because `typing` module prohibits subscribing generics with
        # bare `Union`
        Eager[Any],
        SyncDependency,
    ]
):
    def _create(self, dep: SyncDependency[T], **dep_args: Any) -> Eager[T]:
        created = _create_sync_dependency(self, dep, **dep_args)
        self._resolved[dep.name] = created
        return created


class Resolver(BaseResolver[Awaitable, Dependency]):
    def __init__(self, container: Container):
        super().__init__(container)
        self._async_finalizers_stack = AsyncExitStack()

    def _create(
        self, dep: Dependency[T], **dep_args: Awaitable
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
                ready_value = (
                    await self._async_finalizers_stack.enter_async_context(
                        value
                    )
                )
            else:
                ready_value = await value

            self._resolved[dep.name] = EagerValueAwaitable(ready_value)
            return ready_value

        return create_inner()


@contextmanager
def sync_resolver_scope(container: SyncContainer) -> Iterator[SyncResolver]:
    resolver = SyncResolver(container)
    with resolver._finalizers_stack:
        yield resolver


@asynccontextmanager
async def resolver_scope(container: Container) -> AsyncIterator[Resolver]:
    resolver = Resolver(container)
    # first enter/last exit sync dependencies
    with resolver._finalizers_stack:
        async with resolver._async_finalizers_stack:
            yield resolver
