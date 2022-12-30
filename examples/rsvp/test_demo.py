from .demo import demo
from .contract import EventRSVP
from tests.conftest import check_application_artifacts_output_stability


def test_demo():
    demo()


def test_output_stability():
    app = EventRSVP()
    check_application_artifacts_output_stability(app)
