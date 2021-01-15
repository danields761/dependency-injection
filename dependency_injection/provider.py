from typing import TypeVar, Generic, Awaitable, Any

T = TypeVar('T')


class BaseFactoryWrapper(Generic[T]):
    pass


class FactoryWrapper(BaseFactoryWrapper[T]):
    def provide(self, *args: Any, **kwargs: Any) -> T:
        pass

    def finalize(self) -> None:
        pass


class ContextManagerFactoryWrapper(FactoryWrapper[T]):
    pass


class AsyncFactoryWrapper(BaseFactoryWrapper[T]):
    def provide(self, *args: Any, **kwargs: Any) -> Awaitable[T]:
        pass

    def finalize(self) -> Awaitable[None]:
        pass


class AsyncContextManagerFactoryWrapper(AsyncFactoryWrapper[T]):
    pass
