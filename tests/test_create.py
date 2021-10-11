import pytest

@pytest.mark.parametrize(('expected_permission'), (
    ('read'),
    ('write')
))

def test_create(client, expected_permission):
    data = {
        'username': 'kory',
        'password': 'rods',
        'collection': '/tempZone/home/kory',
        'permission': expected_permission
    }

    response = client.post('/create', data=data)
    assert response.status_code == 200
    assert len(response.get_data(as_text=True)) > 0

    token = response.get_data(as_text=True)

    response = client.post('/list', data=data)
    assert response.status_code == 200
    assert '"permission":"{}"'.format(expected_permission) in response.get_data(as_text=True)

    response = client.post('/revoke/' + token, data=data)
    assert response.status_code == 200

    response = client.post('/list', data=data)
    assert response.status_code == 200
    assert '[]' == response.get_data(as_text=True).strip()

def test_invalid_argument(client):
    data = {
        'username': 'kory',
        'password': 'rods',
        'collection': '/tempZone/home/kory',
        'permission': 'invalid argument'
    }

    response = client.post('/create', data=data)
    assert response.status_code == 400

    response = client.post('/list', data=data)
    assert response.status_code == 200
    assert '[]' == response.get_data(as_text=True).strip()

