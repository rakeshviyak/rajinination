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

import webapp2
import cgi
def escape_html(s):
	return cgi.escape(s, quote=True)

form="""
<form method="post">
Birthday?<br>
<label>year<input type="text" name="year" value="%(year)s"></label>
<br>	
<input type="submit"><br>
<div style="color:red">%(error)s</div>
</form>
"""

def valid_year(year):
    if year and year.isdigit():
        year=int(year)
        if year >= 1950 and year <= 2020:
            return year
		
	
class MainHandler(webapp2.RequestHandler):
	
	
	def message(self,error="", year=""):
		self.response.out.write(form %{"error":error,"year": escape_html(year)})
	
	def get(self):
		self.message()
	
	def post(self):
		year=self.request.get('year')
		user_year = valid_year(self.request.get('year'))
	
		if not(user_year):
			self.message("Error msg",year)
		else:
			self.redirect("/thanks")
			
class ThanksHandler(webapp2.RequestHandler):	
	def get(self):
		self.response.out.write("thanks")

app = webapp2.WSGIApplication([('/', MainHandler),('/thanks',ThanksHandler)],debug=True)