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

from pylons import c, request
from r2.lib.strings import Score
class Printable(object):
    show_spam = False
    show_reports = False
    is_special = False
    can_ban = False
    deleted = False
    rowstyle = ''
    collapsed = False
    author = None
    margin = 0
    is_focal = False
    childlisting = None
    cache_ignore = set(['c', 'author', 'score_fmt', 'child',
                        # displayed score is cachable, so remove score
                        # related fields.
                        'voting_score', 'display_score',
                        'render_score', 'score', '_score', 
                        'upvotes', '_ups',
                        'downvotes', '_downs',
                        'subreddit_slow', '_deleted', '_spam',
                        'cachable', 'make_permalink', 'permalink',
                        'timesince', 'votehash'
                        ])

    @classmethod
    def add_props(cls, user, wrapped):
        from r2.lib.wrapped import CachedVariable
        for item in wrapped:
            # insert replacement variable for timesince to allow for
            # caching of thing templates
            item.display = CachedVariable("display")
            item.timesince = CachedVariable("timesince")
            item.votehash = CachedVariable("votehash")
            item.childlisting = CachedVariable("childlisting")

            score_fmt = getattr(item, "score_fmt", Score.number_only)
            item.display_score = map(score_fmt, item.voting_score)

            if item.cachable:
                item.render_score  = item.display_score
                item.display_score = map(CachedVariable,
                                         ["scoredislikes", "scoreunvoted",
                                          "scorelikes"])

    @property
    def permalink(self, *a, **kw):
        raise NotImplementedError

    def keep_item(self, wrapped):
        return True

    @staticmethod
    def wrapped_cache_key(wrapped, style):
        s = [wrapped._fullname, wrapped._spam, wrapped.reported]

        if style == 'htmllite':
            s.extend([c.bgcolor, c.bordercolor, 
                      request.get.has_key('style'),
                      request.get.get("expanded"), 
                      getattr(wrapped, 'embed_voting_style', None)])
        return s
