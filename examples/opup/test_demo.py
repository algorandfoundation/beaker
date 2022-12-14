import pytest

from beaker import Application
from examples.opup.contract import ExpensiveApp
from examples.opup.main import demo
from examples.opup.op_up import TargetApp, OpUp
from tests.conftest import check_application_artifacts_output_stability


def test_demo():
    demo()


@pytest.mark.parametrize("app_class", [OpUp, ExpensiveApp, TargetApp])
def test_output_stability(app_class: type[Application]):
    app = app_class()
    check_application_artifacts_output_stability(app)
