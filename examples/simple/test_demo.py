import pytest

from beaker import Application

from tests.conftest import check_application_artifacts_output_stability

from examples.simple import calculator, counter, decorators, hello


def test_calc() -> None:
    calculator.demo()


def test_count() -> None:
    counter.demo()


def test_hello() -> None:
    hello.demo()


def test_decorators() -> None:
    decorators.demo()


@pytest.mark.parametrize(
    "app",
    [
        calculator.calculator_app,
        counter.counter_app,
        hello.hello_app,
        decorators.external_example_app,
    ],
)
def test_output_stability(app: Application) -> None:
    check_application_artifacts_output_stability(app, dir_per_test_file=False)
