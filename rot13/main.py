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
<h2>Enter some text to ROT13:</h2>
<input type="text" name="text" value="%(text)s" style="height: 100px; width: 400px;"></input>
<br>
<input type="submit">
</form>
"""

def rot13(x):
    y=" "
    for i in x:
        if ord("A")<= ord(i)<=ord("M"):
            n=ord(i)+13
        elif ord("a")<= ord(i)<=ord("m"):
            n=ord(i)+13
        elif ord("N")<= ord(i)<=ord("Z"):
            n=ord(i)-13
        elif ord("n")<= ord(i)<=ord("z"):
            n=ord(i)-13
        else:
            n=ord(i)
        y=y+chr(n)
    return y


#def rot13(text):
#	rotten=rot.get(text[x])
#		text[x]=text[x].replace(rot.get(text[x]))
#	
	#for(i,o) in (("a","n"),("b","o"),("c","p"),("d","q"),("e","r"),("f","s"),("g","t"),("h","u"),("i","v"),("j","w"),("k","x"),("l","y"),("m","z"),("n","a")):
	#	text=text.replace(i,o)
#	return text

class MainHandler(webapp2.RequestHandler):
	def write_form(self,text=""):
		self.response.out.write(form %{"text":escape_html(text)})
	
	def get(self):
		self.write_form()
		
	def post(self):
		user_text=rot13(self.request.get('text'))
		self.write_form(user_text)

app = webapp2.WSGIApplication([('/', MainHandler)],
                              debug=True)
 