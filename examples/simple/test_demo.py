import pytest

from beaker import Application
from examples.simple.calculator import Calculator
from examples.simple.calculator import demo as calc_demo
from examples.simple.counter import counter_app
from examples.simple.counter import demo as count_demo
from examples.simple.decorators import ExternalExample
from examples.simple.hello import demo as hello_demo
from examples.simple.hello import hello_app
from tests.conftest import check_application_artifacts_output_stability


def test_calc():
    calc_demo()


def test_count():
    count_demo()


def test_hello():
    hello_demo()


@pytest.mark.parametrize(
    "app", [Calculator(), counter_app, hello_app, ExternalExample()]
)
def test_output_stability(app: Application):
    check_application_artifacts_output_stability(app, dir_per_test_file=False)
