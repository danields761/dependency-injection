from __future__ import annotations

import inspect
from collections import defaultdict
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
    Any,
    Iterable,
    List,
    DefaultDict,
)

from dependency_injection.errors import DependencyLookupError
from dependency_injection.models import Scope, Dependency, AnyFactory
from dependency_injection.provider import (
    BaseFactoryWrapper,
    FactoryWrapper,
    AsyncFactoryWrapper,
)
from dependency_injection.type_checking import (
    is_required_supertype_of_provided,
)

T = TypeVar('T')
S = TypeVar('S')
C = TypeVar('C', bound='Container')

ROOT_SCOPE = Scope('init')


class InstantiatedValuesManager:
    pass


class Container:
    current_scope: Scope

    def resolve(self, dep_name: str, required_type: Type[T]) -> T:
        """
        :param dep_name:
        :param required_type: должен быть супертипом для производимого типа,
            иными словами тип запрашиваемой зависимости не может быть
            более специфичным чем тип производимой зависимости
        :return:
        """
        raise NotImplementedError

    def finalize(self) -> None:
        raise NotImplementedError


class MutableContainer(Container):
    def __init__(
        self,
        parent_ctr: Container,
        current_scope: Scope = ROOT_SCOPE,
    ):
        self._parent = parent_ctr
        self._provides_mut: DefaultDict[
            Scope, Dict[str, Dependency]
        ] = defaultdict(dict)
        self.current_scope = current_scope

    def provides(
        self,
        dep_name: str,
        provides_cls: Type[T],
        factory: Optional[AnyFactory] = None,
        **requires: Tuple[str, Type],
    ) -> None:
        self._provides_mut[self.current_scope][dep_name] = Dependency(
            dep_name, provides_cls, requires, factory
        )

    def provides_at_scope(
        self,
        scope: Scope,
        dep_name: str,
        provides_cls: Type[T],
        factory: Optional[AnyFactory] = None,
        **requires: Tuple[str, Type],
    ) -> None:
        pass


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
