# TODO
# - Add error handling
# - Externalize configuration
# - Add support for SSL

from flask import Flask, request, jsonify
from markupsafe import Markup
from jwcrypto import jwt, jwk

from irods.session import iRODSSession
from irods.models import Model
from irods.column import Column, Integer, String
from irods.ticket import Ticket
from irods.api_number import api_number
from irods.message import iRODSMessage, TicketAdminRequest

import base64
import json

app = Flask(__name__)

IRODS_TICKET_BOOTH_SHARED_SECRET = 'THIS IS A SHARED SECRET!'

# TODO Port this to the PRC.
#
# The PRC does not have GenQuery support for tickets. Defining the following class
# enables this, but only for the columns of interest.
#
# See the following for additional details:
#   - https://github.com/irods/python-irodsclient/blob/master/irods/models.py
#   - https://github.com/irods/python-irodsclient/blob/master/irods/ticket.py
#   - https://groups.google.com/g/iROD-Chat/c/gVfxH1Nn3Xc/m/EB1YchTOAAAJ
#   - https://github.com/irods/python-irodsclient/commit/efd1c7495f454242dce81f03e598741cfabd955b#diff-371634f3c7d0926eb7a5118ddef62e79ee9ef2b3e12f893cc49cbe4033e7d270
class GenQueryTicket(Model):
    id              = Column(Integer, 'TICKET_ID',        2200)
    string          = Column(String,  'TICKET_STRING',    2201)
    type            = Column(String,  'TICKET_TYPE',      2202)
    collection_name = Column(String,  'TICKET_COLL_NAME', 2228)

def get_username_and_password(auth_header):
    # Remove the "Basic " prefix.
    auth_header = request.headers.get('authorization')[6:]
    app.logger.info('auth header = [%s]', auth_header)

    username, password = base64.b64decode(auth_header).decode('utf-8').split(':')
    app.logger.info('username = [%s], password = [%s]', username, password)

    return username, password

def make_irods_credentials_dict(username, password):
    return {
        'host': 'localhost',
        'port': 1247,
        'user': username,
        'password': password,
        'zone': 'tempZone'
    }

def generate_token(data):
    #key = jwk.JWK(generate='oct', size=256)
    key = jwk.JWK.from_password(IRODS_TICKET_BOOTH_SHARED_SECRET)

    token = jwt.JWT(header={'alg': 'HS256'}, claims=data)
    token.make_signed_token(key)
    return token.serialize()

    # An encrypted token. This may be helpful in the final implementation.
    #etoken = jwt.JWT(header={'alg': 'A256KW', 'enc': 'A256CBC-HS512'}, claims=token.serialize())
    #etoken.make_encrypted_token(key)
    #return etoken.serialize()

@app.route("/create")
def create():
    if 'authorization' not in request.headers:
        return 'Authorization header is not set.'

    username, password = get_username_and_password(request.headers.get('authorization'))

    if 'collection' not in request.args:
        return '"collection" argument is not set.'

    # Verify that the collection exists.
    collection = Markup(request.args.get('collection', '')).unescape()
    app.logger.info('collection = [%s]', collection)

    # Permissions default to 'read'.
    permission = 'read'
    if 'permission' in request.args:
        permission = Markup(request.args.get('permission', '')).unescape()
        if permission not in ['read', 'write']:
            return 'Invalid ticket permission [{}]'.format(permission)

    with iRODSSession(**make_irods_credentials_dict(username, password)) as session:
        if not session.collections.exists(collection):
            return "Collection does not exist or user does not have permission to access the collection"

        # Generate a ticket with the requested permissions for a collection.
        # TODO What happens if the ticket matches a preexisting token?
        ticket_handle = Ticket(session)
        ticket_handle.issue(permission, collection)

        # Generate a JWT containing the ticket and the collection associated with
        # the ticket.
        return generate_token({'ticket': ticket_handle.ticket, 'collection': collection})

@app.route("/resolve/<token>")
def resolve(token):
    app.logger.info('token = [%s]', token)

    # Extract the payload from the JWT and return it.
    key = jwk.JWK.from_password(IRODS_TICKET_BOOTH_SHARED_SECRET)
    payload = jwt.JWT(key=key, jwt=token)
    app.logger.info('JWT claims = [%s]', payload.claims)

    return payload.claims

@app.route("/list")
def list():
    if 'authorization' not in request.headers:
        return 'Authorization header is not set'

    username, password = get_username_and_password(request.headers.get('authorization'))
    matches = []

    # Lookup all ticket information.
    with iRODSSession(**make_irods_credentials_dict(username, password)) as session:
        for row in session.query(GenQueryTicket.string, GenQueryTicket.type, GenQueryTicket.collection_name):
            matches.append({
                'ticket': row[GenQueryTicket.string],
                'collection': row[GenQueryTicket.collection_name],
                'permission': row[GenQueryTicket.type]
            })

    return jsonify(matches)

@app.route("/revoke/<token>")
def revoke(token):
    app.logger.info('token = [%s]', token)

    if 'authorization' not in request.headers:
        return 'Authorization header is not set'

    username, password = get_username_and_password(request.headers.get('authorization'))

    # Extract the ticket from the JWT.
    key = jwk.JWK.from_password(IRODS_TICKET_BOOTH_SHARED_SECRET)
    payload = jwt.JWT(key=key, jwt=token)
    ticket = json.loads(payload.claims)['ticket']

    # Delete the ticket from iRODS.
    with iRODSSession(**make_irods_credentials_dict(username, password)) as session:
        msg_body = TicketAdminRequest('delete', ticket)
        msg = iRODSMessage('RODS_API_REQ', msg=msg_body, int_info=api_number['TICKET_ADMIN_AN'])

        with session.pool.get_connection() as conn:
            conn.send(msg)
            response = conn.recv()

    return 'OK'

