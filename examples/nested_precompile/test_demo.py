from tests.conftest import check_application_artifacts_output_stability

from examples.nested_precompile.main import demo
from examples.nested_precompile.nested_application import grand_parent_app


def test_demo() -> None:
    demo()


def test_output_stability() -> None:
    check_application_artifacts_output_stability(
        grand_parent_app, dir_per_test_file=False
    )
