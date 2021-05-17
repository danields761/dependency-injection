from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from dependency_injection.core import (
        AsyncContainer,
        Container,
        ScopedAsyncContainers,
        ScopedContainers,
    )


def validate_container(container: Container) -> None:
    pass


def validate_async_container(container: AsyncContainer) -> None:
    pass


def validate_scoped_containers(
    scoped_containers: ScopedContainers,
) -> None:
    pass


def validate_scoped_async_containers(
    scoped_containers: ScopedAsyncContainers,
) -> None:
    pass
