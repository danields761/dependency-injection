from __future__ import annotations

import asyncio
import inspect
from types import TracebackType
from typing import (
    TypeVar,
    Callable,
    Any,
    Union,
    Awaitable,
    ClassVar,
    ContextManager,
    AsyncContextManager,
    Optional,
    Tuple,
    Generic,
    Type,
)

from dependency_injection.models import AnySyncFactory, AnyFactory

T = TypeVar('T')
S = TypeVar('S')
VW = TypeVar('VW')
AF = TypeVar('AF', bound=Callable)

#: `Eager` is opposite to `Awaitable`, uses the rule `Union[T]` <-> `T`
Eager = Union[T]

FinalizerCallable = Callable[
    [Optional[Type[Exception]], Optional[Exception], Optional[TracebackType]],
    VW[bool],
]


class Instantiator(Generic[T, VW, AF]):
    is_async: ClassVar[bool]

    def __init__(self, factory: AF[T], **kwargs: VW[Any]):
        self._factory = factory
        self._kwargs = kwargs
        self._value: Optional[T] = None
        self._finalizer: Optional[FinalizerCallable[VW]] = None

    @property
    def value(self) -> VW[T]:
        if self._value is not None:
            return self._wrap_value(self._value)
        else:
            return self._create_and_set_value()

    def finalize(
        self,
        exc_type: Optional[Type[Exception]],
        exc: Optional[Exception],
        tb: Optional[TracebackType],
    ) -> VW[bool]:
        if self._finalizer:
            return self._finalizer(exc_type, exc, tb)
        else:
            return self._wrap_value(False)

    def _create_and_set_value(self) -> VW[T]:
        raise NotImplementedError

    @classmethod
    def _wrap_value(cls, value: S) -> VW[S]:
        raise NotImplementedError


class SyncInstantiator(Instantiator[T, Eager, AnySyncFactory]):
    is_async = False

    def _create_and_set_value(self) -> T:
        pre_value = self._factory(**self._kwargs)
        if isinstance(pre_value, ContextManager):
            self._value = pre_value.__enter__()
            self._finalizer = pre_value.__exit__
        else:
            self._value = pre_value

        return self._value

    @classmethod
    def _wrap_value(cls, value: S) -> S:
        return value


async def _prepare_arg(name: str, arg: Awaitable) -> Tuple[str, Any]:
    return name, await arg


class AsyncInstantiator(Instantiator[T, Awaitable, AnyFactory]):
    is_async = True

    def _create_and_set_value(self) -> Awaitable[T]:
        async def impl() -> T:
            ready_kwargs = await asyncio.gather(
                *(_prepare_arg(name, kwarg) for name, kwarg in self._kwargs)
            )
            value_pass_1 = self._factory(**dict(ready_kwargs))
            if isinstance(value_pass_1, Awaitable):
                value_pass_2 = await value_pass_1
            else:
                value_pass_2 = value_pass_1

            if isinstance(value_pass_2, AsyncContextManager):
                value_pass_3 = await value_pass_2.__aenter__()
                self._finalizer = value_pass_2.__aexit__
            else:
                value_pass_3 = value_pass_2

            self._value = value_pass_3
            return self._value

        return impl()

    @classmethod
    def _wrap_value(cls, value: S) -> Awaitable[S]:
        fut = asyncio.get_running_loop().create_future()
        fut.set_result(value)
        return fut
