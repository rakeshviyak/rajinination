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

from pylons         import c, g
from r2.lib.wrapped import Templated
from pages   import Reddit
from r2.lib.menus   import NamedButton, NavButton, menu, NavMenu

class AdminSidebar(Templated):
    def __init__(self, user):
        Templated.__init__(self)
        self.user = user


class Details(Templated):
    def __init__(self, link, *a, **kw):
        Templated.__init__(self, *a, **kw)
        self.link = link


class AdminPage(Reddit):
    create_reddit_box  = False
    submit_box         = False
    extension_handling = False
    show_sidebar = False

    def __init__(self, nav_menus = None, *a, **kw):
        #add admin options to the nav_menus
        if c.user_is_admin:
            buttons = []

            if g.translator:
                buttons.append(NavButton(menu.i18n, "i18n"))

            buttons.append(NavButton(menu.awards, "ads"))
            buttons.append(NavButton(menu.awards, "awards"))
            buttons.append(NavButton(menu.errors, "error log"))
            buttons.append(NavButton(menu.usage,  "usage stats"))

            admin_menu = NavMenu(buttons, title='show', base_path = '/admin',
                                 type="lightdrop")
            if nav_menus:
                nav_menus.insert(0, admin_menu)
            else:
                nav_menus = [admin_menu]

        Reddit.__init__(self, nav_menus = nav_menus, *a, **kw)

class AdminProfileMenu(NavMenu):
    def __init__(self, path):
        NavMenu.__init__(self, [], base_path = path,
                         title = 'admin', type="tabdrop")

try:
    from r2admin.lib.pages import *
except ImportError:
    pass
