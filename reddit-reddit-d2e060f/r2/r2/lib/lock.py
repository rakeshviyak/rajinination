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

from __future__ import with_statement
from time import sleep
from datetime import datetime
from threading import local
import os
import socket

from r2.lib.utils import simple_traceback

# thread-local storage for detection of recursive locks
locks = local()

reddit_host = socket.gethostname()
reddit_pid  = os.getpid()

class TimeoutExpired(Exception): pass

class MemcacheLock(object):
    """A simple global lock based on the memcache 'add' command. We
    attempt to grab a lock by 'adding' the lock name. If the response
    is True, we have the lock. If it's False, someone else has it."""

    def __init__(self, stats, group, key, cache,
                 time=30, timeout=30, verbose=True):
        # get a thread-local set of locks that we own
        self.locks = locks.locks = getattr(locks, 'locks', set())

        self.stats = stats
        self.group = group
        self.key = key
        self.cache = cache
        self.time = time
        self.timeout = timeout
        self.have_lock = False
        self.verbose = verbose

    def __enter__(self):
        start = datetime.now()

        my_info = (reddit_host, reddit_pid, simple_traceback())

        #if this thread already has this lock, move on
        if self.key in self.locks:
            return

        timer = self.stats.get_timer("lock_wait")
        timer.start()

        #try and fetch the lock, looping until it's available
        while not self.cache.add(self.key, my_info, time = self.time):
            if (datetime.now() - start).seconds > self.timeout:
                if self.verbose:
                    info = self.cache.get(self.key)
                    if info:
                        info = "%s %s\n%s" % info
                    else:
                        info = "(nonexistent)"
                    msg = ("\nSome jerk is hogging %s:\n%s" %
                                         (self.key, info))
                    msg += "^^^ that was the stack trace of the lock hog, not me."
                else:
                    msg = "Timed out waiting for %s" % self.key
                raise TimeoutExpired(msg)

            sleep(.01)

        timer.stop(subname=self.group)

        #tell this thread we have this lock so we can avoid deadlocks
        #of requests for the same lock in the same thread
        self.locks.add(self.key)
        self.have_lock = True

    def __exit__(self, type, value, tb):
        #only release the lock if we gained it in the first place
        if self.have_lock:
            self.cache.delete(self.key)
            self.locks.remove(self.key)

def make_lock_factory(cache, stats):
    def factory(group, key, **kw):
        return MemcacheLock(stats, group, key, cache, **kw)
    return factory
