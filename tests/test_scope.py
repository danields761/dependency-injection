from pytest import mark

from dependency_injection.models import Scope

ROOT_SCOPE = Scope('root')
APP_SCOPE = Scope('app', ROOT_SCOPE)
OP_SCOPE = Scope('op', APP_SCOPE)

C2_ROOT_SCOPE = Scope('c2_root')
C2_APP_SCOPE = Scope('c2_app', C2_ROOT_SCOPE)
C2_OP_SCOPE = Scope('c2_op', C2_APP_SCOPE)


@mark.parametrize(
    'left, right, result',
    [
        (ROOT_SCOPE, ROOT_SCOPE, True),
        (ROOT_SCOPE, APP_SCOPE, False),
        (APP_SCOPE, ROOT_SCOPE, False),
        (APP_SCOPE, OP_SCOPE, False),
        (ROOT_SCOPE, OP_SCOPE, False),
        (C2_ROOT_SCOPE, ROOT_SCOPE, False),
        (C2_APP_SCOPE, APP_SCOPE, False),
        (C2_OP_SCOPE, OP_SCOPE, False),
    ]
)
def test_equality(left, right, result):
    comparison_result = left == right
    assert comparison_result == result


