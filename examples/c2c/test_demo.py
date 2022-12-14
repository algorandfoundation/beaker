import pytest

from beaker import Application
from tests.conftest import check_application_artifacts_output_stability
from examples.c2c.main import demo, C2CMain, C2CSub


def test_demo():
    demo()


@pytest.mark.parametrize("app_class", [C2CMain, C2CSub])
def test_output_stability(app_class: type[Application]):
    app = app_class()
    check_application_artifacts_output_stability(app)
