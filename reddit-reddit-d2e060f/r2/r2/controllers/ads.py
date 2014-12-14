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

from pylons import request, g
from reddit_base import RedditController
from r2.lib.pages import AdminPage, AdminAds, AdminAdAssign, AdminAdSRs
from validator import *

class AdsController(RedditController):

    @validate(VSponsorAdmin())
    def GET_index(self):
        res = AdminPage(content = AdminAds(),
                        show_sidebar = False,
                        title = 'ads').render()
        return res

    @validate(VSponsorAdmin(),
              ad = VAdByCodename('adcn'))
    def GET_assign(self, ad):
        if ad is None:
            abort(404, 'page not found')

        res = AdminPage(content = AdminAdAssign(ad),
                        show_sidebar = False,
                        title='assign an ad to a community').render()
        return res

    @validate(VSponsorAdmin(),
              ad = VAdByCodename('adcn'))
    def GET_srs(self, ad):
        if ad is None:
            abort(404, 'page not found')

        res = AdminPage(content = AdminAdSRs(ad),
                        show_sidebar = False,
                        title='ad srs').render()
        return res
