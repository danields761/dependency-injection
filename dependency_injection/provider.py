from typing import TypeVar, Generic, Awaitable

T = TypeVar('T')


class BaseProvider(Generic[T]):
    pass


class Provider(BaseProvider[T]):
    def provide(self) -> T:
        pass

    def finalize(self) -> None:
        pass


class ContextManagerProvider(Provider[T]):
    pass


class AsyncProvider(BaseProvider[T]):
    def provide(self) -> Awaitable[T]:
        pass

    def finalize(self) -> Awaitable[None]:
        pass


class AsyncContextManagerProvider(AsyncProvider[T]):
    pass
