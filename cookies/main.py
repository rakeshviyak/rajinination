import os
import webapp2
import jinja2
import re
from google.appengine.ext import db
import hashlib
import hmac
import random
import string

template_dir = os.path.join(os.path.dirname(__file__), 'templates')
jinja_env = jinja2.Environment(loader = jinja2.FileSystemLoader(template_dir), autoescape=True)

USER_RE = re.compile(r"^[a-zA-Z0-9_-]{3,20}$")
PASS_RE = re.compile(r"^.{3,20}$")
EMAIL_RE = re.compile(r"^[\S]+@[\S]+\.[\S]+$")

error_username=""
error_password=""
error_verify=""
error_email=""

class User_info(db.Model):
	username = db.StringProperty(required = True)
	password = db.StringProperty(required = True)
	email=db.StringProperty(required=False)
	created = db.DateTimeProperty(auto_now_add = True)

def valid_username(username):
	return USER_RE.match(username)

def valid_password(password):
	return PASS_RE.match(password)

def valid_email(email):
	if len(email)>0:
		return EMAIL_RE.match(email)

def make_salt():
	return ''.join(random.choice(string.letters) for x in xrange(5))

def make_pw_hash(name, pw, salt=None):
	if not salt:
		salt=make_salt()
	h = hashlib.sha256(name + pw + salt).hexdigest()
	return '%s,%s' % (h, salt)

def valid_pw(name, pw, h):
	salt = h.split(',')[1]
	return h == make_pw_hash(name, pw, salt)

def hash_str(s):
	return hashlib.md5(s).hexdigest()

def make_secure_val(s):
	return "%s|%s" % (s, hash_str(s))

def check_secure_val(h):
	val = h.split('|')[0]
	if h == make_secure_val(val):
		return val

def verify_login(username,password):
	query=db.GqlQuery("SELECT * from User_info where username = :1",username)
	for q in query:
		userpass=q.password
		a=valid_pw(username,password,userpass)
		if a:
			return q.username
	
class Handler(webapp2.RequestHandler):
	def write(self, *a, **kw):
		self.response.out.write(*a, **kw)
	def render_str(self, template, **params):
		t = jinja_env.get_template(template)
		return t.render(params)
	def render(self, template, **kw):
		self.write(self.render_str(template, **kw))

class WelcomePage(Handler):
	def render_welcome(self,username=""):
		self.render("welcome.html",username=username)
	def get(self):
		user_cookie_str = self.request.cookies.get('user')
		if user_cookie_str:
			cookie_val = check_secure_val(user_cookie_str)
			if cookie_val:
				username = str(cookie_val)
				self.render_welcome(username)
			else:
				self.redirect("/signup")

class LogoutPage(Handler):
	def get(self):
		user_cookie_str = self.request.cookies.get('user')
		clr_cookie=" "
		self.response.headers.add_header('Set-Cookie', 'user=%s; Path=/welcome' %clr_cookie)
		self.redirect("/signup")
				
class LoginPage(Handler):
	def render_login(self,username="",login_error=""):
		self.render("login.html",username=username,login_error=login_error)
	def get(self):
		self.render_login()
	def post(self):
		username=self.request.get('username')
		password=self.request.get('password')
		ve_username=valid_username(username)
		ve_password=valid_password(password)
		error_login=""
		log=verify_login(username,password)
		#self.response.out.write(log)
		if log:
			cookie_user=make_secure_val(str(log))
			self.response.headers.add_header('Set-Cookie', 'user=%s; Path=/welcome' %cookie_user)
			self.redirect("/welcome")
		else:
			error_login="Invalid Login"
			self.render_login(username,error_login)	

class MainPage(Handler):
	def render_signup(self,username="",email="",error_username="",error_password="",error_verify="",error_email=""):
		self.render("signup.html",username=username,email=email,error_username=error_username,error_password=error_password,error_verify=error_verify,error_email=error_email)
	def get(self):
		self.render_signup()
	def post(self):
		username=self.request.get('username')
		password=self.request.get('password')
		verify=self.request.get('verify')
		email=self.request.get('email')
		
		ve_username=valid_username(username)
		ve_password=valid_password(password)
		ve_verify=valid_password(verify)
		ve_email=valid_email(email)
		
		error_username=""
		error_password=""
		error_verify=""
		error_email=""
		if not(ve_username):
			error_username="That's not a valid username."
		if not(ve_password or ve_verify):
			error_password="That wasn't a valid password."
		if not(ve_email) and len(email)!=0:
			error_email="That's not a valid email."
		if ve_password and password!=verify:
			error_verify="Your passwords didn't match."
		if ve_password and ve_verify and password==verify and ve_username and (ve_email or len(email)==0):
			se_password=make_pw_hash(username,password)
			user_table=User_info(username=username,password=se_password,email=email)
			user_table.put()
			cookie_user=make_secure_val(str(username))
			self.response.headers.add_header('Set-Cookie', 'user=%s; Path=/welcome' %cookie_user)
			self.redirect("/welcome")
		else:
			self.render_signup(username,email,error_username,error_password,error_verify,error_email)

		
app = webapp2.WSGIApplication([('/signup', MainPage),('/welcome',WelcomePage),('/login',LoginPage),('/logout',LogoutPage)], debug=True)