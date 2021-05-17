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
    ClassVar,
    ContextManager,
    Generic,
    Hashable,
    Iterator,
    Mapping,
    Optional,
    Protocol,
    Sequence,
    Type,
    TypeVar,
    Union,
    cast,
)

from dependency_injection.types_match import (
    TypesMatcher,
    is_type_acceptable_in_place_of,
)
from dependency_injection.utils import AwaitableValue
from dependency_injection.validate_containers import (
    validate_async_container,
    validate_container,
    validate_scoped_async_containers,
    validate_scoped_containers,
)

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
Eager = Union

# Exists, because this part of code abuses not even well-discussed
# "Higher-Kinded Generics", and `typing.Generic` codebase not aware of such
# concept (it is even prohibited by various internal checks). Threat this
# variable as symbol which defines a slot on HK type variable, on which
# place something (either other type variable or concrete type) might be
# plugged in.
HKV = Any

#: Abbreviation for "Allowed Factories",
#: one of `AnySyncFactory` or `AnyFactory`, Higher-Kinded
AF = TypeVar('AF', bound=Callable)

#: Abbreviation for "Value Wrapper"; one of `Eager` or `Awaitable`,
#: Higher-Kinded
VW = TypeVar('VW')

#: Abbreviation for "Guard Type", Higher-Kinded
GT = TypeVar('GT', ContextManager, AsyncContextManager)

#: Abbreviation for "Scope Type"
ST = TypeVar('ST', bound=Hashable)

#: Abbreviation for "Dependency Type", Higher-Kinded
DT = TypeVar('DT', bound='BaseDependency')


@dataclass(frozen=True, unsafe_hash=True)
class BaseDependency(Generic[T, AF]):
    name: str
    provides_type: Type[T]
    requires: Mapping[str, tuple[str, Type]]
    factory: AF[T]
    context_manager: bool = False
    async_: bool = False


class BaseContainer(Protocol[DT]):
    provides: Mapping[str, DT]
    types_matcher: TypesMatcher


@dataclass(frozen=True)
class BaseImmutableContainer(Generic[DT]):
    provides: Mapping[str, DT]
    types_matcher: TypesMatcher = is_type_acceptable_in_place_of


@dataclass(frozen=True)
class BaseScopedContainers(Generic[ST, DT]):
    scopes_order: Sequence[ST]
    scopes: Mapping[ST, BaseContainer[DT]]


# Sync aliases
Dependency = BaseDependency[T, AnySyncFactory[T]]
Container = BaseContainer[Dependency[Any]]
ImmutableContainer = BaseImmutableContainer[Dependency[Any]]
ScopedContainers = BaseScopedContainers[ST, Dependency[Any]]
# Async aliases
AsyncDependency = BaseDependency[T, AnyAsyncFactory[T]]
AsyncContainer = BaseContainer[AsyncDependency[Any]]
AsyncImmutableContainer = BaseImmutableContainer[AsyncDependency[Any]]
ScopedAsyncContainers = BaseScopedContainers[ST, AsyncContainer]


class _HasEnterContextManagerMethod(Protocol):
    def enter_context(self, cm: ContextManager[T]) -> T:
        raise NotImplementedError


class _HasEnterAsyncContextManager(_HasEnterContextManagerMethod, Protocol):
    def enter_async_context(self, cm: AsyncContextManager[T]) -> Awaitable[T]:
        raise NotImplementedError


class BaseResolverProto(Protocol[VW, DT, GT]):
    @property
    def guard(self) -> GT:
        raise NotImplementedError

    def resolve(self, look_name: str, look_type: Type[T]) -> VW[T]:
        raise NotImplementedError


class BaseResolver(Generic[VW, DT, GT]):
    guard: GT[None]
    finalizers_stack: _HasEnterContextManagerMethod

    def __init__(
        self,
        container: BaseContainer[DT],
        unknown_resolver: Optional[Callable[[str, Type[T]], VW[T]]] = None,
    ):
        """
        Init resolver.

        :param container: dependencies container
        :param unknown_resolver: if specified dependency isn't provided within
            given container, then given callable will be tried. It's helps us
            to chain resolvers in different ways.
        """
        self._container = container
        self._resolved: dict[str, VW[Any]] = {}
        self._unknown_resolver = unknown_resolver

    def resolve(self, look_name: str, look_type: Type[T]) -> VW[T]:
        dep: Optional[Dependency[T]] = None
        dep_lookup_exc: Optional[LookupError] = None
        try:
            dep = self._lookup_dep(look_name, look_type)
        except LookupError as exc:
            if not self._unknown_resolver:
                raise
            dep_lookup_exc = exc

        if self._unknown_resolver:
            # "Unknown resolver" might help handle unknown dependency
            try:
                return self._unknown_resolver(look_name, look_type)
            except LookupError:
                # Unknown resolver fails to provide dependency, then raise
                # original lookup exception
                raise dep_lookup_exc

        try:
            memoized_value: VW[T] = self._resolved[dep.name]
            return memoized_value
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

    def _create(self, dep: DT[T], **dep_args: VW) -> VW[T]:
        raise NotImplementedError


class BaseScopedResolver(
    Generic[VW, DT, GT, ST], BaseResolverProto[VW, DT, GT]
):
    _owned_resolver_cls: ClassVar[BaseResolver[VW, DT, GT]]

    def __init__(
        self,
        scoped_containers: BaseScopedContainers[ST, DT],
        parent: Optional[BaseScopedResolver[VW, DT, GT, ST]] = None,
        scope: Optional[ST] = None,
    ):
        if parent is None:
            first_scope = scoped_containers.scopes_order[0]
            if scope is not None and scope != first_scope:
                raise ValueError(
                    'No parent resolver were given, but specified '
                    'scope is not first for scoped containers'
                )
            scope = first_scope
            unknown_resolver = None
        else:
            try:
                parent_scope_idx = scoped_containers.scopes_order.index(
                    parent.scope
                )
            except ValueError:
                raise ValueError(
                    'Parent scope is not valid for given scoped containers'
                )
            scope_idx = parent_scope_idx + 1
            if scope_idx >= len(scoped_containers.scopes_order):
                raise ValueError(
                    'No next scope available for given scoped containers'
                )
            scope = scoped_containers.scopes_order[scope_idx]
            unknown_resolver = parent.resolve

        container = scoped_containers.scopes[scope]
        # Owned resolver is required to avid mixin-usages
        self._owned_resolver: BaseResolver[
            VW, DT, GT
        ] = self._owned_resolver_cls(
            container=container, unknown_resolver=unknown_resolver
        )
        self._scoped_containers = scoped_containers
        self._scope = scope

    @property
    def scope(self) -> ST:
        return self._scope

    @property
    def guard(self) -> GT[None]:
        return self._owned_resolver.guard

    def resolve(self, look_name: str, look_type: Type[T]) -> VW[T]:
        return self._owned_resolver.resolve(look_name, look_type)

    def next_scope(self) -> GT[BaseScopedResolver[VW, DT, GT, ST]]:
        raise NotImplementedError


def _create_dependency_as_sync(
    resolver: BaseResolver[Any, Any, Any],
    dep: BaseDependency[T, Any],
    **dep_args: Any,
) -> T:
    """
    Creates dependency which will live within lifespan of given resolver.

    :param resolver: resolver
    :param dep: dependency to provide
    :param dep_args: dependency factory arguments
    :return: created dependency
    """
    assert (
        not dep.async_
    ), 'Should be never called for dependencies with async factories'

    value: Union[T, ContextManager[T]] = dep.factory(**dep_args)
    if not dep.context_manager:
        return cast(T, value)

    if not isinstance(value, ContextManager):
        raise TypeError(
            f'Dependency {dep.name} expected to be context manager, '
            f'but factory returned {value}'
        )
    return resolver.finalizers_stack.enter_context(value)


class Resolver(BaseResolver[Eager[HKV], Dependency[Any], ContextManager[HKV]]):
    def __init__(self, container: Container):
        super().__init__(container)
        self.guard = self.finalizers_stack = ExitStack()

    def _create(self, dep: Dependency[T], **dep_args: Any) -> Eager[T]:
        created = _create_dependency_as_sync(self, dep, **dep_args)
        self._resolved[dep.name] = created
        return created


class AsyncResolver(
    BaseResolver[
        Awaitable[HKV], AsyncDependency[Any], AsyncContextManager[HKV]
    ]
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
                ready_value = _create_dependency_as_sync(
                    self, dep, **ready_sub_deps
                )
                self._resolved[dep.name] = AwaitableValue(ready_value)
                return ready_value

            factored_value = dep.factory(**ready_sub_deps)
            if not isinstance(
                factored_value, (Awaitable, AsyncContextManager)
            ):
                raise TypeError(
                    f'Dependency {dep} marked as `async_` should always '
                    'return either '
                    '`Awaitable[T]` or `AsyncContextManager[T]`, '
                    f'not {factored_value!r}'
                )

            value: Union[
                Awaitable[T],
                AsyncContextManager[T],
            ] = factored_value
            if not dep.context_manager:
                ready_value = await value
            else:
                if not isinstance(value, AsyncContextManager):
                    raise TypeError(
                        f'Dependency {dep} marked as '
                        '`async_` and `context_manager` have to return '
                        "`AsyncContextManager[T]` from it's factory, "
                        f'not {value!r}'
                    )
                ready_value = await self.finalizers_stack.enter_async_context(
                    value
                )

            # Place created value into the cache as awaitable, so
            # `BaseResolver` can simply return it's value
            self._resolved[dep.name] = AwaitableValue(ready_value)
            return ready_value

        return create_inner()


class ScopedResolver(
    BaseScopedResolver[Eager[HKV], Dependency[Any], ContextManager[HKV], ST],
    Generic[ST],
):
    _owned_resolver_cls = Resolver

    def next_scope(self) -> ContextManager[ScopedResolver[ST]]:
        @contextmanager
        def cm():
            child_resolver = ScopedResolver(self._scoped_containers, self)
            with child_resolver.guard:
                yield child_resolver

        return cm()


class ScopedAsyncResolver(
    BaseScopedResolver[
        Awaitable[HKV], AsyncDependency[Any], AsyncContextManager[HKV], ST
    ],
    Generic[ST],
):
    _owned_resolver_cls = AsyncResolver

    def next_scope(self) -> AsyncContextManager[ScopedAsyncResolver[ST]]:
        @asynccontextmanager
        async def cm():
            child_resolver = ScopedAsyncResolver(self._scoped_containers, self)
            async with child_resolver.guard:
                yield child_resolver

        return cm()


@contextmanager
def create_resolver(container: Container) -> Iterator[Resolver]:
    validate_container(container)

    resolver = Resolver(container)
    with resolver.guard:
        yield resolver


@contextmanager
def create_scoped_resolver(
    scoped_containers: ScopedContainers,
) -> Iterator[ScopedResolver]:
    validate_scoped_containers(scoped_containers)

    resolver = ScopedResolver(scoped_containers)
    with resolver.guard:
        yield resolver


@asynccontextmanager
async def create_async_resolver(
    container: AsyncContainer,
) -> AsyncIterator[AsyncResolver]:
    validate_async_container(container)

    resolver = AsyncResolver(container)
    async with resolver.guard:
        yield resolver


@asynccontextmanager
async def create_scoped_async_resolver(
    scoped_containers: ScopedAsyncContainers,
) -> AsyncIterator[AsyncResolver]:
    validate_scoped_async_containers(scoped_containers)

    resolver = ScopedAsyncResolver(scoped_containers)
    async with resolver.guard:
        yield resolver
