import os
import webapp2
import jinja2
import logging
import cgi
import datetime
import urllib


from google.appengine.ext import db
from google.appengine.api import images
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
		
class Image(db.Model):
	content=db.StringProperty(multiline=True)
	image = db.BlobProperty()
	date = db.DateTimeProperty(auto_now_add=True)
		
class MainPage(Handler):
	def render_blog(self):
		self.response.out.write('<html><body>')
		images = db.GqlQuery("SELECT * FROM Image ORDER BY date DESC limit 5")
		for image in images:
			self.response.out.write('<div><img src="img?img_id=%s"></img>' %image.key())
		self.response.out.write("""
			<form enctype="multipart/form-data" method="post">
                <div><textarea name="content" rows="3" cols="60"></textarea></div>
                <div><label>Avatar:</label></div>
                <div><input type="file" name="img"/></div>
                <div><input type="submit" value="Sign Guestbook"></div>
            </form>
            </body>
          </html>""")
			
	def get(self):
		self.render_blog()
	
	def post(self):
		image=Image()
		image.content = self.request.get('content')
		avatar = images.resize(self.request.get('img'), 500, 500)
		image.image = db.Blob(avatar)
		image.put()
		self.redirect('/')
		
class ImagePage(webapp2.RequestHandler):
    def get(self,img_id):
		#images = Image.get_by_id(int(img_id))
		key = db.Key.from_path('Image', int(img_id))
		images = db.get(key)
		#images=Image.get_key().get_by_id(int(imd_id))
		logging.error(images)
		self.response.out.write('<div><img src="/img?img_id=%s"></img>' %images.key())
		
class ImageHandler(webapp2.RequestHandler):
    def get(self):
        image = db.get(self.request.get('img_id'))
        if image.image:
            self.response.headers['Content-Type'] = 'image/png'
            self.response.out.write(image.image)
        else:
            self.response.out.write('No image')
		

app = webapp2.WSGIApplication([('/', MainPage),('/img',ImageHandler),('/img/([0-9]+)', ImagePage)], debug=True)