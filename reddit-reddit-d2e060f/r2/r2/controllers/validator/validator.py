# The contents of this file are subject to the Common Public Attribution
# License Version 1.0. (the "License"); you may not use this file except in
# compliance with the License. You may obtain a copy of the License at
# http://code.reddit.com/LICENSE. The License is based on the Mozilla Public
# License Version 1.1, but Sections 14 and 15 have been added to cover use of
# software over a computer network and provide for limited attribution for the
# Original Developer. In addition, Exhibit A has been modified to be consistent
# with Exhibit B.
#
# Software distributed under the License is distributed on an "AS IS" basis,
# WITHOUT WARRANTY OF ANY KIND, either express or implied. See the License for
# the specific language governing rights and limitations under the License.
#
# The Original Code is reddit.
#
# The Original Developer is the Initial Developer.  The Initial Developer of
# the Original Code is reddit Inc.
#
# All portions of the code written by reddit are Copyright (c) 2006-2012 reddit
# Inc. All Rights Reserved.
###############################################################################

from pylons import c, g, request, response
from pylons.i18n import _
from pylons.controllers.util import abort
from r2.config.extensions import api_type
from r2.lib import utils, captcha, promote, totp
from r2.lib.filters import unkeep_space, websafe, _force_unicode
from r2.lib.filters import markdown_souptest
from r2.lib.db import tdb_cassandra
from r2.lib.db.operators import asc, desc
from r2.lib.template_helpers import add_sr
from r2.lib.jsonresponse import json_respond, JQueryResponse, JsonResponse
from r2.lib.log import log_text
from r2.models import *
from r2.lib.authorize import Address, CreditCard
from r2.lib.utils import constant_time_compare

from r2.controllers.errors import errors, UserRequiredException
from r2.controllers.errors import VerifiedUserRequiredException
from r2.controllers.errors import GoldRequiredException

from copy import copy
from datetime import datetime, timedelta
from curses.ascii import isprint
import re, inspect
import pycountry
from itertools import chain

def visible_promo(article):
    is_promo = getattr(article, "promoted", None) is not None
    is_author = (c.user_is_loggedin and
                 c.user._id == article.author_id)

    # subreddit discovery links are visible even without a live campaign
    if article._fullname in g.live_config['sr_discovery_links']:
        return True
    
    # promos are visible only if comments are not disabled and the
    # user is either the author or the link is live/previously live.
    if is_promo:
        return (c.user_is_sponsor or
                is_author or
                (not article.disable_comments and
                 article.promote_status >= promote.STATUS.promoted))
    # not a promo, therefore it is visible
    return True

def can_view_link_comments(article):
    return (article.subreddit_slow.can_view(c.user) and
            visible_promo(article))

def can_comment_link(article):
    return (article.subreddit_slow.can_comment(c.user) and
            visible_promo(article))

class Validator(object):
    default_param = None
    def __init__(self, param=None, default=None, post=True, get=True, url=True,
                 docs=None):
        if param:
            self.param = param
        else:
            self.param = self.default_param

        self.default = default
        self.post, self.get, self.url, self.docs = post, get, url, docs
        self.has_errors = False

    def set_error(self, error, msg_params={}, field=False, code=None):
        """
        Adds the provided error to c.errors and flags that it is come
        from the validator's param
        """
        if field is False:
            field = self.param

        c.errors.add(error, msg_params=msg_params, field=field, code=code)
        self.has_errors = True

    def param_docs(self):
        param_info = {}
        for param in filter(None, tup(self.param)):
            param_info[param] = None
        if self.docs:
            param_info.update(self.docs)
        return param_info

    def __call__(self, url):
        self.has_errors = False
        a = []
        if self.param:
            for p in utils.tup(self.param):
                if self.post and request.post.get(p):
                    val = request.post[p]
                elif self.get and request.get.get(p):
                    val = request.get[p]
                elif self.url and url.get(p):
                    val = url[p]
                else:
                    val = self.default
                a.append(val)
        try:
            return self.run(*a)
        except TypeError, e:
            if str(e).startswith('run() takes'):
                # Prepend our class name so we know *which* run()
                raise TypeError('%s.%s' % (type(self).__name__, str(e)))
            else:
                raise


def build_arg_list(fn, env):
    """given a fn and and environment the builds a keyword argument list
    for fn"""
    kw = {}
    argspec = inspect.getargspec(fn)

    # if there is a **kw argument in the fn definition,
    # just pass along the environment
    if argspec[2]:
        kw = env
    #else for each entry in the arglist set the value from the environment
    else:
        #skip self
        argnames = argspec[0][1:]
        for name in argnames:
            if name in env:
                kw[name] = env[name]
    return kw

def _make_validated_kw(fn, simple_vals, param_vals, env):
    for validator in simple_vals:
        validator(env)
    kw = build_arg_list(fn, env)
    for var, validator in param_vals.iteritems():
        kw[var] = validator(env)
    return kw

def set_api_docs(fn, simple_vals, param_vals):
    doc = fn._api_doc = getattr(fn, '_api_doc', {})
    param_info = doc.get('parameters', {})
    for validator in chain(simple_vals, param_vals.itervalues()):
        param_info.update(validator.param_docs())
    doc['parameters'] = param_info

make_validated_kw = _make_validated_kw

def validate(*simple_vals, **param_vals):
    def val(fn):
        @utils.wraps_api(fn)
        def newfn(self, *a, **env):
            try:
                kw = _make_validated_kw(fn, simple_vals, param_vals, env)
                return fn(self, *a, **kw)
            except UserRequiredException:
                return self.intermediate_redirect('/login')
            except VerifiedUserRequiredException:
                return self.intermediate_redirect('/verify')

        set_api_docs(newfn, simple_vals, param_vals)
        return newfn
    return val


def api_validate(response_type=None):
    """
    Factory for making validators for API calls, since API calls come
    in two flavors: responsive and unresponsive.  The machinary
    associated with both is similar, and the error handling identical,
    so this function abstracts away the kw validation and creation of
    a Json-y responder object.
    """
    def wrap(response_function):
        def _api_validate(*simple_vals, **param_vals):
            def val(fn):
                @utils.wraps_api(fn)
                def newfn(self, *a, **env):
                    renderstyle = request.params.get("renderstyle")
                    if renderstyle:
                        c.render_style = api_type(renderstyle)
                    elif not c.extension:
                        # if the request URL included an extension, don't
                        # touch the render_style, since it was already set by
                        # set_extension. if no extension was provided, default
                        # to response_type.
                        c.render_style = api_type(response_type)

                    # generate a response object
                    if response_type == "html" and not request.params.get('api_type') == "json":
                        responder = JQueryResponse()
                    else:
                        responder = JsonResponse()

                    c.response_content_type = responder.content_type

                    try:
                        kw = _make_validated_kw(fn, simple_vals, param_vals, env)
                        return response_function(self, fn, responder,
                                                 simple_vals, param_vals, *a, **kw)
                    except UserRequiredException:
                        responder.send_failure(errors.USER_REQUIRED)
                        return self.api_wrapper(responder.make_response())
                    except VerifiedUserRequiredException:
                        responder.send_failure(errors.VERIFIED_USER_REQUIRED)
                        return self.api_wrapper(responder.make_response())

                set_api_docs(newfn, simple_vals, param_vals)
                return newfn
            return val
        return _api_validate
    return wrap


@api_validate("html")
def noresponse(self, self_method, responder, simple_vals, param_vals, *a, **kw):
    self_method(self, *a, **kw)
    return self.api_wrapper({})

@api_validate("html")
def textresponse(self, self_method, responder, simple_vals, param_vals, *a, **kw):
    return self_method(self, *a, **kw)

@api_validate()
def json_validate(self, self_method, responder, simple_vals, param_vals, *a, **kw):
    if c.extension != 'json':
        abort(404)

    val = self_method(self, responder, *a, **kw)
    if val is None:
        val = responder.make_response()
    return self.api_wrapper(val)

def _validatedForm(self, self_method, responder, simple_vals, param_vals,
                  *a, **kw):
    # generate a form object
    form = responder(request.POST.get('id', "body"))

    # clear out the status line as a courtesy
    form.set_html(".status", "")

    # do the actual work
    val = self_method(self, form, responder, *a, **kw)

    # add data to the output on some errors
    for validator in simple_vals:
        if (isinstance(validator, VCaptcha) and
            form.has_errors('captcha', errors.BAD_CAPTCHA)):
            form.new_captcha()
        elif (isinstance(validator, VRatelimit) and
              form.has_errors('ratelimit', errors.RATELIMIT)):
            form.ratelimit(validator.seconds)

    if val:
        return val
    else:
        return self.api_wrapper(responder.make_response())

@api_validate("html")
def validatedForm(self, self_method, responder, simple_vals, param_vals,
                  *a, **kw):
    return _validatedForm(self, self_method, responder, simple_vals, param_vals,
                          *a, **kw)

@api_validate("html")
def validatedMultipartForm(self, self_method, responder, simple_vals,
                           param_vals, *a, **kw):
    def wrapped_self_method(*a, **kw):
        val = self_method(*a, **kw)
        if val:
            return val
        else:
            return self.iframe_api_wrapper(responder.make_response())
    return _validatedForm(self, wrapped_self_method, responder, simple_vals,
                          param_vals, *a, **kw)


#### validators ####
class nop(Validator):
    def run(self, x):
        return x

class VLang(Validator):
    def run(self, lang):
        if lang in g.all_languages:
            return lang
        return g.lang

class VRequired(Validator):
    def __init__(self, param, error, *a, **kw):
        Validator.__init__(self, param, *a, **kw)
        self._error = error

    def error(self, e = None):
        if not e: e = self._error
        if e:
            self.set_error(e)

    def run(self, item):
        if not item:
            self.error()
        else:
            return item

class VThing(Validator):
    def __init__(self, param, thingclass, redirect = True, *a, **kw):
        Validator.__init__(self, param, *a, **kw)
        self.thingclass = thingclass
        self.redirect = redirect

    def run(self, thing_id):
        if thing_id:
            try:
                tid = int(thing_id, 36)
                thing = self.thingclass._byID(tid, True)
                if thing.__class__ != self.thingclass:
                    raise TypeError("Expected %s, got %s" %
                                    (self.thingclass, thing.__class__))
                return thing
            except (NotFound, ValueError):
                if self.redirect:
                    abort(404, 'page not found')
                else:
                    return None

class VLink(VThing):
    def __init__(self, param, redirect = True, *a, **kw):
        VThing.__init__(self, param, Link, redirect=redirect, *a, **kw)

class VCommentByID(VThing):
    def __init__(self, param, redirect = True, *a, **kw):
        VThing.__init__(self, param, Comment, redirect=redirect, *a, **kw)

class VAd(VThing):
    def __init__(self, param, redirect = True, *a, **kw):
        VThing.__init__(self, param, Ad, redirect=redirect, *a, **kw)

class VAdByCodename(Validator):
    def run(self, codename, required_fullname=None):
        if not codename:
            return self.set_error(errors.NO_TEXT)

        try:
            a = Ad._by_codename(codename)
        except NotFound:
            a = None

        if a and required_fullname and a._fullname != required_fullname:
            return self.set_error(errors.INVALID_OPTION)
        else:
            return a

class VAward(VThing):
    def __init__(self, param, redirect = True, *a, **kw):
        VThing.__init__(self, param, Award, redirect=redirect, *a, **kw)

class VAwardByCodename(Validator):
    def run(self, codename, required_fullname=None):
        if not codename:
            return self.set_error(errors.NO_TEXT)

        try:
            a = Award._by_codename(codename)
        except NotFound:
            a = None

        if a and required_fullname and a._fullname != required_fullname:
            return self.set_error(errors.INVALID_OPTION)
        else:
            return a

class VTrophy(VThing):
    def __init__(self, param, redirect = True, *a, **kw):
        VThing.__init__(self, param, Trophy, redirect=redirect, *a, **kw)

class VMessage(Validator):
    def run(self, message_id):
        if message_id:
            try:
                aid = int(message_id, 36)
                return Message._byID(aid, True)
            except (NotFound, ValueError):
                abort(404, 'page not found')


class VCommentID(Validator):
    def run(self, cid):
        if cid:
            try:
                cid = int(cid, 36)
                return Comment._byID(cid, True)
            except (NotFound, ValueError):
                pass

class VMessageID(Validator):
    def run(self, cid):
        if cid:
            try:
                cid = int(cid, 36)
                m = Message._byID(cid, True)
                if not m.can_view_slow():
                    abort(403, 'forbidden')
                return m
            except (NotFound, ValueError):
                pass

class VCount(Validator):
    def run(self, count):
        if count is None:
            count = 0
        try:
            return max(int(count), 0)
        except ValueError:
            return 0


class VLimit(Validator):
    def __init__(self, param, default=25, max_limit=100, **kw):
        self.default_limit = default
        self.max_limit = max_limit
        Validator.__init__(self, param, **kw)

    def run(self, limit):
        default = c.user.pref_numsites
        if c.render_style in ("compact", api_type("compact")):
            default = self.default_limit  # TODO: ini param?

        if limit is None:
            return default

        try:
            i = int(limit)
        except ValueError:
            return default

        return min(max(i, 1), self.max_limit)

class VCssMeasure(Validator):
    measure = re.compile(r"\A\s*[\d\.]+\w{0,3}\s*\Z")
    def run(self, value):
        return value if value and self.measure.match(value) else ''

subreddit_rx = re.compile(r"\A[A-Za-z0-9][A-Za-z0-9_]{2,20}\Z")

def chksrname(x):
    #notice the space before reddit.com
    if x in ('friends', 'all', ' reddit.com'):
        return False

    try:
        return str(x) if x and subreddit_rx.match(x) else None
    except UnicodeEncodeError:
        return None


class VLength(Validator):
    only_whitespace = re.compile(r"\A\s*\Z", re.UNICODE)

    def __init__(self, param, max_length,
                 empty_error = errors.NO_TEXT,
                 length_error = errors.TOO_LONG,
                 **kw):
        Validator.__init__(self, param, **kw)
        self.max_length = max_length
        self.length_error = length_error
        self.empty_error = empty_error

    def run(self, text, text2 = ''):
        text = text or text2
        if self.empty_error and (not text or self.only_whitespace.match(text)):
            self.set_error(self.empty_error)
        elif len(text) > self.max_length:
            self.set_error(self.length_error, {'max_length': self.max_length})
        else:
            return text

class VPrintable(VLength):
    def run(self, text, text2 = ''):
        text = VLength.run(self, text, text2)

        if text is None:
            return None

        try:
            if all(isprint(str(x)) for x in text):
                return str(text)
        except UnicodeEncodeError:
            pass

        self.set_error(errors.BAD_STRING)
        return None


class VTitle(VLength):
    def __init__(self, param, max_length = 300, **kw):
        VLength.__init__(self, param, max_length, **kw)

class VMarkdown(VLength):
    def __init__(self, param, max_length = 10000, **kw):
        VLength.__init__(self, param, max_length, **kw)

    def run(self, text, text2 = ''):
        text = text or text2
        VLength.run(self, text)
        try:
            markdown_souptest(text)
            return text
        except ValueError:
            import sys
            user = "???"
            if c.user_is_loggedin:
                user = c.user.name
            g.log.error("HAX by %s: %s" % (user, text))
            s = sys.exc_info()
            # reraise the original error with the original stack trace
            raise s[1], None, s[2]

class VSelfText(VMarkdown):

    def set_max_length(self, val):
        self._max_length = val

    def get_max_length(self):
        if c.site.link_type == "self":
            return self._max_length * 4
        return self._max_length * 1.5

    max_length = property(get_max_length, set_max_length)

class VSubredditName(VRequired):
    def __init__(self, item, *a, **kw):
        VRequired.__init__(self, item, errors.BAD_SR_NAME, *a, **kw)

    def run(self, name):
        name = chksrname(name)
        if not name:
            return self.error()
        else:
            try:
                a = Subreddit._by_name(name)
                return self.error(errors.SUBREDDIT_EXISTS)
            except NotFound:
                return name

class VSubredditTitle(Validator):
    def run(self, title):
        if not title:
            self.set_error(errors.NO_TITLE)
        elif len(title) > 100:
            self.set_error(errors.TITLE_TOO_LONG)
        else:
            return title

class VSubredditDesc(Validator):
    def run(self, description):
        if description and len(description) > 500:
            self.set_error(errors.DESC_TOO_LONG)
        return unkeep_space(description or '')

class VAccountByName(VRequired):
    def __init__(self, param, error = errors.USER_DOESNT_EXIST, *a, **kw):
        VRequired.__init__(self, param, error, *a, **kw)

    def run(self, name):
        if name:
            try:
                return Account._by_name(name)
            except NotFound: pass
        return self.error()

def fullname_regex(thing_cls = None, multiple = False):
    pattern = "[%s%s]" % (Relation._type_prefix, Thing._type_prefix)
    if thing_cls:
        pattern += utils.to36(thing_cls._type_id)
    else:
        pattern += r"[0-9a-z]+"
    pattern += r"_[0-9a-z]+"
    if multiple:
        pattern = r"(%s *,? *)+" % pattern
    return re.compile(r"\A" + pattern + r"\Z")

class VByName(Validator):
    # Lookup tdb_sql.Thing or tdb_cassandra.Thing objects by fullname. 
    splitter = re.compile('[ ,]+')
    def __init__(self, param, thing_cls=None, multiple=False, limit=None,
                 error=errors.NO_THING_ID, backend='sql', **kw):
        # Limit param only applies when multiple is True
        if not multiple and limit is not None:
            raise TypeError('multiple must be True when limit is set')
        self.re = fullname_regex(thing_cls)
        self.multiple = multiple
        self.limit = limit
        self._error = error
        self.backend = backend

        Validator.__init__(self, param, **kw)
    
    def run(self, items):
        if self.backend == 'cassandra':
            # tdb_cassandra.Thing objects can't use the regex
            if items and self.multiple:
                items = [item for item in self.splitter.split(items)]
                if self.limit and len(items) > self.limit:
                    return self.set_error(errors.TOO_MANY_THING_IDS)
            if items:                        
                try:
                    return tdb_cassandra.Thing._by_fullname(items, return_dict=False)
                except NotFound:
                    pass
        else:
            if items and self.multiple:
                items = [item for item in self.splitter.split(items)
                         if item and self.re.match(item)]
                if self.limit and len(items) > self.limit:
                    return self.set_error(errors.TOO_MANY_THING_IDS)
            if items and (self.multiple or self.re.match(items)):
                try:
                    return Thing._by_fullname(items, return_dict=False,
                                              data=True)
                except NotFound:
                    pass

        return self.set_error(self._error)

    def param_docs(self):
        return {
            self.param: _('an existing thing id')
        }

class VByNameIfAuthor(VByName):
    def run(self, fullname):
        thing = VByName.run(self, fullname)
        if thing:
            if not thing._loaded: thing._load()
            if c.user_is_loggedin and thing.author_id == c.user._id:
                return thing
        return self.set_error(errors.NOT_AUTHOR)

class VCaptcha(Validator):
    default_param = ('iden', 'captcha')
    
    def run(self, iden, solution):
        if c.user.needs_captcha():
            valid_captcha = captcha.valid_solution(iden, solution)
            if not valid_captcha:
                self.set_error(errors.BAD_CAPTCHA)
            g.stats.action_event_count("captcha", valid_captcha)

class VUser(Validator):
    def run(self, password = None):
        if not c.user_is_loggedin:
            raise UserRequiredException

        if (password is not None) and not valid_password(c.user, password):
            self.set_error(errors.WRONG_PASSWORD)

class VModhash(Validator):
    default_param = 'uh'
    def __init__(self, param=None, fatal=True, *a, **kw):
        Validator.__init__(self, param, *a, **kw)
        self.fatal = fatal

    def run(self, uh):
        pass

    def param_docs(self):
        return {
            self.param: _('a modhash')
        }

class VVotehash(Validator):
    def run(self, vh, thing_name):
        return True

class VAdmin(Validator):
    def run(self):
        if not c.user_is_admin:
            abort(404, "page not found")

class VAdminOrAdminSecret(VAdmin):
    def run(self, secret):
        '''If validation succeeds, return True if the secret was used,
        False otherwise'''
        if secret and constant_time_compare(secret, g.ADMINSECRET):
            return True
        super(VAdminOrAdminSecret, self).run()
        return False

class VVerifiedUser(VUser):
    def run(self):
        VUser.run(self)
        if not c.user.email_verified:
            raise VerifiedUserRequiredException

class VGold(VUser):
    def run(self):
        VUser.run(self)
        if not c.user.gold:
            abort(403, 'forbidden')

class VSponsorAdmin(VVerifiedUser):
    """
    Validator which checks c.user_is_sponsor
    """
    def user_test(self, thing):
        return (thing.author_id == c.user._id)

    def run(self, link_id = None):
        VVerifiedUser.run(self)
        if c.user_is_sponsor:
            return
        abort(403, 'forbidden')

class VSponsor(VVerifiedUser):
    """
    Not intended to be used as a check for c.user_is_sponsor, but
    rather is the user allowed to use the sponsored link system and,
    if there is a link passed in, is the user allowed to edit the link
    in question.
    """
    def user_test(self, thing):
        return (thing.author_id == c.user._id)

    def run(self, link_id = None):
        VVerifiedUser.run(self)
        if c.user_is_sponsor:
            return
        elif link_id:
            try:
                if '_' in link_id:
                    t = Link._by_fullname(link_id, True)
                else:
                    aid = int(link_id, 36)
                    t = Link._byID(aid, True)
                if self.user_test(t):
                    return
            except (NotFound, ValueError):
                pass
            abort(403, 'forbidden')

class VTrafficViewer(VSponsor):
    def user_test(self, thing):
        return (VSponsor.user_test(self, thing) or
                promote.is_traffic_viewer(thing, c.user))

class VSrModerator(Validator):
    def run(self):
        if not (c.user_is_loggedin and c.site.is_moderator(c.user) 
                or c.user_is_admin):
            abort(403, "forbidden")

class VFlairManager(VSrModerator):
    """Validates that a user is permitted to manage flair for a subreddit.
       
    Currently this is the same as VSrModerator. It's a separate class to act as
    a placeholder if we ever need to give mods a way to delegate this aspect of
    subreddit administration."""
    pass

class VCanDistinguish(VByName):
    def run(self, thing_name, how):
        if c.user_is_admin:
            return True
        elif c.user_is_loggedin:
            item = VByName.run(self, thing_name)
            if item.author_id == c.user._id:
                # will throw a legitimate 500 if this isn't a link or
                # comment, because this should only be used on links and
                # comments
                subreddit = item.subreddit_slow
                if how in ("yes", "no") and subreddit.can_distinguish(c.user):
                    return True
                elif how in ("special", "no") and c.user_special_distinguish:
                    return True

        abort(403,'forbidden')

class VSrCanAlter(VByName):
    def run(self, thing_name):
        if c.user_is_admin:
            return True
        elif c.user_is_loggedin:
            item = VByName.run(self, thing_name)
            if item.author_id == c.user._id:
                return True
            else:
                # will throw a legitimate 500 if this isn't a link or
                # comment, because this should only be used on links and
                # comments
                subreddit = item.subreddit_slow
                if subreddit.can_distinguish(c.user):
                    return True
        abort(403,'forbidden')

class VSrCanBan(VByName):
    def run(self, thing_name):
        if c.user_is_admin:
            return 'admin'
        elif c.user_is_loggedin:
            item = VByName.run(self, thing_name)
            # will throw a legitimate 500 if this isn't a link or
            # comment, because this should only be used on links and
            # comments
            subreddit = item.subreddit_slow
            if subreddit.is_moderator(c.user):
                return 'mod'
            # elif subreddit.is_contributor(c.user):
            #     return 'contributor'
        abort(403,'forbidden')

class VSrSpecial(VByName):
    def run(self, thing_name):
        if c.user_is_admin:
            return True
        elif c.user_is_loggedin:
            item = VByName.run(self, thing_name)
            # will throw a legitimate 500 if this isn't a link or
            # comment, because this should only be used on links and
            # comments
            subreddit = item.subreddit_slow
            if subreddit.is_special(c.user):
                return True
        abort(403,'forbidden')


class VSubmitParent(VByName):
    def run(self, fullname, fullname2):
        #for backwards compatability (with iphone app)
        fullname = fullname or fullname2
        if fullname:
            parent = VByName.run(self, fullname)
            if parent:
                if c.user_is_loggedin and parent.author_id in c.user.enemies:
                    self.set_error(errors.USER_BLOCKED)
                if parent._deleted:
                    if isinstance(parent, Link):
                        self.set_error(errors.DELETED_LINK)
                    else:
                        self.set_error(errors.DELETED_COMMENT)
            if isinstance(parent, Message):
                return parent
            else:
                link = parent
                if isinstance(parent, Comment):
                    link = Link._byID(parent.link_id, data=True)
                if link and c.user_is_loggedin and can_comment_link(link):
                    return parent
        #else
        abort(403, "forbidden")

    def param_docs(self):
        return {
            self.param[0]: _('id of parent thing')
        }

class VSubmitSR(Validator):
    def __init__(self, srname_param, linktype_param=None, promotion=False):
        self.require_linktype = False
        self.promotion = promotion

        if linktype_param:
            self.require_linktype = True
            Validator.__init__(self, (srname_param, linktype_param))
        else:
            Validator.__init__(self, srname_param)

    def run(self, sr_name, link_type = None):
        if not sr_name:
            self.set_error(errors.SUBREDDIT_REQUIRED)
            return None

        try:
            sr = Subreddit._by_name(str(sr_name).strip())
        except (NotFound, AttributeError, UnicodeEncodeError):
            self.set_error(errors.SUBREDDIT_NOEXIST)
            return

        if not c.user_is_loggedin or not sr.can_submit(c.user, self.promotion):
            self.set_error(errors.SUBREDDIT_NOTALLOWED)
            return

        if self.require_linktype:
            if link_type not in ('link', 'self'):
                self.set_error(errors.INVALID_OPTION)
                return
            elif link_type == 'link' and sr.link_type == 'self':
                self.set_error(errors.NO_LINKS)
                return
            elif link_type == 'self' and sr.link_type == 'link':
                self.set_error(errors.NO_SELFS)
                return

        return sr

class VSubscribeSR(VByName):
    def __init__(self, srid_param, srname_param):
        VByName.__init__(self, (srid_param, srname_param)) 

    def run(self, sr_id, sr_name):
        if sr_id:
            return VByName.run(self, sr_id)
        elif not sr_name:
            return

        try:
            sr = Subreddit._by_name(str(sr_name).strip())
        except (NotFound, AttributeError, UnicodeEncodeError):
            self.set_error(errors.SUBREDDIT_NOEXIST)
            return

        return sr

MIN_PASSWORD_LENGTH = 3

class VPassword(Validator):
    def run(self, password, verify):
        if not (password and len(password) >= MIN_PASSWORD_LENGTH):
            self.set_error(errors.BAD_PASSWORD)
        elif verify != password:
            self.set_error(errors.BAD_PASSWORD_MATCH)
        else:
            return password.encode('utf8')

user_rx = re.compile(r"\A[\w-]{3,20}\Z", re.UNICODE)

def chkuser(x):
    if x is None:
        return None
    try:
        if any(ch.isspace() for ch in x):
            return None
        return str(x) if user_rx.match(x) else None
    except TypeError:
        return None
    except UnicodeEncodeError:
        return None

class VUname(VRequired):
    def __init__(self, item, *a, **kw):
        VRequired.__init__(self, item, errors.BAD_USERNAME, *a, **kw)
    def run(self, user_name):
        user_name = chkuser(user_name)
        if not user_name:
            return self.error(errors.BAD_USERNAME)
        else:
            try:
                a = Account._by_name(user_name, True)
                if a._deleted:
                   return self.error(errors.USERNAME_TAKEN_DEL)
                else:
                   return self.error(errors.USERNAME_TAKEN)
            except NotFound:
                return user_name

class VLogin(VRequired):
    def __init__(self, item, *a, **kw):
        VRequired.__init__(self, item, errors.WRONG_PASSWORD, *a, **kw)

    def run(self, user_name, password):
        user_name = chkuser(user_name)
        user = None
        if user_name:
            try:
                str(password)
            except UnicodeEncodeError:
                password = password.encode('utf8')
            user = valid_login(user_name, password)
        if not user:
            self.error()
            return False
        return user

class VThrottledLogin(VLogin):
    def __init__(self, *args, **kwargs):
        VLogin.__init__(self, *args, **kwargs)
        self.vdelay = VDelay("login")
        self.vlength = VLength("user", max_length=100)
        
    def run(self, username, password):
        if username:
            username = username.strip()
        username = self.vlength.run(username)

        self.vdelay.run()
        if (errors.RATELIMIT, "vdelay") in c.errors:
            return False

        user = VLogin.run(self, username, password)
        if login_throttle(username, wrong_password=not user):
            VDelay.record_violation("login", seconds=1, growfast=True)
            c.errors.add(errors.WRONG_PASSWORD, field=self.param[1])
        else:
            return user

class VSanitizedUrl(Validator):
    def run(self, url):
        return utils.sanitize_url(url)

    def param_docs(self):
        return {self.param: _("a valid URL")}

class VUrl(VRequired):
    def __init__(self, item, allow_self = True, lookup = True, *a, **kw):
        self.allow_self = allow_self
        self.lookup = lookup
        VRequired.__init__(self, item, errors.NO_URL, *a, **kw)

    def run(self, url, sr = None, resubmit=False):
        if sr is None and not isinstance(c.site, FakeSubreddit):
            sr = c.site
        elif sr:
            try:
                sr = Subreddit._by_name(str(sr))
            except (NotFound, UnicodeEncodeError):
                self.set_error(errors.SUBREDDIT_NOEXIST)
                sr = None
        else:
            sr = None

        if not url:
            return self.error(errors.NO_URL)
        url = utils.sanitize_url(url)
        if not url:
            return self.error(errors.BAD_URL)

        if url == 'self':
            if self.allow_self:
                return url
        elif not self.lookup or resubmit:
            return url
        elif url:
            try:
                l = Link._by_url(url, sr)
                self.error(errors.ALREADY_SUB)
                return utils.tup(l)
            except NotFound:
                return url
        return self.error(errors.BAD_URL)

    def param_docs(self):
        if isinstance(self.param, (list, tuple)):
            param_names = self.param
        else:
            param_names = [self.param]
        params = {}
        try:
            params[param_names[0]] = _('a valid URL')
            params[param_names[1]] = _('a subreddit')
            params[param_names[2]] = _('boolean value')
        except IndexError:
            pass
        return params

class VShamedDomain(Validator):
    def run(self, url):
        if not url:
            return

        is_shamed, domain, reason = is_shamed_domain(url, request.ip)

        if is_shamed:
            self.set_error(errors.DOMAIN_BANNED, dict(domain=domain,
                                                      reason=reason))

class VExistingUname(VRequired):
    def __init__(self, item, *a, **kw):
        VRequired.__init__(self, item, errors.NO_USER, *a, **kw)

    def run(self, name):
        if name and name.startswith('~') and c.user_is_admin:
            try:
                user_id = int(name[1:])
                return Account._byID(user_id, True)
            except (NotFound, ValueError):
                self.error(errors.USER_DOESNT_EXIST)

        # make sure the name satisfies our user name regexp before
        # bothering to look it up.
        name = chkuser(name)
        if name:
            try:
                return Account._by_name(name)
            except NotFound:
                self.error(errors.USER_DOESNT_EXIST)
        else:
            self.error()

    def param_docs(self):
        return {
            self.param: _('the name of an existing user')
        }

class VMessageRecipient(VExistingUname):
    def run(self, name):
        if not name:
            return self.error()
        is_subreddit = False
        if name.startswith('/r/'):
            name = name[3:]
            is_subreddit = True
        elif name.startswith('#'):
            name = name[1:]
            is_subreddit = True
        if is_subreddit:
            try:
                s = Subreddit._by_name(name)
                if isinstance(s, FakeSubreddit):
                    raise NotFound, "fake subreddit"
                if s._spam:
                    raise NotFound, "banned community"
                return s
            except NotFound:
                self.set_error(errors.SUBREDDIT_NOEXIST)
        else:
            account = VExistingUname.run(self, name)
            if account and account._id in c.user.enemies:
                self.set_error(errors.USER_BLOCKED)
            else:
                return account

class VUserWithEmail(VExistingUname):
    def run(self, name):
        user = VExistingUname.run(self, name)
        if not user or not hasattr(user, 'email') or not user.email:
            return self.error(errors.NO_EMAIL_FOR_USER)
        return user


class VBoolean(Validator):
    def run(self, val):
        lv = str(val).lower()
        if lv == 'off' or lv == '' or lv[0] in ("f", "n"):
            return False
        return bool(val)

    def param_docs(self):
        return {
            self.param: _('boolean value')
        }

class VNumber(Validator):
    def __init__(self, param, min=None, max=None, coerce = True,
                 error=errors.BAD_NUMBER, num_default=None,
                 *a, **kw):
        self.min = self.cast(min) if min is not None else None
        self.max = self.cast(max) if max is not None else None
        self.coerce = coerce
        self.error = error
        self.num_default = num_default
        Validator.__init__(self, param, *a, **kw)

    def cast(self, val):
        raise NotImplementedError

    def run(self, val):
        if not val:
            return self.num_default
        try:
            val = self.cast(val)
            if self.min is not None and val < self.min:
                if self.coerce:
                    val = self.min
                else:
                    raise ValueError, ""
            elif self.max is not None and val > self.max:
                if self.coerce:
                    val = self.max
                else:
                    raise ValueError, ""
            return val
        except ValueError:
            if self.max is None and self.min is None:
                range = ""
            elif self.max is None:
                range = _("%(min)d to any") % dict(min=self.min)
            elif self.min is None:
                range = _("any to %(max)d") % dict(max=self.max)
            else:
                range = _("%(min)d to %(max)d") % dict(min=self.min, max=self.max)
            self.set_error(self.error, msg_params=dict(range=range))

class VInt(VNumber):
    def cast(self, val):
        return int(val)

class VFloat(VNumber):
    def cast(self, val):
        return float(val)

class VBid(VNumber):
    '''
    DEPRECATED. Use VFloat instead and check bid amount in function body.
    '''
    def __init__(self, bid, link_id, sr):
        self.duration = 1
        VNumber.__init__(self, (bid, link_id, sr),
                         # targeting is a little more expensive
                         min = g.min_promote_bid,
                         max = g.max_promote_bid, coerce = False,
                         error = errors.BAD_BID)

    def cast(self, val):
        return float(val)/self.duration

    def run(self, bid, link_id, sr = None):
        if link_id:
            try:
                link = Thing._by_fullname(link_id, return_dict = False,
                                          data=True)
                self.duration = max((link.promote_until - link._date).days, 1)
            except NotFound:
                pass
        if VNumber.run(self, bid):
            if sr:
                if self.cast(bid) >= self.min * 1.5:
                    return float(bid)
                else:
                    self.set_error(self.error, msg_params = dict(min=self.min * 1.5,
                                                                 max=self.max))
            else:
                return float(bid)


class VCssName(Validator):
    """
    returns a name iff it consists of alphanumeric characters and
    possibly "-", and is below the length limit.
    """

    r_css_name = re.compile(r"\A[a-zA-Z0-9\-]{1,100}\Z")

    def run(self, name):
        if name:
            if self.r_css_name.match(name):
                return name
            else:
                self.set_error(errors.BAD_CSS_NAME)
        return ''


class VMenu(Validator):

    def __init__(self, param, menu_cls, remember = True, **kw):
        self.nav = menu_cls
        self.remember = remember
        param = (menu_cls.name, param)
        Validator.__init__(self, param, **kw)

    def run(self, sort, where):
        if self.remember:
            pref = "%s_%s" % (where, self.nav.name)
            user_prefs = copy(c.user.sort_options) if c.user else {}
            user_pref = user_prefs.get(pref)

            # check to see if a default param has been set
            if not sort:
                sort = user_pref

        # validate the sort
        if sort not in self.nav.options:
            sort = self.nav.default

        # commit the sort if changed and if this is a POST request
        if (self.remember and c.user_is_loggedin and sort != user_pref
            and request.method.upper() == 'POST'):
            user_prefs[pref] = sort
            c.user.sort_options = user_prefs
            user = c.user
            user._commit()

        return sort


class VRatelimit(Validator):
    def __init__(self, rate_user = False, rate_ip = False,
                 prefix = 'rate_', error = errors.RATELIMIT, *a, **kw):
        self.rate_user = rate_user
        self.rate_ip = rate_ip
        self.prefix = prefix
        self.error = error
        self.seconds = None
        Validator.__init__(self, *a, **kw)

    def run (self):
        from r2.models.admintools import admin_ratelimit

        if g.disable_ratelimit:
            return

        if c.user_is_loggedin and not admin_ratelimit(c.user):
            return

        to_check = []
        if self.rate_user and c.user_is_loggedin:
            to_check.append('user' + str(c.user._id36))
        if self.rate_ip:
            to_check.append('ip' + str(request.ip))

        r = g.cache.get_multi(to_check, self.prefix)
        if r:
            expire_time = max(r.values())
            time = utils.timeuntil(expire_time)

            g.log.debug("rate-limiting %s from %s" % (self.prefix, r.keys()))

            # when errors have associated field parameters, we'll need
            # to add that here
            if self.error == errors.RATELIMIT:
                from datetime import datetime
                delta = expire_time - datetime.now(g.tz)
                self.seconds = delta.total_seconds()
                if self.seconds < 3:  # Don't ratelimit within three seconds
                    return
                self.set_error(errors.RATELIMIT, {'time': time},
                               field = 'ratelimit')
            else:
                self.set_error(self.error)

    @classmethod
    def ratelimit(self, rate_user = False, rate_ip = False, prefix = "rate_",
                  seconds = None):
        to_set = {}
        if seconds is None:
            seconds = g.RATELIMIT*60
        expire_time = datetime.now(g.tz) + timedelta(seconds = seconds)
        if rate_user and c.user_is_loggedin:
            to_set['user' + str(c.user._id36)] = expire_time
        if rate_ip:
            to_set['ip' + str(request.ip)] = expire_time
        g.cache.set_multi(to_set, prefix = prefix, time = seconds)

class VDelay(Validator):
    def __init__(self, category, *a, **kw):
        self.category = category
        Validator.__init__(self, *a, **kw)

    def run (self):
        if g.disable_ratelimit:
            return
        key = "VDelay-%s-%s" % (self.category, request.ip)
        prev_violations = g.cache.get(key)
        if prev_violations:
            time = utils.timeuntil(prev_violations["expire_time"])
            if prev_violations["expire_time"] > datetime.now(g.tz):
                self.set_error(errors.RATELIMIT, {'time': time},
                               field='vdelay')

    @classmethod
    def record_violation(self, category, seconds = None, growfast=False):
        if seconds is None:
            seconds = g.RATELIMIT*60

        key = "VDelay-%s-%s" % (category, request.ip)
        prev_violations = g.memcache.get(key)
        if prev_violations is None:
            prev_violations = dict(count=0)

        num_violations = prev_violations["count"]

        if growfast:
            multiplier = 3 ** num_violations
        else:
            multiplier = 1

        max_duration = 8 * 3600
        duration = min(seconds * multiplier, max_duration)

        expire_time = (datetime.now(g.tz) +
                       timedelta(seconds = duration))

        prev_violations["expire_time"] = expire_time
        prev_violations["duration"] = duration
        prev_violations["count"] += 1

        with g.make_lock("record_violation", "lock-" + key, timeout=5, verbose=False):
            existing = g.memcache.get(key)
            if existing and existing["count"] > prev_violations["count"]:
                g.log.warning("Tried to set %s to count=%d, but found existing=%d"
                             % (key, prev_violations["count"], existing["count"]))
            else:
                g.cache.set(key, prev_violations, max_duration)

class VCommentIDs(Validator):
    #id_str is a comma separated list of id36's
    def run(self, id_str):
        if id_str:
            cids = [int(i, 36) for i in id_str.split(',')]
            comments = Comment._byID(cids, data=True, return_dict = False)
            return comments
        return []


class CachedUser(object):
    def __init__(self, cache_prefix, user, key):
        self.cache_prefix = cache_prefix
        self.user = user
        self.key = key

    def clear(self):
        if self.key and self.cache_prefix:
            g.cache.delete(str(self.cache_prefix + "_" + self.key))

class VOneTimeToken(Validator):
    def __init__(self, model, param, *args, **kwargs):
        self.model = model
        Validator.__init__(self, param, *args, **kwargs)

    def run(self, key):
        token = self.model.get_token(key)

        if token:
            return token
        else:
            self.set_error(errors.EXPIRED)
            return None

class VOneOf(Validator):
    def __init__(self, param, options = (), *a, **kw):
        Validator.__init__(self, param, *a, **kw)
        self.options = options

    def run(self, val):
        if self.options and val not in self.options:
            self.set_error(errors.INVALID_OPTION)
            return self.default
        else:
            return val

    def param_docs(self):
        return {
            self.param: _('one of (%s)') % ', '.join(self.options)
        }

class VImageType(Validator):
    def run(self, img_type):
        if not img_type in ('png', 'jpg'):
            return 'png'
        return img_type

class VSubredditSponsorship(VInt):
    max = 1
    min = 0
    def run(self, val):
        s = super(VSubredditSponsorship, self).run(val)
        if s and not c.user_is_admin:
            abort(403, "forbidden")
        return s

class ValidEmails(Validator):
    """Validates a list of email addresses passed in as a string and
    delineated by whitespace, ',' or ';'.  Also validates quantity of
    provided emails.  Returns a list of valid email addresses on
    success"""
    
    separator = re.compile(r'[^\s,;]+')
    email_re  = re.compile(r'.+@.+\..+')

    def __init__(self, param, num = 20, **kw):
        self.num = num
        Validator.__init__(self, param = param, **kw)
        
    def run(self, emails0):
        emails = set(self.separator.findall(emails0) if emails0 else [])
        failures = set(e for e in emails if not self.email_re.match(e))
        emails = emails - failures

        # make sure the number of addresses does not exceed the max
        if self.num > 0 and len(emails) + len(failures) > self.num:
            # special case for 1: there should be no delineators at all, so
            # send back original string to the user
            if self.num == 1:
                self.set_error(errors.BAD_EMAILS,
                             {'emails': '"%s"' % emails0})
            # else report the number expected
            else:
                self.set_error(errors.TOO_MANY_EMAILS,
                             {'num': self.num})
        # correct number, but invalid formatting
        elif failures:
            self.set_error(errors.BAD_EMAILS,
                         {'emails': ', '.join(failures)})
        # no emails
        elif not emails:
            self.set_error(errors.NO_EMAILS)
        else:
            # return single email if one is expected, list otherwise
            return list(emails)[0] if self.num == 1 else emails


class VCnameDomain(Validator):
    domain_re  = re.compile(r'\A([\w\-_]+\.)+[\w]+\Z')

    def run(self, domain):
        if (domain
            and (not self.domain_re.match(domain)
                 or domain.endswith('.' + g.domain)
                 or domain.endswith('.' + g.media_domain)
                 or len(domain) > 300)):
            self.set_error(errors.BAD_CNAME)
        elif domain:
            try:
                return str(domain).lower()
            except UnicodeEncodeError:
                self.set_error(errors.BAD_CNAME)


# NOTE: make sure *never* to have res check these are present
# otherwise, the response could contain reference to these errors...!
class ValidIP(Validator):
    def run(self):
        if is_banned_IP(request.ip):
            self.set_error(errors.BANNED_IP)
        return request.ip

class VDate(Validator):
    """
    Date checker that accepts string inputs in %m/%d/%Y format.

    Optional parameters include 'past' and 'future' which specify how
    far (in days) into the past or future the date must be to be
    acceptable.

    NOTE: the 'future' param will have precidence during evaluation.

    Error conditions:
       * BAD_DATE on mal-formed date strings (strptime parse failure)
       * BAD_FUTURE_DATE and BAD_PAST_DATE on respective range errors.
    
    """
    def __init__(self, param, future=None, past = None,
                 admin_override = False,
                 reference_date = lambda : datetime.now(g.tz), 
                 business_days = False):
        self.future = future
        self.past   = past

        # are weekends to be exluded from the interval?
        self.business_days = business_days

        # function for generating "now"
        self.reference_date = reference_date

        # do we let admins override date range checking?
        self.override = admin_override
        Validator.__init__(self, param)

    def run(self, date):
        now = self.reference_date()
        override = c.user_is_sponsor and self.override
        try:
            date = datetime.strptime(date, "%m/%d/%Y")
            if not override:
                # can't put in __init__ since we need the date on the fly
                future = utils.make_offset_date(now, self.future,
                                          business_days = self.business_days)
                past = utils.make_offset_date(now, self.past, future = False,
                                          business_days = self.business_days)
                if self.future is not None and date.date() < future.date():
                    self.set_error(errors.BAD_FUTURE_DATE,
                               {"day": self.future})
                elif self.past is not None and date.date() > past.date():
                    self.set_error(errors.BAD_PAST_DATE,
                                   {"day": self.past})
            return date.replace(tzinfo=g.tz)
        except (ValueError, TypeError):
            self.set_error(errors.BAD_DATE)

class VDateRange(VDate):
    """
    Adds range validation to VDate.  In addition to satisfying
    future/past requirements in VDate, two date fields must be
    provided and they must be in order.

    Additional Error conditions:
      * BAD_DATE_RANGE if start_date is not less than end_date
    """
    def run(self, *a):
        try:
            start_date, end_date = [VDate.run(self, x) for x in a]
            if not start_date or not end_date or end_date < start_date:
                self.set_error(errors.BAD_DATE_RANGE)
            return (start_date, end_date)
        except ValueError:
            # insufficient number of arguments provided (expect 2)
            self.set_error(errors.BAD_DATE_RANGE)


class VDestination(Validator):
    def __init__(self, param = 'dest', default = "", **kw):
        self.default = default
        Validator.__init__(self, param, **kw)

    def run(self, dest):
        if not dest:
            dest = request.referer or self.default or "/"

        ld = dest.lower()
        if (ld.startswith("/") or
            ld.startswith("http://") or
            ld.startswith("https://")):

            u = UrlParser(dest)

            if u.is_reddit_url(c.site):
                return dest

        ip = getattr(request, "ip", "[unknown]")
        fp = getattr(request, "fullpath", "[unknown]")
        dm = c.domain or "[unknown]"
        cn = c.cname or "[unknown]"

        log_text("invalid redirect",
                 "%s attempted to redirect from %s to %s with domain %s and cname %s"
                      % (ip, fp, dest, dm, cn),
                 "info")

        return "/"

    def param_docs(self):
        return {
            self.param: _('destination url (must be same-domain)')
        }

class ValidAddress(Validator):
    def __init__(self, param, allowed_countries = ["United States"]):
        self.allowed_countries = allowed_countries
        Validator.__init__(self, param)

    def set_error(self, msg, field):
        Validator.set_error(self, errors.BAD_ADDRESS,
                            dict(message=msg), field = field)

    def run(self, firstName, lastName, company, address,
            city, state, zipCode, country, phoneNumber):
        if not firstName:
            self.set_error(_("please provide a first name"), "firstName")
        elif not lastName:
            self.set_error(_("please provide a last name"), "lastName")
        elif not address:
            self.set_error(_("please provide an address"), "address")
        elif not city: 
            self.set_error(_("please provide your city"), "city")
        elif not state: 
            self.set_error(_("please provide your state"), "state")
        elif not zipCode:
            self.set_error(_("please provide your zip or post code"), "zip")
        elif not country:
            self.set_error(_("please pick a country"), "country")
        else:
            country = pycountry.countries.get(alpha2=country)
            if country.name not in self.allowed_countries:
                self.set_error(_("Our ToS don't cover your country (yet). Sorry."), "country")

        # Make sure values don't exceed max length defined in the authorize.net
        # xml schema: https://api.authorize.net/xml/v1/schema/AnetApiSchema.xsd
        max_lengths = [
            (firstName, 50, 'firstName'), # (argument, max len, form field name)
            (lastName, 50, 'lastName'),
            (company, 50, 'company'),
            (address, 60, 'address'),
            (city, 40, 'city'),
            (state, 40, 'state'),
            (zipCode, 20, 'zip'),
            (phoneNumber, 255, 'phoneNumber')
        ]
        for (arg, max_length, form_field_name) in max_lengths:
            if arg and len(arg) > max_length:
                self.set_error(_("max length %d characters" % max_length), form_field_name)

        if not self.has_errors: 
            return Address(firstName = firstName,
                           lastName = lastName,
                           company = company or "",
                           address = address,
                           city = city, state = state,
                           zip = zipCode, country = country.name,
                           phoneNumber = phoneNumber or "")

class ValidCard(Validator):
    valid_ccn  = re.compile(r"\d{13,16}")
    valid_date = re.compile(r"\d\d\d\d-\d\d")
    valid_ccv  = re.compile(r"\d{3,4}")
    def set_error(self, msg, field):
        Validator.set_error(self, errors.BAD_CARD,
                            dict(message=msg), field = field)

    def run(self, cardNumber, expirationDate, cardCode):
        has_errors = False

        if not self.valid_ccn.match(cardNumber or ""):
            self.set_error(_("credit card numbers should be 13 to 16 digits"),
                           "cardNumber")
            has_errors = True
        
        if not self.valid_date.match(expirationDate or ""):
            self.set_error(_("dates should be YYYY-MM"), "expirationDate")
            has_errors = True
        else:
            now = datetime.now(g.tz)
            yyyy, mm = expirationDate.split("-")
            year = int(yyyy)
            month = int(mm)
            if month < 1 or month > 12:
                self.set_error(_("month must be in the range 01..12"), "expirationDate")
                has_errors = True
            elif datetime(year, month, 1) < datetime(now.year, now.month, 1):
                self.set_error(_("expiration date must be in the future"), "expirationDate")
                has_errors = True

        if not self.valid_ccv.match(cardCode or ""):
            self.set_error(_("card verification codes should be 3 or 4 digits"),
                           "cardCode")
            has_errors = True

        if not has_errors:
            return CreditCard(cardNumber = cardNumber,
                              expirationDate = expirationDate,
                              cardCode = cardCode)

class VTarget(Validator):
    target_re = re.compile("\A[\w_-]{3,20}\Z")
    def run(self, name):
        if name and self.target_re.match(name):
            return name

class VFlairAccount(VRequired):
    def __init__(self, item, *a, **kw):
        VRequired.__init__(self, item, errors.BAD_FLAIR_TARGET, *a, **kw)

    def _lookup(self, name, allow_deleted):
        try:
            return Account._by_name(name, allow_deleted=allow_deleted)
        except NotFound:
            return None

    def run(self, name):
        if not name:
            return self.error()
        return (
            self._lookup(name, False)
            or self._lookup(name, True)
            or self.error())

class VFlairLink(VRequired):
    def __init__(self, item, *a, **kw):
        VRequired.__init__(self, item, errors.BAD_FLAIR_TARGET, *a, **kw)

    def run(self, name):
        if not name:
            return self.error()
        try:
            return Link._by_fullname(name, data=True)
        except NotFound:
            return self.error()

class VFlairCss(VCssName):
    def __init__(self, param, max_css_classes=10, **kw):
        self.max_css_classes = max_css_classes
        VCssName.__init__(self, param, **kw)

    def run(self, css):
        if not css:
            return css

        names = css.split()
        if len(names) > self.max_css_classes:
            self.set_error(errors.TOO_MUCH_FLAIR_CSS)
            return ''

        for name in names:
            if not self.r_css_name.match(name):
                self.set_error(errors.BAD_CSS_NAME)
                return ''

        return css

class VFlairText(VLength):
    def __init__(self, param, max_length=64, **kw):
        VLength.__init__(self, param, max_length, **kw)

class VFlairTemplateByID(VRequired):
    def __init__(self, param, **kw):
        VRequired.__init__(self, param, None, **kw)

    def run(self, flair_template_id):
        try:
            return FlairTemplateBySubredditIndex.get_template(
                c.site._id, flair_template_id)
        except tdb_cassandra.NotFound:
            return None

class VOneTimePassword(Validator):
    max_skew = 2  # check two periods to allow for some clock skew
    ratelimit = 3  # maximum number of tries per period

    def __init__(self, param, required):
        self.required = required
        Validator.__init__(self, param)

    @classmethod
    def validate_otp(cls, secret, password):
        # is the password a valid format and has it been used?
        try:
            key = "otp-%s-%d" % (c.user._id36, int(password))
        except (TypeError, ValueError):
            valid_and_unused = False
        else:
            # leave this key around for one more time period than the maximum
            # number of time periods we'll check for valid passwords
            key_ttl = totp.PERIOD * (cls.max_skew + 1)
            valid_and_unused = g.cache.add(key, True, time=key_ttl)

        # check the password (allowing for some clock-skew as 2FA-users
        # frequently travel at relativistic velocities)
        if valid_and_unused:
            for skew in range(cls.max_skew):
                expected_otp = totp.make_totp(secret, skew=skew)
                if constant_time_compare(password, expected_otp):
                    return True

        return False

    def run(self, password):
        # does the user have 2FA configured?
        secret = c.user.otp_secret
        if not secret:
            if self.required:
                self.set_error(errors.NO_OTP_SECRET)
            return

        # do they have the otp cookie instead?
        if c.otp_cached:
            return

        # make sure they're not trying this too much
        if not g.disable_ratelimit:
            current_password = totp.make_totp(secret)
            key = "otp-tries-" + current_password
            g.cache.add(key, 0)
            recent_attempts = g.cache.incr(key)
            if recent_attempts > self.ratelimit:
                self.set_error(errors.RATELIMIT, dict(time="30 seconds"))
                return

        # check the password
        if self.validate_otp(secret, password):
            return

        # if we got this far, their password was wrong, invalid or already used
        self.set_error(errors.WRONG_PASSWORD)

class VOAuth2ClientID(VRequired):
    default_param = "client_id"
    default_param_doc = _("an app")
    def __init__(self, param=None, *a, **kw):
        VRequired.__init__(self, param, errors.OAUTH2_INVALID_CLIENT, *a, **kw)

    def run(self, client_id):
        client_id = VRequired.run(self, client_id)
        if client_id:
            client = OAuth2Client.get_token(client_id)
            if client and not getattr(client, 'deleted', False):
                return client
            else:
                self.error()

    def param_docs(self):
        return {self.default_param: self.default_param_doc}

class VOAuth2ClientDeveloper(VOAuth2ClientID):
    default_param_doc = _("an app developed by the user")

    def run(self, client_id):
        client = super(VOAuth2ClientDeveloper, self).run(client_id)
        if not client or not client.has_developer(c.user):
            return self.error()
        return client

class VOAuth2Scope(VRequired):
    default_param = "scope"
    def __init__(self, param=None, *a, **kw):
        VRequired.__init__(self, param, errors.OAUTH2_INVALID_SCOPE, *a, **kw)

    def run(self, scope):
        scope = VRequired.run(self, scope)
        if scope:
            parsed_scope = OAuth2Scope(scope)
            if parsed_scope.is_valid():
                return parsed_scope
            else:
                self.error()
