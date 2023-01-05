from tests.conftest import check_application_artifacts_output_stability
from .main import demo
from .nested_application import Grandparent


def test_demo():
    demo()


def test_output_stability():
    app = Grandparent()
    check_application_artifacts_output_stability(app)
