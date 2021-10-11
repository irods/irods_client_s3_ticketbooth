import ssl

# The iRODS server to connect to.
IRODS_HOST = 'localhost'
IRODS_PORT = 1247
IRODS_ZONE = 'tempZone'

# The shared secret used to generate the JWT.
IRODS_TICKET_BOOTH_SHARED_SECRET = 'THIS IS THE SHARED SECRET'

# The hashing algorithm used to generate the JWT.
IRODS_TICKET_BOOTH_JWT_HASHING_ALGORITHM = 'HS256'

# SSL
#IRODS_TICKET_BOOTH_SSL_PURPOSE = ssl.Purpose.SERVER_AUTH
#IRODS_TICKET_BOOTH_SSL_CA_FILE = None
#IRODS_TICKET_BOOTH_SSL_CA_PATH = None
#IRODS_TICKET_BOOTH_SSL_CA_DATA = None
