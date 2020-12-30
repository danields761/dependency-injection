from __future__ import annotations

from typing import (
    TypeVar,
    Union,
    Awaitable,
    Type,
    Mapping,
    ContextManager,
    AsyncContextManager,
    Tuple,
    Optional,
    Dict,
    cast,
)

from dependency_injection.errors import DependencyLookupError
from dependency_injection.models import Scope, Dependency, AnyFactory
from dependency_injection.type_checking import (
    is_required_supertype_of_provided,
)

T = TypeVar('T')
S = TypeVar('S')
C = TypeVar('C', bound='Container')

ROOT_SCOPE = Scope('init')


class Container:
    @property
    def current_scope(self) -> Scope:
        return self._current_scope

    def __init__(
        self,
        resolves: Mapping[str, Dependency],
        scope: Scope = ROOT_SCOPE,
        inherits_container: Optional[Container] = None,
    ):
        self._resolves = resolves
        if inherits_container:
            if (
                scope != inherits_container.current_scope
                and not scope.is_child_of(inherits_container.current_scope)
            ):
                raise ValueError(
                    'New scope must be either same or direct '
                    'children of inherited container'
                )

        self._current_scope = scope
        self._parent_container = inherits_container

    def resolve(
        self, dep_name: str, required_type: Type[T]
    ) -> Union[T, Awaitable[T]]:
        """
        :param dep_name:
        :param required_type: должен быть супертипом для производимого типа,
            иными словами тип запрашиваемой зависимости не может быть
            более специфичным чем тип производимой зависимости
        :return:
        """
        dependency = _lookup_dependency(
            self._all_resolvers(), dep_name, required_type
        )

    def finalize(self) -> Union[None, Awaitable[None]]:
        pass

    def _all_resolvers(self) -> Dict[str, Dependency]:
        parent_resolvers = {}
        if self._parent_container:
            parent_resolvers = self._parent_container._all_resolvers()
        return parent_resolvers | self._resolves


class MutableContainer(Container):
    def __init__(
        self,
        resolves: Optional[Mapping[str, Dependency]] = None,
        scope: Optional[Scope] = None,
        inherits_container: Optional[MutableContainer] = None,
    ):
        super().__init__(resolves or {}, scope, inherits_container)
        self._resolves_mut: Dict[str, Dependency] = {}

    def provides(
        self,
        dep_name: str,
        provides_cls: Type[T],
        factory: Optional[AnyFactory] = None,
        **requires: Tuple[str, Type],
    ) -> None:
        pass

    def provides_at_scope(
        self,
        scope: Scope,
        dep_name: str,
        provides_cls: Type[T],
        factory: Optional[AnyFactory] = None,
        **requires: Tuple[str, Type],
    ) -> None:
        pass

    def _all_resolvers(self) -> Dict[str, Dependency]:
        return super()._all_resolvers() | self._resolves_mut


def container_scope(container: C, scope: Scope) -> ContextManager[C]:
    pass


def container_async_scope(
    container: C, scope: Scope
) -> AsyncContextManager[C]:
    pass


def _lookup_dependency(
    dependencies: Mapping[str, Dependency],
    dep_name: str,
    required_type: Type[T],
) -> Dependency[T]:
    try:
        dependency = dependencies[dep_name]
    except KeyError:
        raise DependencyLookupError(dep_name)

    if not is_required_supertype_of_provided(
        dependency.requires_type, required_type
    ):
        raise DependencyLookupError(
            dep_name, required_type, dependency.requires_type
        )
    return cast(Dependency[T], dependency)
