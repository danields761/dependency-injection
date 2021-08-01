from typing import Any, Awaitable, Generator, Optional, Sequence, TypeVar

T = TypeVar('T')


class AwaitableValue(Awaitable[T]):
    """
    Always return value without suspending coroutine on
    `await AwaitableValue(...)`.

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


ScopeT = TypeVar('ScopeT')


def get_next_scope(scopes: Sequence[ScopeT], parent_scope: Optional[ScopeT]) -> ScopeT:
    if parent_scope is None:
        return scopes[0]

    try:
        parent_scope_idx = scopes.index(parent_scope)
    except ValueError as exc:
        raise ValueError('Parent scope is not valid for given scoped containers') from exc
    scope_idx = parent_scope_idx + 1
    if scope_idx >= len(scopes):
        raise ValueError('No next scope available for given scoped containers')

    return scopes[scope_idx]
