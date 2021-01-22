from __future__ import annotations

import asyncio
from contextlib import contextmanager, asynccontextmanager
from typing import (
    TypeVar,
    Type,
    Mapping,
    ContextManager,
    AsyncContextManager,
    Tuple,
    Optional,
    Dict,
    Protocol,
    Generic,
    Callable,
    Sequence,
    Any,
    overload,
    Union,
    Awaitable,
    ClassVar,
)

from dependency_injection.errors import (
    DependencyTypeMismatchError,
    DependencyLookupError,
)
from dependency_injection.instantiator import (
    Eager,
    Instantiator,
    SyncInstantiator,
    AsyncInstantiator,
)
from dependency_injection.models import (
    Dependency,
    AnyFactory,
    AnySyncFactory,
)
from dependency_injection.type_checking import (
    is_required_supertype_of_provided,
    is_instantiatable_type,
)

T = TypeVar('T')
S = TypeVar('S')
#: Scope type
SC = TypeVar('SC', bound=int)
#: Allowed factory types
AF = TypeVar('AF', bound=Callable)
#: Value wrapper
VW = TypeVar('VW')


class BaseProvider(Generic[SC, VW, AF]):
    instantiator_cls: ClassVar[Type[Instantiator[S, VW, AF]]]

    def __init__(
        self,
        ctr: Container[SC, AF],
        scope: SC,
        parent: Optional[BaseProvider[SC, VW, AF]] = None,
    ):
        if parent and ctr.scope_factory(parent.current_scope + 1) != scope:
            raise RuntimeError('Could not enter indirect scope')

        self.ctr = ctr
        self.current_scope = scope
        self._parent = parent
        self._provided: Dict[str, Instantiator[Any, VW, AF]] = {}

    def provide(self, dep_name: str, required_type: Type[T]) -> VW[T]:
        """
        :param dep_name:
        :param required_type: должен быть супертипом для производимого типа,
            иными словами тип запрашиваемой зависимости не может быть
            более специфичным чем тип производимой зависимости
        :return:
        """
        dependency: Optional[Dependency[T, AF, SC]] = None
        for _, scope_resolves in self.ctr.resolves:
            try:
                dependency = scope_resolves[dep_name]
                break
            except KeyError:
                pass

        if not dependency:
            raise DependencyLookupError(
                dep_name, required_type, 'Not declared'
            )
        if not is_required_supertype_of_provided(
            dependency.provides_type, required_type
        ):
            raise DependencyTypeMismatchError(
                dep_name, required_type, dependency.provides_type
            )

        try:
            return self._lookup_provided(dep_name, required_type).value
        except DependencyLookupError:
            pass

        try:
            scope_owner = self._lookup_scope_owner(dependency.scope)
        except LookupError:
            raise DependencyLookupError(
                dep_name,
                required_type,
                f'declared for future scope "{dependency.scope!r}"',
            )
        return scope_owner._instantiate(dependency).value

    def finalize(self) -> VW[None]:
        raise NotImplementedError

    def _instantiate(
        self, dependency: Dependency[T, AF, SC]
    ) -> Instantiator[T, VW, AF]:
        dependency_kwargs = {
            arg_name: self.provide(arg_dep_name, arg_dep_type)
            for arg_name, (
                arg_dep_name,
                arg_dep_type,
            ) in dependency.requires.items()
        }
        instantiator = self.instantiator_cls(
            dependency.factory, **dependency_kwargs
        )
        self._provided[dependency.name] = instantiator
        return instantiator

    def _lookup_scope_owner(self, scope: SC) -> BaseProvider[SC, VW, AF]:
        if self.current_scope == scope:
            return self
        if self.current_scope < scope:
            raise LookupError(scope)
        parent: Optional[BaseProvider[SC, VW, AF]] = self._parent
        while parent and parent.current_scope != scope:
            parent = parent._parent

        if not parent or parent.current_scope != scope:
            raise LookupError(scope)

        return parent

    def _lookup_provided(
        self, dep_name: str, required_type: Type[T]
    ) -> Instantiator[T, VW, AF]:
        try:
            return self._provided[dep_name]
        except KeyError:
            pass

        if not self._parent:
            raise DependencyLookupError(dep_name, required_type)

        return self._parent._lookup_provided(dep_name, required_type)


class SyncProvider(BaseProvider[SC, Eager, AnySyncFactory]):
    instantiator_cls = SyncInstantiator

    def finalize(self) -> None:
        for instantiator in self._provided.values():
            instantiator.finalize()


class AsyncProvider(BaseProvider[SC, Awaitable, AnyFactory]):
    instantiator_cls = AsyncInstantiator

    def finalize(self) -> Awaitable[None]:
        return asyncio.gather(
            *(
                instantiator.finalize()
                for instantiator in self._provided.values()
            )
        )


class Container(Protocol[SC, AF]):
    @property
    def scope_factory(self) -> Callable[[int], SC]:
        raise NotImplementedError

    @property
    def resolves(
        self,
    ) -> Sequence[Tuple[SC, Mapping[str, Dependency[Any, AF, SC]]]]:
        raise NotImplementedError


SyncContainer = Container[SC, AnySyncFactory]
AsyncContainer = Container[SC, AnyFactory]


class MutableContainer(Container[SC, AF]):
    def __init__(
        self,
        scope_factory: Callable[[int], SC],
        resolves: Optional[
            Sequence[Tuple[SC, Mapping[str, Dependency[Any, AF, SC]]]]
        ] = None,
    ):
        self._scope_factory = scope_factory
        if resolves is None:
            resolves = ()
        self._resolves = list(
            (scope, dict(scope_resolves)) for scope, scope_resolves in resolves
        )

    def provides(
        self,
        dep_name: str,
        provides_type: Type[T],
        factory: Optional[AF[T]] = None,
        **requires: Tuple[str, Type],
    ) -> None:
        self.provides_at_scope(
            self._scope_factory(0),
            dep_name,
            provides_type,
            factory,
            **requires,
        )

    def provides_at_scope(
        self,
        scope: SC,
        dep_name: str,
        provides_type: Type[T],
        factory: Optional[AF[T]] = None,
        **requires: Tuple[str, Type],
    ) -> None:
        if len(self._resolves) <= scope:
            if len(self._resolves):
                last_scope, _ = self._resolves[-1]
            else:
                last_scope = -1

            self._resolves.extend(
                (self._scope_factory(i), {})
                for i in range(last_scope + 1, scope + 1)
            )
        if not factory:
            if not is_instantiatable_type(provides_type):
                raise TypeError(
                    'Could not register provider for'
                    'non-instantiatable type without factory'
                )

            factory = provides_type

        _, scope_deps = self._resolves[scope]
        scope_deps[dep_name] = Dependency(
            scope, dep_name, provides_type, requires, factory
        )

    @property
    def resolves(
        self,
    ) -> Sequence[Tuple[SC, Mapping[str, Dependency[Any, AF, SC]]]]:
        return self._resolves

    @property
    def scope_factory(self) -> Callable[[int], SC]:
        return self._scope_factory


@overload
def provider_scope(ctr: SyncContainer) -> ContextManager[SyncProvider[SC]]:
    ...


@overload
def provider_scope(
    provider: SyncProvider[SC], scope: SC
) -> ContextManager[SyncProvider[SC]]:
    ...


@overload
def provider_async_scope(
    ctr: AsyncContainer,
) -> AsyncContextManager[AsyncProvider[SC]]:
    ...


@overload
def provider_async_scope(
    provider: AsyncProvider[SC], scope: SC
) -> AsyncContextManager[AsyncProvider[SC]]:
    ...


@contextmanager
def provider_scope(
    provider_or_ctr: Union[SyncProvider[SC], SyncContainer],
    scope: Optional[SC] = None,
) -> ContextManager[SyncProvider[SC]]:
    if isinstance(provider_or_ctr, BaseProvider):
        provider = provider_or_ctr
        next_provider = SyncProvider(provider.ctr, scope, provider)
    else:
        ctr = provider_or_ctr
        next_provider = SyncProvider(ctr, ctr.scope_factory(0))

    try:
        yield next_provider
    finally:
        next_provider.finalize()


@asynccontextmanager
async def provider_async_scope(
    provider_or_ctr: Union[AsyncProvider[SC], AsyncContainer[SC]],
    scope: Optional[SC] = None,
) -> AsyncContextManager[AsyncProvider[SC]]:
    if isinstance(provider_or_ctr, BaseProvider):
        provider = provider_or_ctr
        next_provider = AsyncProvider(provider.ctr, scope, provider)
    else:
        ctr = provider_or_ctr
        next_provider = AsyncProvider(ctr, ctr.scope_factory(0))

    try:
        yield next_provider
    finally:
        await next_provider.finalize()
