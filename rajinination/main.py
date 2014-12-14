#!/usr/bin/env python
#
# Copyright 2007 Google Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#

import os
import re
import random
import hashlib
import hmac
import logging
import cgi
import datetime
import sys
from string import letters
import ndbpager
import json
import StringIO
import textwrap

import webapp2
import jinja2
import random
import secrets
import urllib2 as urllib
import io
import cgi
import mimetypes


from google.appengine.api import memcache
from google.appengine.datastore.datastore_query import Cursor
from google.appengine.ext import db
from google.appengine.ext.db import to_dict
from google.appengine.ext import ndb
from google.appengine.api import images
from google.appengine.api import users
from secrets import SESSION_KEY
from webapp2 import WSGIApplication, Route
from webapp2_extras import auth, sessions
from jinja2.runtime import TemplateNotFound
from datetime import datetime, timedelta
from math import log
from google.appengine.api import urlfetch
from google.appengine.api import mail

import time
import PIL
from PIL import Image, ImageDraw, ImageFont




template_dir = os.path.join(os.path.dirname(__file__), 'templates')
jinja_env = jinja2.Environment(loader = jinja2.FileSystemLoader(template_dir),
                               autoescape = True)

secret = 'fuck'




epoch = datetime(1970, 1, 1)

SIMPLE_TYPES = (int, long, float, bool, dict, basestring, list)

def to_dict(model):
	output = {}
	for key, prop in model._properties.iteritems():
		value = getattr(model, key)
		logging.error(type(value))
		
		if value is None or isinstance(value, SIMPLE_TYPES):
			output[key] = value
			logging.error(output)
		elif isinstance(value, datetime):
			# Convert date/datetime to ms-since-epoch ("new Date()").
			ms = time.mktime(value.utctimetuple())
			ms += getattr(value, 'microseconds', 0) / 1000
			output[key] = int(ms)
			logging.error(output)
		elif isinstance(value, ndb.GeoPt):
			output[key] = {'lat': value.lat, 'lon': value.lon}
			logging.error(output)
		elif isinstance(value, ndb.Key):
			#logging.error(value.get())
			logging.error(type(str(value)))
			
			
			
			output[key] = str(value)
			#output[key] = to_dict(value.get())
			logging.error(output)
		else:
			raise ValueError('cannot encode ' + repr(prop))
	
	return output

EMAIL_RE  = re.compile(r'^[\S]+@[\S]+\.[\S]+$')
def valid_email(email):
    return not email or EMAIL_RE.match(email)
	
	
def epoch_seconds(date):
    """Returns the number of seconds from the epoch to date."""
    td = date - epoch
    return td.days * 86400 + td.seconds + (float(td.microseconds) / 1000000)

def score(ups, downs):
    return ups - downs

def hot(ups, downs, date):
    """The hot formula. Should match the equivalent function in postgres."""
    s = score(ups, downs)
    order = log(max(abs(s), 1), 10)
    sign = 1 if s > 0 else -1 if s < 0 else 0
    seconds = epoch_seconds(date) - 1134028003
    return round(order + sign * seconds / 45000, 7)



def render_str(template, **params):
    t = jinja_env.get_template(template)
    return t.render(params)

def make_secure_val(val):
    return '%s|%s' % (val, hmac.new(secret, val).hexdigest())

def check_secure_val(secure_val):
    val = secure_val.split('|')[0]
    if secure_val == make_secure_val(val):
        return val

class BlogHandler(webapp2.RequestHandler):
	def write(self, *a, **kw):
		self.response.out.write(*a, **kw)
		
	def render_str(self, template,template_vars={}, **params):
		params['user'] = self.current_user
		params['url_for'] = self.uri_for
		params['logged_in'] = self.logged_in
		params['loginfirst']= self.session.get_flashes(key='logininfo')
		params['logoutfirst']= self.session.get_flashes(key='logoutinfo')
		params['sentmail']= self.session.get_flashes(key='sentmail')
		params['flashes'] = self.session.get_flashes()
		params.update(template_vars)
		return render_str(template, **params)
	
	def render(self, template,template_vars={}, **kw):
		self.write(self.render_str(template,template_vars, **kw))
	
	
	@webapp2.cached_property	
	def current_user(self):
		"""Returns currently logged in user"""
		user_dict = self.auth.get_user_by_session()
		#logging.error(user_dict)
		if user_dict:
			return self.auth.store.user_model.get_by_id(user_dict['user_id'])
			
		else:
			return None
	
	@webapp2.cached_property
	def auth(self):
		return auth.get_auth()
	
	def dispatch(self):
		# Get a session store for this request.
		self.session_store = sessions.get_store(request=self.request)
		try:
			# Dispatch the request.
			webapp2.RequestHandler.dispatch(self)
		finally:
			# Save all sessions.
			self.session_store.save_sessions(self.response)
			#logging.info("dispatch")
			#logging.info(self.auth.get_user_by_session())
	
	@webapp2.cached_property
	def session(self):
		"""Returns a session using the default cookie key"""
		return self.session_store.get_session()
		
	@webapp2.cached_property
	def logged_in(self):
		"""Returns true if a user is currently logged in, false otherwise"""
		return self.auth.get_user_by_session() is not None
		
	def head(self, *args):
		"""Head is used by Twitter. If not there the tweet button shows 0"""
		pass
	
	def initialize(self, *a, **kw):
		webapp2.RequestHandler.initialize(self, *a, **kw)
		self.user = self.current_user
	
	def read_secure_cookie(self, name):
		cookie_val = self.request.cookies.get(name)
		return cookie_val and check_secure_val(cookie_val)
		
	def loginurl(self):
		self.set_secure_cookie('url', self.request.url)
	
	def logouturl(self):
		self.response.headers.add_header('Set-Cookie', 'url=; Path=/')
		
	def set_secure_cookie(self, name, val):
		cookie_val = make_secure_val(val)
		self.response.headers.add_header('Set-Cookie','%s=%s; Path=/' % (name, cookie_val))
	

		
def make_salt(length = 5):
    return ''.join(random.choice(letters) for x in xrange(length))

def make_pw_hash(name, pw, salt = None):
    if not salt:
        salt = make_salt()
    h = hashlib.sha256(name + pw + salt).hexdigest()
    return '%s,%s' % (salt, h)

def valid_pw(name, password, h):
    salt = h.split(',')[0]
    return h == make_pw_hash(name, password, salt)

def users_key(group = 'default'):
    return db.Key.from_path('users', group)

class User(ndb.Model):
	name = ndb.StringProperty()
	pw_hash = ndb.StringProperty()
	email = ndb.StringProperty()
	avatar_url=ndb.StringProperty()
	link=ndb.StringProperty()
	
	
	



class MainHandler(BlogHandler):
	def get(self):
		self.render("frontdummy.html")

def imagerender(self):
	self._render_text = self.content.replace('\n', '<br>')
	logging.error(self.key)
	votes=ndb.gql("SELECT * FROM Vote WHERE imageid=:1 AND sign=:2",self.key,1)
	#logging.error(votes.count())
	votecounter=0
	for vote in votes:
		votecounter +=1
	return self,votecounter

def timedelta(usedtime):
	current_time=datetime.now()-usedtime
	if current_time.days>=365:
		return str(current_time.days/365) + " year ago"
	if current_time.days>=31 and current_time.days<365:
		return str(current_time.days/30) + " month ago"
	if current_time.days>=1 and current_time.days<31:
		return str(current_time.days) + " days ago"
	if current_time.days<1 and (current_time.seconds)/3600 >= 1:
		return str((current_time.seconds)/3600) + " hours ago"
	if (current_time.seconds)/3600 < 1:
		return str((current_time.seconds)/60) + " mins ago"	
	
class Img(ndb.Model):
	content=ndb.StringProperty(required=True)
	image = ndb.BlobProperty(required=True)
	date = ndb.DateTimeProperty(auto_now_add=True)
	user = ndb.KeyProperty(kind="User",required=True)

		
	def render(self):
		self,votecounter=imagerender(self)
		return render_str("post_image.html", i = self,votecounter=votecounter)
	
	def thumbnailrender(self):
		self,votecounter=imagerender(self)
		return render_str("thumbnail_image.html", i = self,votecounter=votecounter)
	
	def permalinkrender(self):
		self,votecounter=imagerender(self)
		current_delta=timedelta(self.date)
		
			
		logging.error(current_delta)
		return render_str("permalink.html", i = self,time_delta=current_delta,votecounter=votecounter)
	
	
def parent_key(parent_name=None):
    """Constructs a Datastore key for a imagelist entity with parent_name."""
    return ndb.Key('imagelist', parent_name or 'default_image')

def new_dbrender():
	return ndb.gql("SELECT * FROM Img WHERE ANCESTOR IS :1 ORDER BY date DESC",parent_key())
	
class ImagePost(BlogHandler):
	def get(self):
		
		imgs = new_dbrender()
		p=self.request.get('p')
		pager = ndbpager.Pager(query=imgs, page=p)
		images, _, _ = pager.paginate(page_size=secrets.pagesize)
		url=self.request.path_url+"?"
		self.loginurl()
		#self.set_secure_cookie('page','1')
		self.render("hot_image.html",html_class="New",images=images,pager=pager,url_for_other_page=url,title="New",description="Source of whats new and popular")

class NewImage(BlogHandler):
	def get(self):
			self.loginurl()
			self.render("newimage.html",html_class="Upload",title="Upload a funny pic",description="Place to share your fun with others. Show the creativity")
		
	def post(self):
		
		htmlclass='Upload'
		if self.current_user:
			avatar=self.request.get('img')
			if avatar:
				newimageloader(self,avatar,htmlclass)
			else:
				error = " Post Title and Image is compulsory, please fill both!"
				self.render('newimage.html',html_class=htmlclass,content=self.request.get('content'),error=error, title="Upload a funny pic",description="Share the fun with the world.Show up the creativity")
		else:
			error = " Boss: You need to be logged to perform this!"
			self.render('newimage.html',html_class=htmlclass,content=self.request.get('content'),error=error, title="Upload a funny pic",description="Share the fun with the world.Show up the creativity")

class NewImageSecret(BlogHandler):
	def get(self):
			self.loginurl()
			self.render("newimage.html",html_class="Upload",secret="Secret",title="Upload a funny pic",description="Place to share your fun with others. Show the creativity")
		
	def post(self):
		
		htmlclass='Upload'
		
		avatar=self.request.get('img')
		if avatar:
			newimageloader(self,avatar,htmlclass)
		else:
			error = "Post Title and Image is compulsory, please fill both!"
			self.render('newimage.html',html_class=htmlclass,secret="Secret",content=self.request.get('content'),error=error, title="Upload a funny pic",description="Share the fun with the world.Show up the creativity")
		

class NewWebImageSecret(BlogHandler):
	def get(self):
			self.loginurl()
			self.render("newimage.html",html_class="Upload_Web",secret="Secret",title="Upload a funny pic",description="Place to share your fun with others. Show the creativity")
		
	def post(self):
		htmlclass='Upload_Web'
		imgurl=self.request.get('weblink')
		try:
			result=urlfetch.fetch(imgurl,method=urlfetch.GET, deadline=15)
			logging.error(result)
			if result.status_code == 200:
				logging.error("upload")
				avatar=(result.content)
				newimageloader(self,avatar,htmlclass)
			else:
				logging.error("error-code: %s",result.status_code)
				error="Error: Sorry, our servers can't able to get your pics. Please try again. "
				self.render('newimage.html',html_class=htmlclass,secret="Secret",error=error, content=self.request.get('content'),title="Upload a funny pic",description="Place to share your fun with others. Show the creativity")
		except urlfetch.DeadlineExceededError:
				error="Error: Sorry, our servers can't able to upload your pics. Please try again. "
				self.render('newimage.html',html_class=htmlclass,secret="Secret",error=error, content=self.request.get('content'),title="Upload a funny pic",description="Place to share your fun with others. Show the creativity")
				
		except urlfetch.InvalidURLError:
				error="Error: Please enter a valid URL. "
				self.render('newimage.html',html_class=htmlclass,secret="Secret",error=error, content=self.request.get('content'),title="Upload a funny pic",description="Place to share your fun with others. Show the creativity")
				
class NewWebImage(BlogHandler):
	def get(self):
			self.loginurl()
			self.render("newimage.html",html_class="Upload_Web",title="Upload a funny pic",description="Place to share your fun with others. Show the creativity")
		
	def post(self):
		htmlclass='Upload_Web'
		if self.current_user:
			
			imgurl=self.request.get('weblink')
			try:
				result=urlfetch.fetch(imgurl,method=urlfetch.GET, deadline=15)
				logging.error(result)
				if result.status_code == 200:
					logging.error("upload")
					avatar=(result.content)
					newimageloader(self,avatar,htmlclass)
				else:
					logging.error("error-code: %s",result.status_code)
					error="Error: Sorry, our servers can't able to get your pics. Please try again. "
					self.render('newimage.html',html_class=htmlclass,error=error, content=self.request.get('content'),title="Upload a funny pic",description="Place to share your fun with others. Show the creativity")
			
				
			

			
			except urlfetch.DeadlineExceededError:
				error="Error: Sorry, our servers can't able to upload your pics. Please try again. "
				self.render('newimage.html',html_class=htmlclass,error=error, content=self.request.get('content'),title="Upload a funny pic",description="Place to share your fun with others. Show the creativity")
				
			except urlfetch.InvalidURLError:
				error="Error: Please enter a valid URL. "
				self.render('newimage.html',html_class=htmlclass,error=error, content=self.request.get('content'),title="Upload a funny pic",description="Place to share your fun with others. Show the creativity")
		else:
			error="Error: You need to be logged in to perform this "
			self.render('newimage.html',html_class=htmlclass,error=error, content=self.request.get('content'),title="Upload a funny pic",description="Place to share your fun with others. Show the creativity")
		

class SpecialImg(ndb.Model):
	category = ndb.StringProperty()
	image = ndb.BlobProperty(required=True)
	date = ndb.DateTimeProperty(auto_now_add=True)
	popular = ndb.KeyProperty()

	
class SpecialImageHandler(BlogHandler):
	def get(self):
		self.render('specialimage.html')
		
	def post(self):	
		img=self.request.get('image')
		category=self.request.get('category')
		if img:
			simg=SpecialImg(category=category,image=img)
			simg.put()
		self.redirect('/')

def generateimagerender(self,error,content,uploadimage):
		self.loginurl()
		imgs = ndb.gql("SELECT * FROM SpecialImg ORDER BY date DESC")
		logging.error(imgs.count)
		self.render('addcaption.html',html_class="Generate_image",content=content,title="Add a cool caption",description="Place to create your own image and share with others. Show the creativity",imgs=imgs,fullwidth='a',error=error,uploadimage=uploadimage)


class NewImageTag(BlogHandler):
	def get(self):
		error=""
		content=""
		generateimagerender(self,error,content,"")
		
	def post(self):
		caption = self.request.get('caption')
		uploadpic = self.request.get('uploadpic')
		logging.error(uploadpic)
		logging.error(caption)
		if caption:
			if self.current_user:
				logging.error(caption)
				htmlclass='Generate_image'
				urlsafe_key=self.request.get('uploadimage')
				if urlsafe_key:
					img_key = ndb.Key(urlsafe=urlsafe_key)
					logging.error(img_key)
					image = img_key.get()
					if image.image:
						logging.error(image.image)
						newimageloader(self,image.image,htmlclass)
					else:
						self.response.out.write('No image')
				else:
					error="Error : Boss pls select & preview the image and then upload !! "
					content=self.request.get('content')
					generateimagerender(self,error,content,"")
			else:
				error="Error : Boss, you need to be logged in to perform this !! "
				content=self.request.get('content')
				generateimagerender(self,error,content,"")
		elif uploadpic:
			logging.error(uploadpic)
			avatar=self.request.get('image')
			content=""
			error=""
			logging.error(avatar)
			if avatar:
				try:
					logging.error("try")
					i=BufferImg()
					i.image = images.resize(avatar,secrets.max_i_width,secrets.max_i_height)
					i.put()
					generateimagerender(self,error,content,"/img?img_id="+i.key.urlsafe())
				except images.NotImageError:
					error="Sorry, we don't recognize that image format.We can process JPEG, GIF, PNG, BMP, TIFF, and ICO files."
					generateimagerender(self,error,content,"")
				except images.BadImageError:
					error="Sorry, we had a problem processing the image provided.We can process JPEG, GIF, PNG, BMP, TIFF, and ICO files"
					generateimagerender(self,error,content,"")
				except images.LargeImageError:
					error="Sorry, the image provided was too large for us to process."
					generateimagerender(self,error,content,"")
			else:
				error = "Boss, select a picture from your computer and then submit"
				logging.error(error)
				generateimagerender(self,error,content,"")
		
		
			
		
		

class BufferImg(ndb.Model):
	image = ndb.BlobProperty(required=True)
	date = ndb.DateTimeProperty(auto_now_add=True)
	
		
def drawtext(xaxis,yaxis,text,font,color,draw):			
	draw.text((xaxis, yaxis), text, font = font,fill=color)

def	aligntext(align,xaxis,yaxis,margin,text_width,text,font,color,draw):
	
	if align == "left":
		drawtext(margin,yaxis,text,font,color,draw)
	if align == "center":
		drawtext((xaxis-text_width)/2,yaxis,text,font,color,draw)
	if align == "right":
		drawtext((xaxis-margin-text_width),yaxis,text,font,color,draw)
	
def nooflines(caption,font,i_width,draw):
	t_width,t_height = draw.textsize(caption,font)
	logging.error(t_width)
	nooflines=(t_width/i_width)+1
	logging.error(nooflines)
	fontwidth=len(caption)/nooflines
	logging.error(fontwidth)
	lines = textwrap.wrap(caption, width = fontwidth)
	logging.error(lines)
	return lines,t_height
	
	
def caption(caption,font,align,i_width,yaxis,margin,color,lines,draw):
	
	for line in lines:
		logging.error("line")
		width, height = font.getsize(str(line))
		aligntext(align,i_width,yaxis,margin,width,str(line),font,color,draw)
		logging.error(width)
		yaxis += height
	
class GenerateHandler(BlogHandler):
    def post(self):
		#get inputs need to caption
		topAlign=self.request.get('topAlign')
		bottomAlign=self.request.get('bottomAlign')
		font=self.request.get('font')
		fontsize=int(self.request.get('fontsize'))
		color=self.request.get('color')
		topCaption=self.request.get('topCaption')
		bottomCaption=self.request.get('bottomCaption')
		imagelink=self.request.get('imagelink')
		
		logging.error(imagelink)
		urlsafe_key= imagelink.replace("/img?img_id=","")
		logging.error(urlsafe_key)
		img_key = ndb.Key(urlsafe=urlsafe_key)
		logging.error(img_key)
		image = img_key.get()
		#logging.error(image.image)
		
		font=font+'.ttf'
		logging.error(font)
		
		
		#image read
		#fd = urllib.urlopen('http://newevolutiondesigns.com/images/freebies/black-wallpaper-preview-3.jpg')
		#logging.error(fd)
		#image_file = io.BytesIO(fd.read())
		#logging.error(image_file)
		#im = Image.open(image_file)
		image_file = io.BytesIO(image.image)
		im=Image.open(image_file)
		logging.error(im)
		
		#get image size
		i_width,i_height=im.size
		logging.error(i_width)
		logging.error(i_height)
		draw=ImageDraw.Draw(im)
		
		#get font
		font = ImageFont.truetype(font,fontsize)
		logging.error(font)
		margin=10
		
		im_watermark=Image.open('waterm.jpg')
		logging.error(im_watermark)
		mark_width,mark_height=im_watermark.size
		logging.error(mark_width)
		im.paste(im_watermark,(i_width-mark_width,i_height-mark_height))
		#add caption if any
		if topCaption:
			lines,theight = nooflines(topCaption,font,i_width,draw)
			
			caption(topCaption,font,topAlign,i_width,margin,margin,color,lines,draw)
		
		if bottomCaption:
			lines,theight = nooflines(bottomCaption,font,i_width,draw)
			l=0
			for line in lines:
				l +=1
			caption(bottomCaption,font,bottomAlign,i_width,i_height-(l*theight)-margin,margin,color,lines,draw)
		
		
		
		#draw image and save it in buffer
		draw=ImageDraw.Draw(im)
		#draw.text((10,10),'powerstar kjhasdas asdjhas',(255,255,0),font=font)
		#draw=ImageDraw.Draw(im)
		#logging.error(draw)
		#logging.error(im)
		buf = StringIO.StringIO()
		im.save(buf, format= 'JPEG')
	
		jpeg = buf.getvalue()
		buf.close()
		logging.error(jpeg)
		
		#a=Image.open(StringIO.StringIO(jpeg))
		#logging.error(type(a))
		#saving image in datastore for retrieving in json. Note: this part need to changed as it occupies memory probably need to use some kind buffer
		i=BufferImg(image=jpeg)
		i.put()
		r = json.dumps({"imagekey" : i.key.urlsafe()})
		logging.error(r)
		self.response.headers["Content-Type"] = "application/json; charset=UTF-8"
		self.response.out.write(r)
		
		
		"""
		if self.current_user:
			
			
			
			userid=self.current_user.key
			imagekey=ndb.Key('Img',int(imgid),parent=parent_key())
			thumpsup=1;
			thimpsdowm=-1;
			if imagekey and action:
				if action=="ThumpsUp":
					r=thumps(imagekey,userid,imgid,1)
				elif action=="ThumpsDown":
					r=thumps(imagekey,userid,imgid,-1)
				else:
					r = json.dumps({"status" : "nochange"})
					
		else:
			
			r = json.dumps({"status" : "err","action" : action,"id" : imgid})
		
		logging.error(r)
		self.response.headers["Content-Type"] = "application/json; charset=UTF-8"
		self.response.out.write(r)	
		"""

		
def sendemail(fromemail,toemail,subject,body,attachments,reply_to):
	if not attachments and not reply_to:
		mail.send_mail(sender=fromemail,
					  to=toemail,
					  subject=subject,
					  body=body)
	if attachments and reply_to:
		mail.send_mail(sender=fromemail,
					  to=toemail,
					  subject=subject,
					  body=body,
					  attachments=attachments,
					  reply_to=reply_to)
	if not attachments and reply_to:
		mail.send_mail(sender=fromemail,
					  to=toemail,
					  subject=subject,
					  body=body,
					  reply_to=reply_to)
	if attachments and not reply_to:
		mail.send_mail(sender=fromemail,
					  to=toemail,
					  subject=subject,
					  body=body,
					  attachments=attachments)
	logging.error("sent")
		

def emailimagelink(self,toemail,link):				  
	fromemail=secrets.email
	toemail = toemail
	subject="RajiniNation : Your picture is submitted succesfully"
	emailbody="Dear "+ self.current_user.name+""":

	Your picture has been uploaded successfully. You can now visit """+link+""" for the pic. Thanks for using and we see u soon. Have fun :)  
	
	Please let us know if you have any questions.

	The Rajinination.com Team
	"""
	logging.error(emailbody)
	body=emailbody
	logging.error(toemail)
	sendemail(fromemail,toemail,subject,body,[],"")
		
def newimagerender(self,error,htmlclass,content):
	if htmlclass=="Generate_image":
		generateimagerender(self,error,content,"")
	else:
		self.render('newimage.html',html_class=htmlclass,error=error,content=content,title="Upload a funny pic",description="Place to share your fun with others. Show the creativity")
			
def newimageloader(self,avatar,htmlclass):			
		image=Img(parent=parent_key())
		image.content = self.request.get('content')
		tag1=self.request.get('Funny')
		tag2=self.request.get('RajiniStyle')
		tag3=self.request.get('WTK')
		tag4=self.request.get('EKSI')
		tag5=self.request.get('Rage')
		tag6=self.request.get('Shit')
		postfb=self.request.get('postfb')
		email=self.request.get('email')
		secretname=self.request.get('name')
		secretavatarurl=self.request.get('avatarurl')
		secretpassword=str(self.request.get('password'))
		logging.error(secretpassword)
		logging.error(type(secretpassword))
		logging.error(secrets.secretpassword)
		if self.current_user:
			image.user=self.current_user.key
		
		if secretname:
			if secretpassword==secrets.secretpassword:
			
				u=ndb.gql("SELECT * FROM User WHERE name=:1",secretname).get()
				logging.error(u)
				if not u:
					u=User(name=secretname)
					if secretavatarurl:
						u.avatar_url=secretavatarurl
					u.put()
				logging.error(u)
				logging.error(u.key)
				image.user=u.key
			else:
				logging.error("Password not correct")
				avatar=""

		if avatar and image.content:
			try:
				
				image.image = images.resize(avatar,secrets.max_i_width,secrets.max_i_height)
				image.put()
				redirecturl='/i/%s' %image.key.id()
				logging.error(redirecturl)
				hot=Hot(imageid=image.key,hotvalue=0,votecounter=0)
				hot.put()
				
				if tag1:
					tag=Tag(imageid=image.key,tagname="Funny")
					logging.error(tag)
					tag.put()
					logging.error(tag.key.id())
				if tag2:
					tag=Tag(imageid=image.key,tagname="RajiniStyle")
					tag.put()
				if tag3:
					tag=Tag(imageid=image.key,tagname="WTK")
					tag.put()
				if tag4:
					tag=Tag(imageid=image.key,tagname="EKSI")
					tag.put()
				if tag5:
					tag=Tag(imageid=image.key,tagname="Rage")
					tag.put()
				if tag6:
					tag=Tag(imageid=image.key,tagname="Shit")
					tag.put()
				if email:
					logging.error(email)
					emailimagelink(self,email,str(self.request.host_url)+redirecturl)
				if 	postfb:
					self.redirect('/i')
					getimageid=str(image.key.id())
					hosturl=str(self.request.host_url)
					redirecturl = hosturl + '/i/' + getimageid
					picture = hosturl + "/img?img_id=" + str(image.key.urlsafe())
					logging.error(picture)
				
					postfblink="https://www.facebook.com/dialog/feed? app_id="+secrets.FACEBOOK_APP_ID+"& link="+redirecturl+"& picture="+picture+"& name="+str(image.content)+"& caption="+redirecturl+"& description="+str(image.content)+"& redirect_uri="+redirecturl
					
					#postfblink = "https://graph.facebook.com/dialog/feed?app_id="+ secrets.FACEBOOK_APP_ID + "&link=" + redirecturl + "&picture=" + picture + "&name=" + str(image.content) + "&caption=" + redirecturl + "&description="+str(image.content)+"&redirect_uri=" + redirecturl
					
					#postfblink = "https://graph.facebook.com/brent/feed? link="+redirecturl+"& picture="+picture+"& name="+str(image.content)+"& caption="+redirecturl+"& description=" + redirecturl +"&"
					redirecturl=postfblink
				
					
				
				self.redirect(redirecturl)
			except images.NotImageError:
				error="Sorry, we don't recognize that image format.We can process JPEG, GIF, PNG, BMP, TIFF, and ICO files."
				newimagerender(self,error,htmlclass,image.content)
			except images.BadImageError:
				error="Sorry, we had a problem processing the image provided.We can process JPEG, GIF, PNG, BMP, TIFF, and ICO files"
				newimagerender(self,error,htmlclass,image.content)
			except images.LargeImageError:
				error="Sorry, the image provided was too large for us to process."
				newimagerender(self,error,htmlclass,image.content)
			"""except images.RequestTooLargeError:
				error="Sorry, the image provided was too large for us to process."
				newimagerender(self,error,htmlclass,image.content)
			except images.AttributeError:
				error="Sorry, the image provided was too large for us to process."
				newimagerender(self,error,htmlclass,image.content)
			"""
			
		else:
			error = " Title and Image is compulsory, please fill both!"
			newimagerender(self,error,htmlclass,image.content)



class UploadPictureHandler(BlogHandler):
	def post(self):
		avatar=self.request.get('uploadpic')
		logging.error(avatar)
		if avatar:
			try:
				logging.error("try")
				i=BufferImg()
				i.image = images.resize(avatar,secrets.max_i_width,secrets.max_i_height)
				i.put()
				logging.error(i.key)
			except images.NotImageError:
				error="Sorry, we don't recognize that image format.We can process JPEG, GIF, PNG, BMP, TIFF, and ICO files."
				#newimagerender(self,error,htmlclass,image.content)
			except images.BadImageError:
				error="Sorry, we had a problem processing the image provided.We can process JPEG, GIF, PNG, BMP, TIFF, and ICO files"
				#newimagerender(self,error,htmlclass,image.content)
			except images.LargeImageError:
				error="Sorry, the image provided was too large for us to process."
				#newimagerender(self,error,htmlclass,image.content)
			
			
class RandomPage(BlogHandler):
	def get(self):
		previous,current,next=randomdb(3)
		logging.error(current)
		images = current.get()
		
		#comments = ndb.gql("SELECT * FROM Comment WHERE imageid=:1",current)
		logging.error(current.id())
		logging.error(images)
		self.loginurl()
		self.render('permalink_image.html',html_class="Random",images=images,previous=previous.id(),next=next.id())		
		
class ImagePage(BlogHandler):
	def get(self,img_id):
		images = ndb.Key('Img',int(img_id),parent=parent_key()).get()
		self.loginurl()
		#logging.error(int(img_id))
		#comments = ndb.gql("SELECT * FROM Comment WHERE imageid=:1",ndb.Key('Img',int(img_id),parent=parent_key()))
		popular = ndb.gql("SELECT * FROM Hot ORDER BY votecounter DESC LIMIT 3")
		previous,next=randomdb(2)
		logging.error(popular)
		
		self.render('permalink_image.html',html_class="Permalink",images=images,previous=previous.id(),next=next.id(),popular=popular)

class SideRefresh(BlogHandler):
	def post(self):
		popular = ndb.gql("SELECT * FROM Hot ORDER BY votecounter DESC")
		p=self.request.get('p')
		logging.error(popular)
		pager = ndbpager.Pager(query=popular, page=p)
		populars, _, _ = pager.paginate(page_size=3)
		
		r = json.dumps({"popular" : populars })
		logging.error(r)
		self.response.headers["Content-Type"] = "application/json; charset=UTF-8"
		self.response.out.write(r)	
		

class EmailUsHandler(BlogHandler):
	def get(self):
		self.render('emailus.html')
	
	def post(self):
		name=self.request.get('name')
		email=self.request.get('email')
		subject=self.request.get('subject')
		message=self.request.get('message')
		attachment=self.request.POST['attachment']
		reply_to=""
		attachments=[]
		Error_Name=""
		Error_Subject=""
		Error_Message=""
		if name and subject and message:
			
			a=self.request.get('attachment')
			if a:
				attachments=[(attachment.filename,attachment.file.read())]
				logging.error(attachments)

			if email:
				reply_to=email
			body=message+"\nFrom : "+name
			try:
				sendemail(secrets.email,secrets.email,subject,body,attachments,reply_to)
				self.session.add_flash("Sent Sucess",key='sentmail')
				self.redirect('/hot')
			except mail.InvalidAttachmentTypeError:
				self.render("emailus.html",name=name,email=email,subject=subject,message=message,Error_Mail="We dont support this file format. Please upload with other format")
			except mail.Error:
				self.render("emailus.html",name=name,email=email,subject=subject,message=message,Error_Mail="Error occured while sending email. Please try again")
		else:
			
			if not name:
				Error_Name="Name is required"
			if not subject:
				Error_Subject="Subject is required"
			if not message:
				Error_Message="Message is required"
			self.render("emailus.html",name=name,email=email,subject=subject,message=message,Error_Name=Error_Name,Error_Subject=Error_Subject,Error_Message=Error_Message)
		
		
def randomdb(num):
	q = Img.query()
	item_keys = q.fetch(2000,keys_only=True)
	return random.sample(item_keys, num)


			
class ImageHandler(BlogHandler):
    def get(self):
		img_key = ndb.Key(urlsafe=self.request.get('img_id'))
		image=img_key.get()
		if image.image:
			#logging.error(image.image)
			self.response.headers['Content-Type'] = 'image/png'
			self.response.out.write(image.image)
		else:
			self.response.out.write('No image')		

class Vote(ndb.Model):
	userid = ndb.KeyProperty(kind="User",required=True)
	imageid = ndb.KeyProperty(kind="Img",required=True)
	sign = ndb.IntegerProperty(required=True)
	

class Comment(ndb.Model):
	userid = ndb.KeyProperty(kind="User",required=True)
	imageid = ndb.KeyProperty(kind="Img",required=True)
	comment = ndb.TextProperty(required=True)
	date = ndb.DateTimeProperty(auto_now_add=True)

class Hot(ndb.Model):
	imageid = ndb.KeyProperty(kind="Img",required=True)
	time = ndb.DateTimeProperty(auto_now_add=True)
	hotvalue = ndb.FloatProperty(required=True)
	votecounter = ndb.IntegerProperty()

class Tag(ndb.Model):
	imageid = ndb.KeyProperty(kind="Img",required=True)
	time = ndb.DateTimeProperty(auto_now_add=True)
	tagname = ndb.StringProperty(required=True)	
	
	
class VoteHandler(BlogHandler):
    def post(self):
		action=self.request.get('action')
		imgid=int(self.request.get('imgid'))
		if self.current_user:
			
			userid=self.current_user.key
			imagekey=ndb.Key('Img',int(imgid),parent=parent_key())
			thumpsup=1;
			thimpsdowm=-1;
			if imagekey and action:
				if action=="ThumpsUp":
					r=thumps(imagekey,userid,imgid,1)
				elif action=="ThumpsDown":
					r=thumps(imagekey,userid,imgid,-1)
				else:
					r = json.dumps({"status" : "nochange"})
					
		else:
			
			r = json.dumps({"status" : "err","action" : action,"id" : imgid})
		
		logging.error(r)
		self.response.headers["Content-Type"] = "application/json; charset=UTF-8"
		self.response.out.write(r)	

			
def thumps(imagekey,userid,imgid,direction):
	v = ndb.gql("SELECT * FROM Vote WHERE imageid=:1 AND userid=:2",imagekey,userid)
	if v.count()==0:
		vote=Vote(imageid=imagekey,userid=userid,sign=direction)
		vote.put()
	else:
		for vote in v:
			vote.sign=direction
			vote.put()
	votes=ndb.gql("SELECT * FROM Vote WHERE imageid=:1",imagekey)
	upcounter=0
	downcounter=0
	
	for vote in votes:
		if vote.sign==1:
			upcounter +=1
		elif vote.sign==-1:
			downcounter+=1
	logging.info(upcounter)
	logging.info(downcounter)
	hotvalues=ndb.gql("SELECT * FROM Hot WHERE imageid=:1",imagekey)
	for h in hotvalues:
		hotvalue=hot(upcounter,downcounter,h.time)
		h.hotvalue=hotvalue
		h.votecounter= upcounter-downcounter			
		h.put()
	votes=ndb.gql("SELECT * FROM Vote WHERE imageid=:1 and sign=:2",imagekey,1)
	return json.dumps({"status" : "ok", "votes": votes.count(),"id":imgid, "action":direction})
		
			
class ProfileHandler(BlogHandler):
	def get(self,user_id):
		#u=User.by_id(int(user_id))
		userid=ndb.Key('User',int(user_id))
		u = userid.get()
		images=ndb.gql("SELECT * FROM Img WHERE user=:1 ORDER BY date DESC",userid)
		#votes=ndb.gql("SELECT * FROM Vote WHERE userid=:1 AND sign=:2 LIMIT 10",userid,1)
		p=self.request.get('p')
		pager = ndbpager.Pager(query=images, page=p)
		imgs, _, _ = pager.paginate(page_size=secrets.pagesize)
		logging.error(imgs)
		logging.error(pager)
		logging.error(u)
		self.loginurl()
		url=self.request.path_url
		self.render('userpage.html',u=u,images=imgs,url_for_other_page=url,pager=pager)

class ProfileHandlerLikes(BlogHandler):
	def get(self,user_id):
		
		userid=ndb.Key('User',int(user_id))
		u = userid.get()
		votes=ndb.gql("SELECT * FROM Vote WHERE userid=:1 AND sign=:2",userid,1)
		p=self.request.get('p')
		pager = ndbpager.Pager(query=votes, page=p)
		v, _, _ = pager.paginate(page_size=secrets.pagesize)
		logging.error(v)
		#logging.error(u)
		self.loginurl()
		url=self.request.path_url
		self.render('userpage.html',u=u,votes=v,url_for_other_page=url,pager=pager)

		
def hot_dbrender():
	return ndb.gql("SELECT * FROM Hot ORDER BY hotvalue DESC")
	
class HotHandler(BlogHandler):
	def get(self):
		#logging.error(self.request.get('cursor'))
		hot = hot_dbrender()
		p=self.request.get('p')
		pager = ndbpager.Pager(query=hot, page=p)
		logging.error(hot)
		logging.error(pager)
		hots, _, _ = pager.paginate(page_size=secrets.pagesize)
		logging.error(hots)
		#logging.error(random.random())
		#logging.error(self.request.path_url)
		url=self.request.path_url+"?"
		self.loginurl()
		#self.set_secure_cookie('page','1')
		self.render("hot_image.html",hots=hots,pager=pager,url_for_other_page=url,html_class="Hot",title="Hot !!",description="Votes promote the post to the front page")		


class LoadPageHandler(BlogHandler):
	def imgrender(self,img,cookie_name):
		#page=self.read_secure_cookie(cookie_name)
		page=cookie_name
		if page:
			page=int(page)
			pager = ndbpager.Pager(query=img, page=page+1)
			
			logging.error(pager)
			imgs, _, _ = pager.paginate(page_size=secrets.pagesize)
			#self.set_secure_cookie(cookie_name,str(page+1))
			logging.error(imgs)
			nextpage=0
			if pager.has_next:
				nextpage=1
			logging.error(nextpage)
			return imgs,nextpage,page+1
	
	def post(self):
		
		#get inputs need to caption
		type=str(self.request.get('type'))
		page=str(self.request.get('p'))
		page=int(page.replace('page',''))
		logging.error(page)
		
		divhtml=""
		if type=="hot":
			container="refreshhot"
			logging.error("hot")
			img = hot_dbrender()
			logging.error(img)
			hots,nextpage,page=self.imgrender(img,page)			
			for h in hots:
				divhtml += h.imageid.get().render()
			
			
		elif type=="new":
			container="refreshnew"
			logging.error("new")
			img = new_dbrender()
			images,nextpage,page=self.imgrender(img,page)
			for i in images:
				divhtml += i.render()
			
			
		elif type=="tag":
			container="refreshtag"
			logging.error("hot")
			tagname=str(self.request.get('tagname'))
			img = tag_dbrender(tagname)
			hots,nextpage,page=self.imgrender(img,page)			
			for h in hots:
				divhtml += h.imageid.get().render()
				
						
		divhtml='<div id="page'+str(page)+'">'+divhtml+"</div>"
		myJson = json.dumps({"html":divhtml,"container":container,"nextpage":nextpage,"page":"page"+str(page)})	
		#logging.error(myJson)
		logging.error(nextpage)
		logging.error(str(page))
		self.response.headers["Content-Type"] = "application/json; charset=UTF-8"
		self.response.out.write(myJson)
		
def tag_dbrender(tagname):
	return ndb.gql("SELECT * FROM Tag WHERE tagname=:1 ORDER BY time DESC",tagname)
	
class TagHandler(BlogHandler):
	def get(self):
		tagname=self.request.get('t')
		tag = tag_dbrender(tagname)
		p=self.request.get('p')
		pager = ndbpager.Pager(query=tag, page=p)
		logging.error(secrets.pagesize)
		hots, _, _ = pager.paginate(page_size=secrets.pagesize)
		#logging.error(random.random())
		logging.error(self.request.path_url)
		url=self.request.path_url+"?t="+tagname+"&"
		logging.error(self.request.url)
		self.loginurl()
		
		#self.set_secure_cookie('page','1')
		self.render("hot_image.html",hots=hots,pager=pager,url_for_other_page=url,html_class="Tag",title=tagname)		


class DeleteImageHandler(BlogHandler):
	def get(self):
		self.render('deleteimage.html')
	def post(self):
		img_id = self.request.get('img_id')
		password = self.request.get('password')
		if password==secrets.deletepassword:
			img_key=ndb.Key('Img',int(img_id),parent=parent_key())
			logging.error(img_key)
			tag_key=ndb.gql("SELECT * FROM Tag WHERE imageid=:1",img_key).get(keys_only=True)
			hot_key=ndb.gql("SELECT * FROM Hot WHERE imageid=:1",img_key).get(keys_only=True)
			vote_key=ndb.gql("SELECT * FROM Vote WHERE imageid=:1",img_key).get(keys_only=True)
			logging.error(tag_key)
			logging.error(hot_key)
			logging.error(tag_key)
			logging.error(tag_key)
			if tag_key:
				tag_key.delete()
			if hot_key:
				hot_key.delete()
			if vote_key:
				vote_key.delete()
			if img_key:
				img_key.delete()
		self.redirect(self.request.path_url)
		
		
def handle_404(request, response, exception):
    logging.exception(exception)
    response.write('Oops! I could swear this page was here!')
    response.set_status(404)

def handle_500(request, response, exception):
    logging.exception(exception)
    response.write('A server error occurred!')
    response.set_status(500)		
			
if 'lib' not in sys.path:
    sys.path[0:0] = ['lib']


# webapp2 config
app_config = {
  'webapp2_extras.sessions': {
    'cookie_name': '_simpleauth_sess',
    'secret_key': SESSION_KEY,
  },
  'webapp2_extras.auth': {
    'user_attributes': []
  }
}





# Map URLs to handlers
routes = [
  Route('/', handler=MainHandler),
  Route('/img',handler=ImageHandler),
  Route('/new',handler=ImagePost),
  Route('/hot',handler=HotHandler),
  Route('/new:P',handler=NewImage),
  Route('/new:P/web',handler=NewWebImage),
  Route('/new:P/edit',handler=NewImageTag),
  Route('/new:Psecret',handler=NewImageSecret),
  Route('/new:P/websecret',handler=NewWebImageSecret),
  Route('/i/<:([0-9]+)>',handler=ImagePage),
  Route('/i',handler=RandomPage),
  Route('/login',handler='handlers.RootHandler'),
  Route('/username',handler='handlers.UserNameHandler'),
  Route('/vote',handler=VoteHandler),
  Route('/generate',handler=GenerateHandler),
  Route('/loadpage',handler=LoadPageHandler),
  Route('/emailus',handler=EmailUsHandler),
  Route('/uploadpicture',handler=UploadPictureHandler),
  Route('/siderefresh',handler=SideRefresh),
  Route('/u/<:([0-9]+)>',handler=ProfileHandler),
  Route('/u/<:([0-9]+)>/likes',handler=ProfileHandlerLikes),
  Route('/tag',handler=TagHandler),
  Route('/spcialimagehandler:POL',handler=SpecialImageHandler),
  Route('/delimg',handler=DeleteImageHandler),
  Route('/profile', handler='handlers.ProfileHandler', name='profile'),
  Route('/logout', handler='handlers.AuthHandler:logout', name='logout'),
  Route('/auth/<provider>', 
    handler='handlers.AuthHandler:_simple_auth', name='auth_login'),
  Route('/auth/<provider>/callback', 
    handler='handlers.AuthHandler:_auth_callback', name='auth_callback')
]

app = WSGIApplication(routes, config=app_config, debug=True)

def handle_error(request, response, exception):
	c = { 'exception': str(exception) }
	status_int = hasattr(exception, 'status_int') and exception.status_int or 500
	template = secrets.error_templates[status_int]
   	t=render_str(template, **c)
	response.write(t)
	response.set_status(status_int)



#app.error_handlers[404] = handle_error
#app.error_handlers[500] = handle_error