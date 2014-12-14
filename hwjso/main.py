import os
import webapp2
import jinja2
import sys
import re
import urllib2
import json
import time 
from datetime import datetime
from xml.dom import minidom
from google.appengine.ext import db

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
	
		
class Blog(db.Model):
    title = db.StringProperty(required = True)
    blog = db.TextProperty(required = True)
    created = db.DateTimeProperty(auto_now_add = True)
		
class MainPage(Handler):
	def render_blog(self):
		blogs = db.GqlQuery("SELECT * FROM Blog ORDER BY created DESC limit 5")
		self.render("home.html",blogs=blogs)
	def get(self):
		self.render_blog()

class JsonMainPage(Handler):
	def get(self):
		blogs = db.GqlQuery("SELECT * FROM Blog")
		d={}
		for blog in blogs:
			datetimestr = blog.created
			timestr=datetimestr.strftime("%Y-%m-%d %H:%M:%S")
			d.update({"title":blog.title,"blog":blog.blog,"created":timestr})
		jsondumps=json.dumps(d)
		self.render("json.html",jsondumps=jsondumps,mimetype = 'application/json')
		#self.response.headers['Content-Type'] = 'application/json'		
		
class Newpost(Handler):
	def render_newpost(self,error="",title="",blog=""):
		self.render("index.html",error=error,title=title,blog=blog)
	def get(self):
		self.render_newpost()
	def post(self):
		title = self.request.get("title") 
		blog = self.request.get("blog")
		if title and blog:
			a=Blog(title=title,blog=blog)
			a.put()
			blog_id=int(a.key().id())
			blog_address="/blog/"+ str(blog_id)
			self.redirect(blog_address)
		else:
			error="bitch fill correctly"
			self.render_newpost(error,title,blog)
			
class JsonHandler(MainPage):
	def get(self,blog_id):
		blogs = Blog.get_by_id(int(blog_id))
		d={}
		datetimestr = blogs.created
		timestr=datetimestr.strftime("%Y-%m-%d %H:%M:%S")
		d={"title":blogs.title,"blog":blogs.blog,"created":timestr}
		jsondumps=json.dumps(d)
		self.render("json.html",jsondumps=jsondumps,mimetype = 'application/json')
		#self.response.headers['Content-Type'] = 'application/json'		
		
class PostHandler(MainPage):
		def get(self, blog_id):
			blogs = Blog.get_by_id(int(blog_id))
			self.render("post.html", blogs=blogs)

app = webapp2.WSGIApplication([('/blog', MainPage),('/blog.json', JsonMainPage),('/blog/newpost',Newpost),('/blog/(\d+)',PostHandler),('/blog/(\d+).json',JsonHandler)], debug=True)	