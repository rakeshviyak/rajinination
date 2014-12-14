import os
import webapp2
import jinja2
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
		
class MainHandler(webapp2.RequestHandler):
    def get(self):
		self.response.headers['Content-Type']='test/plain'
		visits=self.request.cookies.get('visits',0)
		self.write("You here %s !!",%visits)

app = webapp2.WSGIApplication([('/', MainHandler)],
                              debug=True)
