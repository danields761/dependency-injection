from contextlib import AbstractAsyncContextManager, AbstractContextManager
from typing import Callable
from unittest.mock import AsyncMock, MagicMock, Mock, call

from pytest import mark

from dependency_injection.core import (
    AsyncDependency,
    AsyncImmutableContainer,
    create_async_resolver,
)
from dependency_injection.utils import AwaitableValue
from tests.helpers import A_INST, A, DepOnA

pytestmark = mark.usefixtures('loop')


# Make aliases to avoid verbosity
Dependency = AsyncDependency
ImmutableContainer = AsyncImmutableContainer
create_resolver = create_async_resolver


def create_dependency(*args, is_async_factory=True, **kwargs):
    return Dependency.create(*args, is_async_factory=is_async_factory, **kwargs)


async def test_provides_sync_value():
    container = ImmutableContainer(
        {'a': create_dependency('a', A, {}, lambda: A_INST, is_async_factory=False)}
    )
    async with create_resolver(container) as resolver:
        assert await resolver.resolve('a', A) is A_INST


async def test_memoizes_sync_value_and_still_returns_awaitable():
    a_factory = Mock(Callable, name='a-factory', return_value=A_INST)
    container = ImmutableContainer(
        {'a': create_dependency('a', A, {}, a_factory, is_async_factory=False)}
    )

    async with create_resolver(container) as resolver:
        v1 = await resolver.resolve('a', A)
        v2 = await resolver.resolve('a', A)
        assert v1 is A_INST
        assert v2 is A_INST
        assert a_factory.mock_calls == [call()]

        # Actually, this is pure internal detail, but why not test it here?
        v3_awaitable = resolver.resolve('a', A)
        assert isinstance(v3_awaitable, AwaitableValue)
        assert await v3_awaitable is A_INST


async def test_provides_sync_cm_value():
    a_cm = MagicMock(AbstractContextManager, name='a-cm')
    a_cm.__enter__.return_value = A_INST
    a_cm_factory = Mock(Callable, name='a-factory', return_value=a_cm)
    container = ImmutableContainer(
        {
            'a': create_dependency(
                'a', A, {}, a_cm_factory, is_async_factory=False, is_context_manager=True
            )
        }
    )

    async with create_resolver(container) as resolver:
        a = await resolver.resolve('a', A)
        assert a is A_INST
        assert a_cm_factory.mock_calls == [call()]
        assert a_cm.mock_calls == [call.__enter__(a_cm)]

    assert a_cm.mock_calls == [
        call.__enter__(a_cm),
        # Verify context manager being finalized after exiting resolver's scope
        call.__exit__(a_cm, None, None, None),
    ]


async def test_provides_async_value():
    a_factory = AsyncMock(Callable, name='a-factory', return_value=A_INST)
    container = ImmutableContainer({'a': create_dependency('a', A, {}, a_factory)})

    async with create_resolver(container) as resolver:
        a = await resolver.resolve('a', A)
        assert a is A_INST
        assert a_factory.mock_calls == [call()]
        assert a_factory.await_args_list == [call()]


async def test_memoizes_async_value_and_still_returns_awaitable():
    a_factory = AsyncMock(Callable, name='a-factory', return_value=A_INST)
    container = ImmutableContainer({'a': create_dependency('a', A, {}, a_factory)})

    async with create_resolver(container) as resolver:
        v1 = await resolver.resolve('a', A)
        v2 = await resolver.resolve('a', A)
        assert v1 is A_INST
        assert v2 is A_INST
        assert a_factory.mock_calls == [call()]


async def test_provides_async_cm_value():
    a_cm = AsyncMock(AbstractAsyncContextManager, name='a-cm')
    a_cm.__aenter__.return_value = A_INST
    a_cm_factory = Mock(Callable, name='a-factory', return_value=a_cm)
    container = ImmutableContainer(
        {'a': create_dependency('a', A, {}, a_cm_factory, is_context_manager=True)}
    )

    async with create_resolver(container) as resolver:
        a = await resolver.resolve('a', A)
        assert a is A_INST
        assert a_cm_factory.mock_calls == [call()]
        assert a_cm.mock_calls == [call.__aenter__(a_cm)]
        assert a_cm.__aenter__.await_args_list == [call(a_cm)]

    assert a_cm.mock_calls == [
        call.__aenter__(a_cm),
        # Verify context manager being finalized after exiting resolver's scope
        call.__aexit__(a_cm, None, None, None),
    ]
    assert a_cm.__aexit__.await_args_list == [call(a_cm, None, None, None)]


async def test_async_factory_depends_on_sync():
    a_factory = Mock(Callable, name='a-factory', return_value=A_INST)
    dep_on_a_factory = AsyncMock(Callable, name='dep-on-a', wraps=DepOnA)
    container = ImmutableContainer(
        {
            'a': create_dependency('a', A, {}, a_factory, is_async_factory=False),
            'dep_on_a': create_dependency(
                'dep_on_a',
                DepOnA,
                {'a': ('a', A)},
                dep_on_a_factory,
            ),
        },
    )

    async with create_resolver(container) as resolver:
        dep_on_a = await resolver.resolve('dep_on_a', DepOnA)
        assert dep_on_a.a is A_INST
        assert a_factory.mock_calls == [call()]
        assert dep_on_a_factory.mock_calls == [call(a=A_INST)]
        assert dep_on_a_factory.await_args_list == [call(a=A_INST)]


async def test_sync_factory_depends_on_async():
    a_factory = AsyncMock(Callable, name='a-factory', return_value=A_INST)
    dep_on_a_factory = Mock(Callable, name='dep-on-a', wraps=DepOnA)
    container = ImmutableContainer(
        {
            'a': create_dependency('a', A, {}, a_factory),
            'dep_on_a': create_dependency(
                'dep_on_a',
                DepOnA,
                {'a': ('a', A)},
                dep_on_a_factory,
                is_async_factory=False,
            ),
        },
    )

    async with create_resolver(container) as resolver:
        dep_on_a = await resolver.resolve('dep_on_a', DepOnA)
        assert dep_on_a.a is A_INST
        assert a_factory.mock_calls == [call()]
        assert a_factory.await_args_list == [call()]
        assert dep_on_a_factory.mock_calls == [call(a=A_INST)]
