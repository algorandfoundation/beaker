from tests.conftest import check_application_artifacts_output_stability
from .main import demo
from .nested_application import grand_parent_app


def test_demo():
    demo()


def test_output_stability():
    check_application_artifacts_output_stability(
        grand_parent_app, dir_per_test_file=False
    )
