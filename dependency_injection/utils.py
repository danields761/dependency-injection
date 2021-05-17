from typing import Any, Awaitable, Generator, TypeVar

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
