
import pytest


# STEP 1: Create a reusable synthetic database result.
@pytest.fixture
def revenue_data():
    return {
        "op": 125000,
        "ip": 340000,
        "hospital": "Demo Hospital"
    }


# STEP 2: Test the fixture.
def test_op_revenue(revenue_data):
    # TODO 1: Verify OP revenue equals 125000
    assert revenue_data["op"] == 125000



def test_ip_revenue(revenue_data):
    # TODO 2: Verify IP revenue equals 340000.
    assert revenue_data["ip"] == 340000
        


def test_hospital_name(revenue_data):
    # TODO 3: Verify hospital name equals "Demo Hospital".
    assert revenue_data["hospital"] == "Demo Hospital"
