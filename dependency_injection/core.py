from __future__ import annotations

import abc
from contextlib import AsyncExitStack, ExitStack, asynccontextmanager, contextmanager
from dataclasses import dataclass
from typing import (
    Any,
    AsyncContextManager,
    AsyncIterator,
    Awaitable,
    Callable,
    ContextManager,
    Generic,
    Hashable,
    Iterator,
    Literal,
    Mapping,
    Optional,
    Protocol,
    Sequence,
    TypeVar,
    Union,
    cast,
    overload,
)

from dependency_injection.types_match import TypesMatcher, is_type_acceptable_in_place_of
from dependency_injection.utils import AwaitableValue, get_next_scope
from dependency_injection.validate_containers import (
    validate_async_container,
    validate_container,
    validate_scoped_async_containers,
    validate_scoped_containers,
)

C = TypeVar('C')
T = TypeVar('T')
T_cov = TypeVar('T_cov', covariant=True)
GuardT = TypeVar('GuardT', ContextManager, AsyncContextManager)
ScopeT = TypeVar('ScopeT', bound=Hashable)


@dataclass(frozen=True)
class CallableFactory(Generic[T_cov]):
    create: Callable[..., T_cov]


@dataclass(frozen=True)
class ContextManagerFactory(Generic[T_cov]):
    create: Callable[..., ContextManager[T_cov]]


@dataclass(frozen=True)
class AsyncCallableFactory(Generic[T_cov]):
    create: Callable[..., Awaitable[T_cov]]


@dataclass(frozen=True)
class AsyncContextManagerFactory(Generic[T_cov]):
    create: Callable[..., AsyncContextManager[T_cov]]


AnySyncFactory = Union[Callable[..., T_cov], Callable[..., ContextManager[T_cov]]]
AnyAsyncFactory = Union[
    AnySyncFactory[T_cov],
    Callable[..., Awaitable[T_cov]],
    Callable[..., AsyncContextManager[T_cov]],
]

AnySyncFactoryWrapper = Union[CallableFactory[T_cov], ContextManagerFactory[T_cov]]
AnyAsyncFactoryWrapper = Union[
    AnySyncFactoryWrapper[T_cov],
    AsyncCallableFactory[T_cov],
    AsyncContextManagerFactory[T_cov],
]


@overload
def _create_factory_wrapper(
    factory: AnySyncFactoryWrapper[T], is_async: Literal[False], is_context_manager: bool
) -> AnySyncFactoryWrapper[T]:
    ...


def _create_factory_wrapper(
    factory: AnyAsyncFactoryWrapper[T], is_async: bool, is_context_manager: bool
) -> AnyAsyncFactoryWrapper[T]:
    factory_wrapper_cls = {
        (False, False): CallableFactory,
        (False, True): ContextManagerFactory,
        (True, False): AsyncCallableFactory,
        (True, True): AsyncContextManagerFactory,
    }[(is_async, is_context_manager)]
    return factory_wrapper_cls(create=factory)


@dataclass(frozen=True)
class BaseDependency(Generic[T_cov]):
    name: str
    provides_type: type[T_cov]
    requires: Mapping[str, Union[type[Any], tuple[str, type[Any]]]]
    factory: AnyAsyncFactoryWrapper[T_cov]


@dataclass(frozen=True)
class Dependency(BaseDependency[T_cov]):
    factory: AnySyncFactoryWrapper[T_cov]

    @classmethod
    def create(
        cls: type[C],
        name: str,
        provides_type: type[T_cov],
        requires: Mapping[str, Union[type[Any], tuple[str, type[Any]]]],
        factory: AnySyncFactory[T_cov],
        is_context_manager: bool = False,
    ) -> C:
        return cls(
            name=name,
            provides_type=provides_type,
            requires=requires,
            factory=_create_factory_wrapper(factory, False, is_context_manager),
        )


@dataclass(frozen=True)
class AsyncDependency(BaseDependency[T_cov]):
    @classmethod
    def create(
        cls: type[C],
        name: str,
        provides_type: type[T_cov],
        requires: Mapping[str, Union[type[Any], tuple[str, type[Any]]]],
        factory: AnyAsyncFactory[T_cov],
        is_async_factory: bool = True,
        is_context_manager: bool = False,
    ) -> C:
        return cls(
            name=name,
            provides_type=provides_type,
            requires=requires,
            factory=_create_factory_wrapper(factory, is_async_factory, is_context_manager),
        )

    def as_sync_dependency(self) -> Dependency[T_cov]:
        factory = self.factory
        if not isinstance(factory, (CallableFactory, ContextManagerFactory)):
            raise TypeError(
                "Could not convert async dependency with async factories into sync dependency"
            )

        return Dependency(
            name=self.name,
            provides_type=self.provides_type,
            requires=self.requires,
            factory=factory,
        )


AnyDependency = Union[Dependency[T], AsyncDependency[T]]


class BaseContainer(Protocol):
    provides: Mapping[str, AnyDependency[Any]]
    provides_unnamed: Sequence[AnyDependency[Any]]
    types_matcher: TypesMatcher


class Container(BaseContainer, Protocol):
    provides: Mapping[str, Dependency[Any]]
    provides_unnamed: Sequence[Dependency[Any]]


class AsyncContainer(BaseContainer, Protocol):
    provides: Mapping[str, AsyncDependency[Any]]
    provides_unnamed: Sequence[AsyncDependency[Any]]


AnyContainer = Union[Container, AsyncContainer]


class ScopedContainers(Protocol[ScopeT]):
    scopes_order: Sequence[ScopeT]
    scopes: Mapping[ScopeT, Container]


class ScopedAsyncContainers(Protocol[ScopeT]):
    scopes_order: Sequence[ScopeT]
    scopes: Mapping[ScopeT, AsyncContainer]


@dataclass(frozen=True)
class ImmutableContainer:
    provides: Mapping[str, Dependency[Any]]
    provides_unnamed: Sequence[Dependency[AnyDependency]] = ()
    types_matcher: TypesMatcher = is_type_acceptable_in_place_of


@dataclass(frozen=True)
class AsyncImmutableContainer:
    provides: Mapping[str, AsyncDependency[Any]]
    provides_unnamed: Sequence[AsyncDependency[AnyDependency]] = ()
    types_matcher: TypesMatcher = is_type_acceptable_in_place_of


@dataclass(frozen=True)
class ImmutableScopedContainers(Generic[ScopeT]):
    scopes_order: Sequence[ScopeT]
    scopes: Mapping[ScopeT, Container]


@dataclass(frozen=True)
class AsyncImmutableScopedContainers(Generic[ScopeT]):
    scopes_order: Sequence[ScopeT]
    scopes: Mapping[ScopeT, AsyncContainer]


AnyContainersStack = Union[ScopedContainers[ScopeT], ScopedAsyncContainers[ScopeT]]


class _HasEnterContextManager(Protocol):
    def enter_context(self, cm: ContextManager[T]) -> T:
        raise NotImplementedError


class _HasEnterAsyncContextManager(_HasEnterContextManager, Protocol):
    def enter_async_context(self, cm: AsyncContextManager[T]) -> Awaitable[T]:
        raise NotImplementedError


class _HasGuard(Protocol[GuardT]):
    @property
    def guard(self) -> GuardT:
        raise NotImplementedError


class _ResolverProto(_HasGuard[ContextManager[None]], Protocol):
    def resolve(self, look_name: Optional[str], look_type: type[T]) -> T:
        raise NotImplementedError


class _AsyncResolverProto(_HasGuard[AsyncContextManager[None]], Protocol):
    def resolve(self, look_name: Optional[str], look_type: type[T]) -> Awaitable[T]:
        raise NotImplementedError


_AnyResolver = Union[_ResolverProto, _AsyncResolverProto]


class _Resolve(Protocol):
    def __call__(self, look_name: Optional[str], look_type: type[T]) -> T:
        raise NotImplementedError


class _AsyncResolve(Protocol):
    async def __call__(self, look_name: Optional[str], look_type: type[T]) -> T:
        raise NotImplementedError


_AnyResolve = Union[_Resolve, _AsyncResolve]


class BaseResolver(Generic[GuardT], abc.ABC):
    guard: GuardT
    finalizers_stack: Union[_HasEnterContextManager, _HasEnterAsyncContextManager]
    _container: AnyContainer
    _resolve_unknown: Optional[_AnyResolve]
    _resolved_cache: dict[str, Any]

    def resolve(self, look_name: Optional[str], look_type: type[T]) -> Union[T, Awaitable[T]]:
        try:
            dep = self._lookup_dep(look_name, look_type)
        except LookupError as exc:
            if self._resolve_unknown is None:
                raise

            try:
                # Try to recover via unknown resolver
                return self._resolve_unknown(look_name, look_type)
            except LookupError as ru_exc:
                raise ru_exc from exc

        try:
            # TODO can't validate cached value type
            memoized_value = self._resolved_cache[dep.name]
            return cast(Union[T, Awaitable[T]], memoized_value)
        except LookupError:
            pass

        # TODO check for cyclic dependencies
        dep_args = {
            arg_name: self.resolve(sub_dep_name, sub_dep_type)
            for arg_name, (sub_dep_name, sub_dep_type) in dep.requires.items()
        }
        return self._create(dep, **dep_args)

    def _lookup_dep(self, look_name: str, look_type: type[T]) -> AnyDependency[T]:
        not_found = look_name not in self._container.provides
        if not_found:
            raise LookupError(f'Dependency `{look_name}: {look_type}` not found')

        maybe_dep = self._container.provides[look_name]
        if not self._container.types_matcher(maybe_dep.provides_type, look_type):
            raise LookupError(
                f"Requested dependency `{look_name}: {look_type}` doesn't "
                f'matches provided type {maybe_dep.provides_type}'
            )
        # `T` is should be guarantied by types matcher
        dep: AnyDependency[T] = maybe_dep
        return dep

    def _create(self, dep: AnyDependency[T], **dep_args: Any) -> Union[T, Awaitable[T]]:
        raise NotImplementedError


class _BaseResolverFactory(Protocol[GuardT]):
    def __call__(
        self, container: AnyContainer, resolve_unknown: Optional[_AnyResolve] = None
    ) -> BaseResolver[GuardT]:
        pass


class BaseScopedResolver(Generic[GuardT, ScopeT], abc.ABC):
    @property
    @abc.abstractmethod
    def _owned_resolver_factory(
        self,
    ) -> _BaseResolverFactory[GuardT]:
        raise NotImplementedError

    def __init__(
        self,
        scoped_containers: AnyContainersStack[ScopeT],
        parent: Union[ScopedResolver[GuardT, ScopeT], ScopedAsyncResolver[GuardT, ScopeT]] = None,
        scope: Optional[ScopeT] = None,
    ):
        new_scope = get_next_scope(
            scoped_containers.scopes_order, None if parent is None else parent.scope
        )
        resolve_unknown = None if parent is None else parent.resolve
        if scope is not None and new_scope != scope:
            raise ValueError(
                f'Could not enter given scope "{scope}", ' f'only "{new_scope}" is possible'
            )
        self._scope = new_scope

        container = scoped_containers.scopes[self._scope]
        # Owned resolver is required to avid mixin-usages
        self._owned_resolver: BaseResolver[GuardT] = self._owned_resolver_factory(
            container=container, resolve_unknown=resolve_unknown
        )
        self._scoped_containers = scoped_containers

    @property
    def scope(self) -> ScopeT:
        return self._scope

    @property
    def guard(self) -> GuardT:
        return self._owned_resolver.guard

    def resolve(self, look_name: str, look_type: type[T]) -> Union[T, Awaitable[T]]:
        return self._owned_resolver.resolve(look_name, look_type)


def _create_dependency_sync(
    finalizers_stack: _HasEnterContextManager,
    dep: Dependency[T],
    **dep_args: Any,
) -> T:
    if isinstance(dep.factory, CallableFactory):
        return dep.factory.create(**dep_args)
    elif isinstance(dep.factory, ContextManagerFactory):
        value = dep.factory.create(**dep_args)
        return finalizers_stack.enter_context(value)
    else:
        raise TypeError(f'Unexpected dependency factory for dependency {dep!r}')


async def _create_dependency_async(
    finalizers_stack: _HasEnterAsyncContextManager,
    dep: AsyncDependency[T],
    **dep_args: Awaitable[Any],
) -> T:
    ready_sub_deps = {
        sub_dep_name: await sub_dep_awaitable
        for sub_dep_name, sub_dep_awaitable in dep_args.items()
    }

    if isinstance(dep.factory, (CallableFactory, ContextManagerFactory)):
        return _create_dependency_sync(
            finalizers_stack,
            dep.as_sync_dependency(),
            **ready_sub_deps,
        )
    if isinstance(dep.factory, AsyncCallableFactory):
        return await dep.factory.create(**ready_sub_deps)
    elif isinstance(dep.factory, AsyncContextManagerFactory):
        context_manager = dep.factory.create(**ready_sub_deps)
        return await finalizers_stack.enter_async_context(context_manager)
    else:
        raise TypeError(f'Unexpected dependency factory for dependency {dep!r}')


class Resolver(BaseResolver[ContextManager[None]]):
    def __init__(
        self,
        container: Container,
        resolve_unknown: Optional[_Resolve] = None,
    ):
        self._container = container
        self._resolved_cache: dict[str, Any] = {}
        self._resolve_unknown = resolve_unknown
        self.guard = self.finalizers_stack = ExitStack()

    def resolve(self, look_name: Optional[str], look_type: type[T]) -> T:
        return cast(
            T,
            super().resolve(look_name, look_type),
        )

    def _lookup_dep(self, look_name: str, look_type: type[T]) -> Dependency[T]:
        dep = super()._lookup_dep(look_name, look_type)
        if not isinstance(dep, Dependency):
            raise RuntimeError(
                f"Unexpected condition: sync resolver received dependency of other type {dep!r}"
            )

        return dep

    def _create(self, dep: AnyDependency[T], **dep_args: Any) -> T:
        if not isinstance(dep, Dependency):
            raise RuntimeError(
                f"Unexpected condition: sync resolver received dependency of other type {dep!r}"
            )

        created = _create_dependency_sync(self.finalizers_stack, dep, **dep_args)
        self._resolved_cache[dep.name] = created
        return created


class AsyncResolver(BaseResolver[AsyncContextManager[None]]):
    def __init__(
        self,
        container: AsyncContainer,
        resolve_unknown: Optional[_AsyncResolve] = None,
    ):
        self._container = container
        self._resolved_cache: dict[str, Any] = {}
        self._resolve_unknown = resolve_unknown
        self.guard = self.finalizers_stack = AsyncExitStack()

    def resolve(self, look_name: Optional[str], look_type: type[T]) -> Awaitable[T]:
        return cast(
            Awaitable[T],
            super().resolve(look_name, look_type),
        )

    def _lookup_dep(self, look_name: str, look_type: type[T]) -> AsyncDependency[T]:
        dep = super()._lookup_dep(look_name, look_type)
        if not isinstance(dep, AsyncDependency):
            raise RuntimeError(
                f"Unexpected condition: async resolver received dependency of other type {dep!r}"
            )

        return dep

    async def _create(self, dep: AnyDependency[T], **dep_args: Any) -> T:
        if any(not isinstance(dep, Awaitable) for dep in dep_args.values()):
            raise RuntimeError(
                f"Unexpected condition: not all arguments for "
                f"async dependency is awaitables {dep_args!r}"
            )

        if not isinstance(dep, AsyncDependency):
            raise RuntimeError(
                f"Unexpected condition: async resolver received dependency of other type {dep!r}"
            )

        value = await _create_dependency_async(self.finalizers_stack, dep, **dep_args)
        self._resolved_cache[dep.name] = AwaitableValue(value)
        return value


class ScopedResolver(
    BaseScopedResolver[ContextManager[None], ScopeT],
    Generic[ScopeT],
):
    _owned_resolver_factory = Resolver

    def __init__(
        self,
        scoped_containers: ScopedContainers[ScopeT],
        parent: Optional[ScopedResolver[ScopeT]] = None,
        scope: Optional[ScopeT] = None,
    ):
        super().__init__(scoped_containers, parent=parent, scope=scope)

    def resolve(self, look_name: str, look_type: type[T]) -> T:
        return cast(
            T,
            super().resolve(look_name, look_type),
        )

    def next_scope(self, scope: Optional[ScopeT] = None) -> ContextManager[ScopedResolver[ScopeT]]:
        child_resolver = ScopedResolver(
            scoped_containers=cast(ScopedContainers, self._scoped_containers),
            parent=self,
            scope=scope,
        )

        @contextmanager
        def cm():
            with child_resolver.guard:
                yield child_resolver

        return cm()


class ScopedAsyncResolver(
    BaseScopedResolver[AsyncContextManager[None], ScopeT],
    Generic[ScopeT],
):
    _owned_resolver_factory = AsyncResolver

    def resolve(self, look_name: str, look_type: type[T]) -> Awaitable[T]:
        return cast(
            Awaitable[T],
            super().resolve(look_name, look_type),
        )

    def next_scope(
        self, scope: Optional[ScopeT] = None
    ) -> AsyncContextManager[ScopedAsyncResolver[ScopeT]]:
        child_resolver = ScopedAsyncResolver(
            scoped_containers=cast(ScopedAsyncContainers, self._scoped_containers),
            parent=self,
            scope=scope,
        )

        @asynccontextmanager
        async def cm():
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
