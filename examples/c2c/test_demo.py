import pytest

import beaker

from tests.conftest import check_application_artifacts_output_stability

from examples.c2c import c2c_main, c2c_sub, demo


def test_demo() -> None:
    demo.main()


@pytest.mark.parametrize("app", [c2c_main.app, c2c_sub.app])
def test_output_stability(app: beaker.Application) -> None:
    check_application_artifacts_output_stability(app, dir_per_test_file=False)
