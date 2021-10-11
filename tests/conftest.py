import pytest

from ticket_booth.main import create_app

@pytest.fixture
def client():
    return create_app({'TESTING': True}).test_client()

