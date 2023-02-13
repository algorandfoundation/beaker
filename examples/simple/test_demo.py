import pytest

from beaker import Application
from examples.simple.calculator import calculator_app
from examples.simple.calculator import demo as calc_demo
from examples.simple.counter import counter_app
from examples.simple.counter import demo as count_demo
from examples.simple.decorators import external_example_app
from examples.simple.hello import demo as hello_demo
from examples.simple.hello import hello_app
from tests.conftest import check_application_artifacts_output_stability


def test_calc() -> None:
    calc_demo()


def test_count() -> None:
    count_demo()


def test_hello() -> None:
    hello_demo()


@pytest.mark.parametrize(
    "app", [calculator_app, counter_app, hello_app, external_example_app]
)
def test_output_stability(app: Application) -> None:
    check_application_artifacts_output_stability(app, dir_per_test_file=False)
