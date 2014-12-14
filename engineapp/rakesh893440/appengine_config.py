import os
ON_DEV = os.environ.get('SERVER_SOFTWARE', '').startswith('Dev')

engineauth = {
    # Login uri. The user will be returned here if an error occures.
    'login_uri': '/', # default 'login/'
    # The user is sent here after successfull authentication.
    'success_uri': '/',
    'secret_key': 'CHANGE_TO_A_SECRET_KEY',
    # Comment out the following lines to use default
    # User and UserProfile models.
    'user_model': 'models.CustomUser',
}

engineauth['provider.google'] = {
    'client_id': '948888594735.apps.googleusercontent.com',
    'client_secret': 'T13SFSvEBi8xIIWuP3eGr4gH',
    'api_key': '',
    'scope': 'https://www.googleapis.com/auth/plus.me',
    }

engineauth['provider.github'] = {
    'client_id': '7c9a74ca5fd7bdb149c2',
    'client_secret': 'a6dbb9f8db8f881290db3bdc32c8f2ac3d5b2535',
    }

engineauth['provider.linkedin'] = {
    'client_id': 'jfsgpazuxzb2',
    'client_secret': 'LxGBTeCpQlb4Ad2R',
    }

engineauth['provider.twitter'] = {
    'client_id': 'l8nfb1saEW4mlTOARqunKg',
    'client_secret': 'LCQweRuuGndhtNWihnwiDxs9npkNRII8GAgpGkYFi5c',
    }


if ON_DEV:
    # Facebook settings for Development
    FACEBOOK_APP_KEY = '364885163603509'
    FACEBOOK_APP_SECRET = 'cbf3c1d192c6bd43db3751b205049139'
else:
    # Facebook settings for Production
    FACEBOOK_APP_KEY = '109551039166233'
    FACEBOOK_APP_SECRET = 'f929abbc0c5092164df693d047f880ec'

engineauth['provider.facebook'] = {
    'client_id': FACEBOOK_APP_KEY,
    'client_secret': FACEBOOK_APP_SECRET,
    'scope': 'email',
    }


def webapp_add_wsgi_middleware(app):
    from engineauth import middleware
    return middleware.AuthMiddleware(app)

