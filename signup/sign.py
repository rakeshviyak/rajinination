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
import re


form="""
<form method="post">
<h2>Signup</h2>
<table>
<tr>
<td class="label">Username</td>
<td><input type="text" name="username" value="%(username)s"></td>
<td class="error">%(error_username)s</td>
</tr>
<tr>
<td class="label">Password</td>
<td><input type="password" name="password" value=""></td>
<td class="error">%(error_password)s</td>
</tr>
<tr>
<td class="label">Verify Password</td>
<td><input type="password" name="verify" value=""></td>
<td class="error">%(error_verify)s</td>
</tr>
<tr>
<td class="label">Email (optional)</td>
<td><input type="text" name="email" value="%(email)s"></td>
<td class="error">%(error_email)s</td>
</tr>
</table><br>
<input type="submit">
</form>
"""

USER_RE = re.compile(r"^[a-zA-Z0-9_-]{3,20}$")
PASS_RE = re.compile(r"^.{3,20}$")
EMAIL_RE = re.compile(r"^[\S]+@[\S]+\.[\S]+$")

error_username=""
error_password=""
error_verify=""
error_email=""

def valid_username(username):
    return USER_RE.match(username)

def valid_password(password):
    return PASS_RE.match(password)

def valid_email(email):
    if len(email)>0:
        return EMAIL_RE.match(email)


class MainPage(webapp2.RequestHandler):
	def message(self,username="",email="",error_username="",error_password="",error_verify="",error_email=""):
		self.response.out.write(form %{"username":username,"email":email,"error_username":error_username,"error_password":error_password,"error_verify":error_verify,"error_email":error_email})
	def get(self):
		self.message()
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
			self.response.out.write("Welcome")
		else:
			self.message(username,email,error_username,error_password,error_verify,error_email)
		
app = webapp2.WSGIApplication([('/', MainPage)], debug=True)