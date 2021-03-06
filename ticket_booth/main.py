# TODO
# - Add error handling
# - Add support for SSL
# - Consider implementing a setup.py file
#    - See https://flask.palletsprojects.com/en/2.0.x/tutorial/install/

from flask import Flask, request, jsonify, current_app
from markupsafe import Markup
from jwcrypto import jwt, jwk

from irods.session import iRODSSession
from irods.models import Model
from irods.column import Column, Integer, String
from irods.ticket import Ticket
from irods.api_number import api_number
from irods.message import iRODSMessage, TicketAdminRequest
from irods.exception import CATALOG_ALREADY_HAS_ITEM_BY_THAT_NAME

import json

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

def error_bad_request(msg):
    return (msg, 400)

def error_bad_auth_header():
    return bad_request('Invalid authorization header: missing or incorrect value.')

def make_irods_credentials_dict(username, password):
    return {
        'host': current_app.config['IRODS_HOST'],
        'port': current_app.config['IRODS_PORT'],
        'user': username,
        'password': password,
        'zone': current_app.config['IRODS_ZONE'],
    }

def generate_jwt(data):
    key = jwk.JWK.from_password(current_app.config['IRODS_TICKET_BOOTH_SHARED_SECRET'])
    token = jwt.JWT(header={'alg': current_app.config['IRODS_TICKET_BOOTH_JWT_HASHING_ALGORITHM']}, claims=data)
    token.make_signed_token(key)
    return token.serialize()

    # An encrypted token. This may be helpful in the final implementation.
    #etoken = jwt.JWT(header={'alg': 'A256KW', 'enc': 'A256CBC-HS512'}, claims=token.serialize())
    #etoken.make_encrypted_token(key)
    #return etoken.serialize()

def create_app(config=None):
    app = Flask(__name__)
    app.config.from_object('ticket_booth.config')
    app.config.from_envvar('IRODS_TICKET_BOOTH_CONFIGURATION_FILE', silent=True)

    if config:
        app.config.from_mapping(config)

    @app.route("/create", methods=['POST'])
    def create():
        username = Markup(request.form['username']).unescape()
        password = Markup(request.form['password']).unescape()
        collection = Markup(request.form['collection']).unescape()

        if 'permission' in request.form:
            permission = Markup(request.form['permission']).unescape()
            if permission not in ['read', 'write']:
                return error_bad_request('Invalid query argument: bad ticket permission [{}]'.format(permission))
        else:
            permission = 'read' # Permissions default to 'read'.

        app.logger.info('username=[%s], password=[%s], collection=[%s], permission=[%s]',
            username, password, collection, permission)

        with iRODSSession(**make_irods_credentials_dict(username, password)) as session:
            if not session.collections.exists(collection):
                return error_bad_request('Insufficient permissions: access not allowed to [{}]'.format(collection))

            # Allow up to three attempts for ticket / JWT creation.
            # This improves durability in the face of duplicate ticket strings.
            for i in range(3):
                try:
                    # Generate a ticket with the requested permissions for a collection.
                    # Because the ticket string is generated by the client, it is possible for
                    # the client to hit a duplicate ticket error. Hence, the surrounding for-loop.
                    ticket_handle = Ticket(session)
                    ticket_handle.issue(permission, collection)

                    return generate_jwt({'ticket': ticket_handle.ticket, 'collection': collection})
                
                except CATALOG_ALREADY_HAS_ITEM_BY_THAT_NAME:
                    pass

        return error_bad_request('Could not create JWT for collection [{}]. Try again.'.format(collection))

    # This API needs more investigation. Until we know the use-cases around it, it
    # will remain commented out.
    #@app.route("/resolve/<token>")
    #def resolve(token):
    #    app.logger.info('token = [%s]', token)
    #
    #    # Extract the payload from the JWT and return it.
    #    key = jwk.JWK.from_password(app.config['IRODS_TICKET_BOOTH_SHARED_SECRET'])
    #    payload = jwt.JWT(key=key, jwt=token)
    #    app.logger.info('JWT claims = [%s]', payload.claims)
    #
    #    return payload.claims

    @app.route("/list", methods=['POST'])
    def list():
        username = Markup(request.form['username']).unescape()
        password = Markup(request.form['password']).unescape()

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

    @app.route("/revoke/<token>", methods=['POST'])
    def revoke(token):
        username = Markup(request.form['username']).unescape()
        password = Markup(request.form['password']).unescape()

        # Extract the ticket from the JWT.
        key = jwk.JWK.from_password(app.config['IRODS_TICKET_BOOTH_SHARED_SECRET'])
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

    return app

