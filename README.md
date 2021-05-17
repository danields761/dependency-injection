# Dependency-Injection prototype library

Examples:

```python
from dependency_injection.core import (
    ScopedContainers, 
    ImmutableContainer,
    Dependency,
    create_scoped_resolver,
)


SCOPES = ['root', 'app', 'handler']

scoped_containers = ScopedContainers(
    SCOPES,
    {
        'root': ImmutableContainer(
            {'cfg': Dependency('cfg', Cfg, {}, cfg_factory)}
        ),
        'app': ImmutableContainer(
            {
                'db': Dependency(
                    'db', DB, {'cfg': ('cfg', Cfg)}, db_factory
                ),
                'cache': Dependency(
                    'cache',
                    Cache,
                    {'cfg': ('cfg', Cfg)},
                    cache_factory,
                ),
            }
        ),
        'handler': ImmutableContainer(
            {
                'transaction': Dependency(
                    'transaction',
                    Transaction,
                    {'db': ('db', DB)},
                    transaction_factory,
                ),
                'foo_ctrl': Dependency(
                    'foo_ctrl',
                    FooCtrl,
                    {'transaction': ('transaction', Transaction)},
                    foo_ctrl_factory,
                ),
                'bar_ctrl': Dependency(
                    'bar_ctrl',
                    BarCtrl,
                    {
                        'transaction': ('transaction', Transaction),
                        'cache': ('cache', Cache),
                    },
                    bar_ctrl_factory,
                ),
            }
        ),
    },
)

with create_scoped_resolver(scoped_containers) as root_resolver:
    with root_resolver.next_scope() as app_resolver:
        with app_resolver.next_scope() as handler_resolver:
            foo_ctrl = handler_resolver.resolve('foo_ctrl', FooCtrl)
            bar_ctrl = handler_resolver.resolve('bar_ctrl', BarCtrl)

```
