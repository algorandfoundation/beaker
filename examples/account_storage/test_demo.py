from examples.account_storage.main import demo, DiskHungry
from tests.conftest import check_application_artifacts_output_stability


def test_demo():
    demo()


def test_output_stability():
    app = DiskHungry()
    check_application_artifacts_output_stability(app)
