import os
import webapp2
import jinja2
import logging
import re
import sys
import urllib2
from xml.dom import minidom
from google.appengine.ext import db
from google.appengine.api import memcache

template_dir = os.path.join(os.path.dirname(__file__), 'templates')
jinja_env = jinja2.Environment(loader = jinja2.FileSystemLoader(template_dir), autoescape=True)

GMAPS_URL = "http://maps.googleapis.com/maps/api/staticmap?size=380x263&sensor=false&"
def gmap_img(points):
        markers = '&'.join('markers=%s,%s' % (p.lat, p.lon) for p in points)
        return GMAPS_URL + markers


IP_URL  = "http://api.hostip.info/?ip="
def get_coords(ip):
        ip = "4.2.2.2"
        url = IP_URL + ip
        content = None
        try:
                content = urllib2.urlopen(url).read()
        except urllib2.URLError:
                return

        if content:
                d = minidom.parseString(content)
                coords = d.getElementsByTagName("gml:coordinates")
                if coords and coords[0].childNodes[0].nodeValue:
                        lon, lat = coords[0].childNodes[0].nodeValue.split(',')
                        return db.GeoPt(lat, lon)

class Handler(webapp2.RequestHandler):
    def write(self, *a, **kw):
        self.response.out.write(*a, **kw)
    def render_str(self, template, **params):
        t = jinja_env.get_template(template)
        return t.render(params)
    def render(self, template, **kw):
        self.write(self.render_str(template, **kw))
		
class Art(db.Model):
	title = db.StringProperty(required = True)
	art = db.TextProperty(required = True)
	created = db.DateTimeProperty(auto_now_add = True)
	coords = db.GeoPtProperty( )


def top_arts(update=False):
	key='top'
	arts=memcache.get(key)
	if arts is None or update:
		logging.error("DB QUERY")
		arts = db.GqlQuery("SELECT * FROM Art ORDER BY created DESC")
		arts = list(arts)
		memcache.set(key,arts)
	return arts
	
class MainPage(Handler):
	def render_front(self,error="",title="",art=""):
		
		#prevent the running of multiple queries
                arts = top_arts()

                #find which arts have coords
                img_url = None
                points = filter(None, (a.coords for a in arts))
                if points:
                        img_url = gmap_img(points)

                #display the image URL

                self.render("front.html", title = title, art = art, error = error, arts = arts, img_url = img_url)
		
		self.render("front.html",error=error,title=title,art=art,arts=arts)
	def get(self):
		self.write(self.request.remote_addr)
		self.write(repr(get_coords(self.request.remote_addr)))
		self.render_front()
	def post(self):
		title = self.request.get("title") 
		art = self.request.get("art")
		if title and art:
			a=Art(title=title,art=art)
			coords = get_coords(self.request.remote_addr)
                        #if we have coordinates, add them to the art
                        if coords:
                                a.coords = coords
			a.put()
			top_arts(update="True")
			self.redirect("/")
		else:
			error="bitch fill correctly"
			self.render_front(error,title,art)
	
app = webapp2.WSGIApplication([('/', MainPage)], debug=True)