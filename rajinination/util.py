	"""
	def set_secure_cookie(self, name, val):
		cookie_val = make_secure_val(val)
		self.response.headers.add_header(
			'Set-Cookie',
			'%s=%s; Path=/' % (name, cookie_val))
	
	def read_secure_cookie(self, name):
		cookie_val = self.request.cookies.get(name)
		return cookie_val and check_secure_val(cookie_val)
	
	def login(self, user):
		self.set_secure_cookie('user_id', str(user.key().id()))
		
	def logout(self):
		self.response.headers.add_header('Set-Cookie', 'user_id=; Path=/')
	
		
	def initialize(self, *a, **kw):
		webapp2.RequestHandler.initialize(self, *a, **kw)
		uid = self.read_secure_cookie('user_id')
		self.user = uid and User.by_id(int(uid))
	"""

	
	
class Register(Signup):
    def done(self):
		#make sure the user doesn't already exist
		u = User.by_name(self.username)
		if u:
			msg = 'That user already exists.'
			self.render('signup-form.html', error_username = msg)
		else:
			u = User.register(self.username, self.password, self.email)
			u.put()
			self.login(u)
			self.redirect('/blog')

class Login(BlogHandler):
    def get(self):
        self.render('login-form.html')

    def post(self):
        username = self.request.get('username')
        password = self.request.get('password')

        u = User.login(username, password)
        if u:
            self.login(u)
            self.redirect('/blog')
        else:
            msg = 'Invalid login'
            self.render('login-form.html', error = msg)
			
class Logout(BlogHandler):
    def get(self):
        self.logout()
        self.redirect('/blog')

def blog_flush():
	memcache.flush_all()

class FlushHandler(BlogHandler):
	def get(self):
		blog_flush()
		self.redirect('/blog')
		
def blog_key(name = 'default'):
    return db.Key.from_path('blogs', name)

def mem_set(key,val):
	memcache.set(key,val)

def mem_get(val):
	return memcache.get(val)
	
def get_posts(update = False):
	mc_key = 'JOKES'
	posts=mem_get(mc_key)
	if update or posts is None:
		logging.error("DB QUERY")
		q = Post.all().order('-created').fetch(limit = 10)
		posts = list(q)
		mem_set(mc_key, posts)
	return posts

class Post(db.Model):
    subject = db.StringProperty(required = True)
    content = db.TextProperty(required = True)
    created = db.DateTimeProperty(auto_now_add = True)
    last_modified = db.DateTimeProperty(auto_now = True)

    def render(self):
		self._render_text = self.content.replace('\n', '<br>')
		permalink = "/blog/%s" %str(self.key().id())
		return render_str("post.html", p = self,permalink=permalink)



		
class BlogFront(BlogHandler):
    def get(self):
        #posts = db.GqlQuery("select * from Post order by created desc limit 10")
		posts=get_posts()
		self.render('front.html', posts = posts)

class PostPage(BlogHandler):
    def get(self, post_id):
		#key = db.Key.from_path('Post', int(post_id), parent=blog_key())
		#post = db.get(key)
		post_key ='POST_' + post_id
		post=mem_get(post_key)
		if not post:
			key = db.Key.from_path('Post', int(post_id), parent=blog_key())
			post = db.get(key)
			mem_set(post_key,post)
		if not post:
			self.error(404)
			return
		self.render("permalink.html", post = post)

class NewPost(BlogHandler):
	def get(self):
		if self.current_user:
			self.render("newpost.html")
		else:
			self.redirect("/login")
	
	def post(self):
		if not self.user:
			self.redirect('/blog')
		subject = self.request.get('subject')
		content = self.request.get('content')
		
		if subject and content:
			
			p = Post(parent = blog_key(), subject = subject, content = content)
			p.put()
			posts=get_posts(True)
			self.redirect('/blog/%s' % str(p.key().id()))
		else:
			error = "subject and content, please!"
			self.render("newpost.html", subject=subject, content=content, error=error)
			
			
			
class User(db.Model):
	name = db.StringProperty()
	pw_hash = db.StringProperty()
	email = db.StringProperty()
	avatar_url=db.StringProperty()
	link=db.StringProperty()
	@classmethod
	def by_id(cls, uid):
		return User.get_by_id(uid, parent = users_key())
		
	@classmethod
	def by_name(cls, name):
		u = User.all().filter('name =', name).get()
		return u
		
	@classmethod
	def register(cls, name, pw, email = None):
		pw_hash = make_pw_hash(name, pw)
		return User(parent = users_key(),
                    name = name,
                    pw_hash = pw_hash,
                    email = email)
					
	@classmethod
	def login(cls, name, pw):
		u = cls.by_name(name)
		if u and valid_pw(name, pw, u.pw_hash):
			return u
			
			
USER_RE = re.compile(r"^[a-zA-Z0-9_-]{3,20}$")
def valid_username(username):
    return username and USER_RE.match(username)

PASS_RE = re.compile(r"^.{3,20}$")
def valid_password(password):
    return password and PASS_RE.match(password)

EMAIL_RE  = re.compile(r'^[\S]+@[\S]+\.[\S]+$')
def valid_email(email):
    return not email or EMAIL_RE.match(email)

class Signup(BlogHandler):
    def get(self):
        self.render("signup-form.html")

    def post(self):
        have_error = False
        self.username = self.request.get('username')
        self.password = self.request.get('password')
        self.verify = self.request.get('verify')
        self.email = self.request.get('email')

        params = dict(username = self.username,
                      email = self.email)

        if not valid_username(self.username):
            params['error_username'] = "That's not a valid username."
            have_error = True

        if not valid_password(self.password):
            params['error_password'] = "That wasn't a valid password."
            have_error = True
        elif self.password != self.verify:
            params['error_verify'] = "Your passwords didn't match."
            have_error = True

        if not valid_email(self.email):
            params['error_email'] = "That's not a valid email."
            have_error = True

        if have_error:
            self.render('signup-form.html', **params)
        else:
			self.done()

    def done(self, *a, **kw):
        raise NotImplementedError
