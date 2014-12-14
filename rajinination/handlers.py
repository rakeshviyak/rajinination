# -*- coding: utf-8 -*-
import logging
import secrets
import main
import webapp2
from webapp2_extras import auth, sessions, jinja2
from jinja2.runtime import TemplateNotFound

from simpleauth import SimpleAuthHandler


class RootHandler(main.BlogHandler):
  def get(self):
    
    self.render('login.html', {'html_class': "Login"})

class UserNameHandler(main.BlogHandler):
  def get(self):
    """Handles default langing page"""
    self.render('layout.html')

    
class ProfileHandler(main.BlogHandler):
	def get(self):
		logging.info(self.auth.get_user_by_session())
		"""Handles GET /profile"""
		logging.error(self.logged_in)
		if self.logged_in:
			logging.error(self.auth.get_user_by_session())
			logging.error(self.current_user)
			self.render('profile.html', {
						'user': self.current_user, 
						'session': self.auth.get_user_by_session(),
						'html_class':"Profile"
						})
		else:
			logging.error(self.auth.get_user_by_session())
			logging.error(self.current_user)
			self.redirect('/')


class AuthHandler(main.BlogHandler, SimpleAuthHandler):
  """Authentication handler for OAuth 2.0, 1.0(a) and OpenID."""

  # Enable optional OAuth 2.0 CSRF guard
  OAUTH2_CSRF_STATE = True
  
  USER_ATTRS = {
    'facebook' : {
      'id'     : lambda id: ('avatar_url', 
        'http://graph.facebook.com/{0}/picture?type=large'.format(id)),
      'name'   : 'name',
      'link'   : 'link',
	  'email'  : 'email'
    },
    'google'   : {
      'picture': 'avatar_url',
      'name'   : 'name',
      'link'   : 'link',
	  'emails' : 'email'
    },
    'windows_live': {
      'avatar_url': 'avatar_url',
      'name'      : 'name',
      'link'      : 'link'
    },
    'twitter'  : {
      'profile_image_url': 'avatar_url',
      'screen_name'      : 'name',
      'link'             : 'link'
    },
    'linkedin' : {
      'picture-url'       : 'avatar_url',
      'first-name'        : 'name',
      'public-profile-url': 'link'
    },
    'openid'   : {
      'id'      : lambda id: ('avatar_url', '/img/missing-avatar.png'),
      'nickname': 'name',
      'email'   : 'link'
    }
  }
  
  def _on_signin(self, data, auth_info, provider):
	"""Callback whenever a new or existing user is logging in.data is a user info dictionary.auth_info contains access token or oauth token and secret.
	 """
	auth_id = '%s:%s' % (provider, data['id'])
	logging.info('Looking for a user with id %s', auth_id)
	user = self.auth.store.user_model.get_by_auth_id(auth_id)
	_attrs = self._to_user_model_attrs(data, self.USER_ATTRS[provider])
	logging.error(_attrs)
	logging.error(user)
	if user:
		logging.info('Found existing user to log in')
		user.populate(**_attrs)
		user.put()
		logging.error(user.put())
		
		self.auth.set_session(self.auth.store.user_to_dict(user))
		
		logging.error(self.auth.get_user_by_session())
		
		# Existing users might've changed their profile data so we update our
		# local model anyway. This might result in quite inefficient usage
		# of the Datastore, but we do this anyway for demo purposes.
		#
		# In a real app you could compare _attrs with user's properties fetched
		# from the datastore and update local user in case something's changed.
	else:
		# check whether there's a user currently logged in
		# then, create a new user if nobody's signed in, 
		# otherwise add this auth_id to currently logged in user.
		if self.logged_in:
			logging.info('Updating currently logged in user')
			u = self.current_user
			u.populate(**_attrs)
			# The following will also do u.put(). Though, in a real app
			# you might want to check the result, which is
			# (boolean, info) tuple where boolean == True indicates success
			# See webapp2_extras.appengine.auth.models.User for details.
			u.add_auth_id(auth_id)
		else:
			logging.info('Creating a brand new user')
			ok, user = self.auth.store.user_model.create_user(auth_id, **_attrs)
			logging.error(auth_id)
			logging.error(ok)
			logging.error(user)
			if ok:
				self.auth.set_session(self.auth.store.user_to_dict(user))

    # Remember auth data during redirect, just for this demo. You wouldn't
    # normally do this.
	logging.error(data)
	logging.error(auth_info)
	
	self.session.add_flash(data, 'data - from _on_signin(...)')
	
	self.session.add_flash(auth_info, 'auth_info - from _on_signin(...)')
	
	self.session.add_flash("login sucess",key='logininfo')
	logging.error(self.auth.get_user_by_session())
	
	logging.error(self.read_secure_cookie('url'))
	# Go to the profile page
	
	self.redirect(str(self.read_secure_cookie('url')))

  def logout(self):
	self.auth.unset_session()
	self.session.add_flash("logout sucess",key='logoutinfo')
	self.redirect(str(self.read_secure_cookie('url')))

  def handle_exception(self, exception, debug):
    logging.error(exception)
    self.render('error.html', {'exception': exception})
    
  def _callback_uri_for(self, provider):
    return self.uri_for('auth_callback',provider=provider, _full=True)
    
  def _get_consumer_info_for(self, provider):
	"""Returns a tuple (key, secret) for auth init requests."""
	logging.error(secrets.AUTH_CONFIG[provider])
	return secrets.AUTH_CONFIG[provider]
    
  def _to_user_model_attrs(self, data, attrs_map):
    """Get the needed information from the provider dataset."""
    user_attrs = {}
    for k, v in attrs_map.iteritems():
      attr = (v, data.get(k)) if isinstance(v, str) else v(data.get(k))
      user_attrs.setdefault(*attr)

    return user_attrs
