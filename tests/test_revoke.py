def test_revoke(client):
    data = {
        'username': 'kory',
        'password': 'rods',
        'collection': '/tempZone/home/kory'
    }

    response = client.post('/create', data=data)
    assert response.status_code == 200

    token = response.get_data(as_text=True)

    response = client.post('/revoke/' + token, data=data)
    assert response.status_code == 200

    response = client.post('/list', data=data)
    assert response.status_code == 200
    assert '[]' == response.get_data(as_text=True).strip()

