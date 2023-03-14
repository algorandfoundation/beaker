from tests.conftest import check_application_artifacts_output_stability

from examples.nested_precompile import demo
from examples.nested_precompile.smart_contracts import grandparent


def test_demo() -> None:
    demo.main()


def test_output_stability() -> None:
    check_application_artifacts_output_stability(
        grandparent.app, dir_per_test_file=False
    )
