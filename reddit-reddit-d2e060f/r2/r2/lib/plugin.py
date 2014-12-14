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

import sys
import os.path
import pkg_resources
from collections import OrderedDict

from pylons import config


class Plugin(object):
    js = {}
    config = {}
    live_config = {}
    needs_static_build = False

    def __init__(self, entry_point):
        self.entry_point = entry_point

    @property
    def name(self):
        return self.entry_point.name

    @property
    def path(self):
        module = sys.modules[type(self).__module__]
        return os.path.dirname(module.__file__)

    @property
    def template_dir(self):
        """Add module/templates/ as a template directory."""
        return os.path.join(self.path, 'templates')

    @property
    def static_dir(self):
        return os.path.join(self.path, 'public')

    def on_load(self):
        pass

    def add_js(self, module_registry=None):
        if not module_registry:
            from r2.lib import js
            module_registry = js.module

        for name, module in self.js.iteritems():
            if name not in module_registry:
                module_registry[name] = module
            else:
                module_registry[name].extend(module)

    def declare_queues(self, queues):
        pass

    def add_routes(self, mc):
        pass

    def load_controllers(self):
        pass


class PluginLoader(object):
    def __init__(self, plugin_names=None):
        if plugin_names is None:
            entry_points = self.available_plugins()
        else:
            entry_points = []
            for name in plugin_names:
                try:
                    entry_point = self.available_plugins(name).next()
                except StopIteration:
                    print >> sys.stderr, ("Unable to locate plugin "
                                          "%s. Skipping." % name)
                    continue
                else:
                    entry_points.append(entry_point)

        self.plugins = OrderedDict()
        for entry_point in entry_points:
            plugin_cls = entry_point.load()
            self.plugins[entry_point.name] = plugin_cls(entry_point)

    def __len__(self):
        return len(self.plugins)

    def __iter__(self):
        return self.plugins.itervalues()

    def __reversed__(self):
        return reversed(self.plugins.values())

    def __getitem__(self, key):
        return self.plugins[key]

    @staticmethod
    def available_plugins(name=None):
        return pkg_resources.iter_entry_points('r2.plugin', name)

    def declare_queues(self, queues):
        for plugin in self:
            plugin.declare_queues(queues)

    def load_plugins(self):
        g = config['pylons.g']
        for plugin in self:
            # Record plugin version
            entry = plugin.entry_point
            git_dir = os.path.join(entry.dist.location, '.git')
            g.record_repo_version(entry.name, git_dir)

            # Load plugin
            g.config.add_spec(plugin.config)
            config['pylons.paths']['templates'].insert(0, plugin.template_dir)
            plugin.add_js()
            plugin.on_load()

    def load_controllers(self):
        for plugin in self:
            plugin.load_controllers()
