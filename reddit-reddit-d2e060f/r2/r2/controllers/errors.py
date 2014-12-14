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

from paste.httpexceptions import HTTPForbidden, HTTPError
from r2.lib.utils import Storage, tup
from pylons import request
from pylons.i18n import _
from copy import copy

error_list = dict((
        ('USER_REQUIRED', _("please login to do that")),
        ('HTTPS_REQUIRED', _("this page must be accessed using https")),
        ('VERIFIED_USER_REQUIRED', _("you need to set a valid email address to do that.")),
        ('NO_URL', _('a url is required')),
        ('BAD_URL', _('you should check that url')),
        ('BAD_CAPTCHA', _('care to try these again?')),
        ('BAD_USERNAME', _('invalid user name')),
        ('USERNAME_TAKEN', _('that username is already taken')),
        ('USERNAME_TAKEN_DEL', _('that username is taken by a deleted account')),
        ('USER_BLOCKED', _("you can't send to a user that you have blocked")),
        ('NO_THING_ID', _('id not specified')),
        ('TOO_MANY_THING_IDS', _('you provided too many ids')),
        ('NOT_AUTHOR', _("you can't do that")),
        ('NOT_USER', _("you are not logged in as that user")),
        ('DELETED_LINK', _('the link you are commenting on has been deleted')),
        ('DELETED_COMMENT', _('that comment has been deleted')),
        ('DELETED_THING', _('that element has been deleted')),
        ('BAD_PASSWORD', _('that password is unacceptable')),
        ('WRONG_PASSWORD', _('invalid password')),
        ('BAD_PASSWORD_MATCH', _('passwords do not match')),
        ('NO_NAME', _('please enter a name')),
        ('NO_EMAIL', _('please enter an email address')),
        ('NO_EMAIL_FOR_USER', _('no email address for that user')),
        ('NO_TO_ADDRESS', _('send it to whom?')),
        ('NO_SUBJECT', _('please enter a subject')),
        ('USER_DOESNT_EXIST', _("that user doesn't exist")),
        ('NO_USER', _('please enter a username')),
        ('INVALID_PREF', "that preference isn't valid"),
        ('BAD_NUMBER', _("that number isn't in the right range (%(range)s)")),
        ('BAD_STRING', _("you used a character here that we can't handle")),
        ('BAD_BID', _("your bid must be at least $%(min)d per day and no more than to $%(max)d in total.")),
        ('ALREADY_SUB', _("that link has already been submitted")),
        ('SUBREDDIT_EXISTS', _('that reddit already exists')),
        ('SUBREDDIT_NOEXIST', _('that reddit doesn\'t exist')),
        ('SUBREDDIT_NOTALLOWED', _("you aren't allowed to post there.")),
        ('SUBREDDIT_REQUIRED', _('you must specify a subreddit')),
        ('BAD_SR_NAME', _('that name isn\'t going to work')),
        ('RATELIMIT', _('you are doing that too much. try again in %(time)s.')),
        ('QUOTA_FILLED', _("You've submitted too many links recently. Please try again in an hour.")),
        ('SUBREDDIT_RATELIMIT', _("you are doing that too much. try again later.")),
        ('EXPIRED', _('your session has expired')),
        ('DRACONIAN', _('you must accept the terms first')),
        ('BANNED_IP', "IP banned"),
        ('BAD_CNAME', "that domain isn't going to work"),
        ('USED_CNAME', "that domain is already in use"),
        ('INVALID_OPTION', _('that option is not valid')),
        ('CHEATER', 'what do you think you\'re doing there?'),
        ('BAD_EMAILS', _('the following emails are invalid: %(emails)s')),
        ('NO_EMAILS', _('please enter at least one email address')),
        ('TOO_MANY_EMAILS', _('please only share to %(num)s emails at a time.')),
        ('OVERSOLD', _('that reddit has already been oversold on %(start)s to %(end)s. Please pick another reddit or date.')),
        ('BAD_DATE', _('please provide a date of the form mm/dd/yyyy')),
        ('BAD_DATE_RANGE', _('the dates need to be in order and not identical')),
        ('BAD_FUTURE_DATE', _('please enter a date at least %(day)s days in the future')),
        ('BAD_PAST_DATE', _('please enter a date at least %(day)s days in the past')),
        ('BAD_ADDRESS', _('address problem: %(message)s')),
        ('BAD_CARD', _('card problem: %(message)s')),
        ('TOO_LONG', _("this is too long (max: %(max_length)s)")),
        ('NO_TEXT', _('we need something here')),
        ('INVALID_CODE', _("we've never seen that code before")),
        ('CLAIMED_CODE', _("that code has already been claimed -- perhaps by you?")),
        ('NO_SELFS', _("that reddit doesn't allow text posts")),
        ('NO_LINKS', _("that reddit only allows text posts")),
        ('TOO_OLD', _("that's a piece of history now; it's too late to reply to it")),
        ('BAD_CSS_NAME', _('invalid css name')),
        ('BAD_REVISION', _('invalid revision ID')),
        ('TOO_MUCH_FLAIR_CSS', _('too many flair css classes')),
        ('BAD_FLAIR_TARGET', _('not a valid flair target')),
        ('OAUTH2_INVALID_CLIENT', _('invalid client id')),
        ('OAUTH2_INVALID_REDIRECT_URI', _('invalid redirect_uri parameter')),
        ('OAUTH2_INVALID_SCOPE', _('invalid scope requested')),
        ('OAUTH2_ACCESS_DENIED', _('access denied by the user')),
        ('CONFIRM', _("please confirm the form")),
        ('CONFLICT', _("conflict error while saving")),
        ('NO_API', _('cannot perform this action via the API')),
        ('DOMAIN_BANNED', _('%(domain)s is not allowed on reddit: %(reason)s')),
        ('NO_OTP_SECRET', _('you must enable two-factor authentication')),
        ('NOT_SUPPORTED', _('this feature is not supported')),
        ('BAD_IMAGE', _('image problem')),
        ('DEVELOPER_ALREADY_ADDED', _('already added')),
        ('TOO_MANY_DEVELOPERS', _('too many developers')),
        ('BAD_HASH', _("i don't believe you.")),
    ))
errors = Storage([(e, e) for e in error_list.keys()])

class Error(object):

    def __init__(self, name, i18n_message, msg_params, field=None, code=None):
        self.name = name
        self.i18n_message = i18n_message
        self.msg_params = msg_params
        # list of fields in the original form that caused the error
        self.fields = tup(field) if field else []
        self.code = code
        
    @property
    def message(self):
        return _(self.i18n_message) % self.msg_params

    def __iter__(self):
         #yield ('num', self.num)
        yield ('name', self.name)
        yield ('message', _(self.message))

    def __repr__(self):
        return '<Error: %s>' % self.name

class ErrorSet(object):
    def __init__(self):
        self.errors = {}

    def __contains__(self, pair):
        """Expectes an (error_name, field_name) tuple and checks to
        see if it's in the errors list."""
        return self.errors.has_key(pair)

    def __getitem__(self, name):
        return self.errors[name]

    def __repr__(self):
        return "<ErrorSet %s>" % list(self)

    def __iter__(self):
        for x in self.errors:
            yield x

    def __len__(self):
        return len(self.errors)
        
    def add(self, error_name, msg_params={}, field=None, code=None):
        msg = error_list.get(error_name)
        for field_name in tup(field):
            e = Error(error_name, msg, msg_params, field=field_name, code=code)
            self.errors[(error_name, field_name)] = e

    def remove(self, pair):
        """Expectes an (error_name, field_name) tuple and removes it
        from the errors list."""
        if self.errors.has_key(pair):
            del self.errors[pair]

class WikiError(HTTPError):
    def __init__(self, code, reason=None, **data):
        self.code = code
        data['reason'] = self.explanation = reason or 'UNKNOWN_ERROR'
        self.error_data = data
        HTTPError.__init__(self)

class ForbiddenError(HTTPForbidden):
    def __init__(self, error):
        HTTPForbidden.__init__(self)
        self.explanation = error_list[error]

class UserRequiredException(Exception): pass
class VerifiedUserRequiredException(Exception): pass
class GoldRequiredException(Exception): pass
