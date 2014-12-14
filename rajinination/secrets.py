# Copy this file into secrets.py and set keys, secrets and scopes.

# This is a session secret key used by webapp2 framework.
# Get 'a random and long string' from here: 
# http://clsc.net/tools/random-string-generator.php
# or execute this from a python shell: import os; os.urandom(64)

import os
import logging
CURRENT_VERSION_ID = os.environ.get('CURRENT_VERSION_ID', None)
if os.environ.get('SERVER_SOFTWARE', '').startswith('Google App Engine'):
  DEVELOPMENT = False
else:
  DEVELOPMENT = True

PRODUCTION = not DEVELOPMENT
DEBUG = DEVELOPMENT


logging.error(DEVELOPMENT)

SESSION_KEY = "a very long and secret session key goes here asjhgsd kjagshfhjsd jhgsad"

def devorprod(envi,devid,prodid):
	if envi==True:
		logging.error(devid)
		return devid
	else:
		logging.error(prodid)
		return prodid

# Google APIs
Google_app_id_dev='948888594735.apps.googleusercontent.com'
Google_app_secret_dev= 'T13SFSvEBi8xIIWuP3eGr4gH'
Google_app_id_prod= '948888594735-gejkj2btlsj9b3b82cepto7g9l55p9l3.apps.googleusercontent.com'
Google_app_secret_prod= 'CQ4xHsrneb8U3ph05wQpC8ek'

GOOGLE_APP_ID = devorprod(DEVELOPMENT,Google_app_id_dev,Google_app_id_prod)
GOOGLE_APP_SECRET = devorprod(DEVELOPMENT,Google_app_secret_dev,Google_app_secret_prod)

# Facebook auth apis
Facebook_app_id_dev='364885163603509'
Facebook_app_secret_dev= 'cbf3c1d192c6bd43db3751b205049139'
Facebook_app_id_prod='332104320221141'
Facebook_app_secret_prod='5d0ffb92c09e5928d531536296fd8f0b'


FACEBOOK_APP_ID = devorprod(DEVELOPMENT,Facebook_app_id_dev,Facebook_app_id_prod)
FACEBOOK_APP_SECRET = devorprod(DEVELOPMENT,Facebook_app_secret_dev,Facebook_app_secret_prod)

# https://www.linkedin.com/secure/developer
LINKEDIN_CONSUMER_KEY = 'consumer key'
LINKEDIN_CONSUMER_SECRET = 'consumer secret'

# https://manage.dev.live.com/AddApplication.aspx
# https://manage.dev.live.com/Applications/Index
WL_CLIENT_ID = 'client id'
WL_CLIENT_SECRET = 'client secret'

# https://dev.twitter.com/apps
TWITTER_CONSUMER_KEY = 'az4LcRE2cXQOMWFpLurg'
TWITTER_CONSUMER_SECRET = 'T9l3gfq7I0G5ronzvBjF8T9fAq9ChhJsLJywSnAYs'

# config that summarizes the above
AUTH_CONFIG = {
  # OAuth 2.0 providers
  'google'      : (GOOGLE_APP_ID, GOOGLE_APP_SECRET,
                  'https://www.googleapis.com/auth/userinfo.profile'),
  'facebook'    : (FACEBOOK_APP_ID, FACEBOOK_APP_SECRET,
                  'user_about_me'),
  'windows_live': (WL_CLIENT_ID, WL_CLIENT_SECRET,
                  'wl.signin'),

  # OAuth 1.0 providers don't have scopes
  'twitter'     : (TWITTER_CONSUMER_KEY, TWITTER_CONSUMER_SECRET),
  'linkedin'    : (LINKEDIN_CONSUMER_KEY, LINKEDIN_CONSUMER_SECRET),

  # OpenID doesn't need any key/secret
}


error_templates = {
    404: 'error404.html',
    500: 'error404.html',
}


email='thalaivar@rajinination.com'
secretpassword='thalaivar!'
deletepassword='thala'
pagesize=10

max_i_width=750
max_i_height=2000