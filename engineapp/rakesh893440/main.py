import os
import webapp2
import jinja2
import logging
import cgi
import datetime
import urllib
import jinja2
import sys
import os
import re
import webapp2
from webapp2 import Route
import os
from jinja2.filters import do_pprint
from engineauth import models
from google.appengine.ext import ndb
from engineauth.middleware import EngineAuthRequest
from webob import Request



from google.appengine.ext import db
from google.appengine.api import images
from google.appengine.api import users
from google.appengine.api import users

template_dir = os.path.join(os.path.dirname(__file__), 'templates')
jinja_env = jinja2.Environment(loader = jinja2.FileSystemLoader(template_dir), autoescape=True)


class Handler(webapp2.RequestHandler):
	def write(self, *a, **kw):
		self.response.out.write(*a, **kw)
		
	def render_str(self, template, **params):
		t = jinja_env.get_template(template)
		return t.render(params)
	def render(self, template, **kw):
		self.write(self.render_str(template, **kw))
	"""def initialize(self, *a, **kw):
		webapp2.RequestHandler.initialize(self, *a, **kw)
		req=EngineAuthRequest(self.read_secure_cookie('_eauth'))
		req._load_session()
		profiles=req._load_user()
		session = self.request.session if self.request.session else None
		user = self.request.user if self.request.user else None
		profiles = None
		if user:
			profile_keys = [ndb.Key('UserProfile', p) for p in user.auth_ids]
			profiles = ndb.get_multi(profile_keys)
		self.profiles = profiles
		"""
class Image(db.Model):
	content=db.StringProperty(multiline=True)
	image = db.BlobProperty()
	date = db.DateTimeProperty(auto_now_add=True)
		
class MainPage(Handler):
	def get(self):
		self.render('fronts.html')
		
routes = [
    Route(r'/login',handler=MainPage),Route(r'/', handler='handlers.PageHandler:root', name='pages-root'),

    # Wipe DS
    Route(r'/tasks/whip-ds', handler='handlers.WipeDSHandler', name='whip-ds'),
    ]		

	
config = {
    'webapp2_extras.sessions': {
        'secret_key': 'wIDjEesObzp5nonpRHDzSp40aba7STuqC6ZRY'
    },
    'webapp2_extras.auth': {
        #        'user_model': 'models.User',
        'user_attributes': ['displayName', 'email'],
        },
    'webapp2_extras.jinja2': {
        'filters': {
            'do_pprint': do_pprint,
            },
        },
    }
	
app = webapp2.WSGIApplication(routes, debug=True,config=config)

