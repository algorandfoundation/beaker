import pytest

from beaker import Application
from tests.conftest import check_application_artifacts_output_stability
from examples.c2c.main import demo, main_app, sub_app


def test_demo() -> None:
    demo()


@pytest.mark.parametrize("app", [sub_app, main_app])
def test_output_stability(app: Application) -> None:
    check_application_artifacts_output_stability(app, dir_per_test_file=False)
