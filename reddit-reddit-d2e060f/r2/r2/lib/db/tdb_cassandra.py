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

import inspect
import pytz
from datetime import datetime
from socket import gethostbyaddr

from pylons import g

from pycassa import ColumnFamily
from pycassa.pool import MaximumRetryException
from pycassa.cassandra.ttypes import ConsistencyLevel, NotFoundException
from pycassa.system_manager import (SystemManager, UTF8_TYPE,
                                    COUNTER_COLUMN_TYPE, TIME_UUID_TYPE,
                                    ASCII_TYPE)
from pycassa.types import DateType
from r2.lib.utils import tup, Storage
from r2.lib import cache
from uuid import uuid1, UUID
from itertools import chain
import cPickle as pickle
from pycassa.util import OrderedDict
import base64

connection_pools = g.cassandra_pools
default_connection_pool = g.cassandra_default_pool

keyspace = 'reddit'
thing_cache = g.thing_cache
disallow_db_writes = g.disallow_db_writes
tz = g.tz
log = g.log
read_consistency_level = g.cassandra_rcl
write_consistency_level = g.cassandra_wcl
debug = g.debug
make_lock = g.make_lock
db_create_tables = g.db_create_tables

import json

thing_types = {}

TRANSIENT_EXCEPTIONS = (MaximumRetryException,)

# The available consistency levels
CL = Storage(ANY    = ConsistencyLevel.ANY,
             ONE    = ConsistencyLevel.ONE,
             QUORUM = ConsistencyLevel.QUORUM,
             ALL    = ConsistencyLevel.ALL)

# the greatest number of columns that we're willing to accept over the
# wire for a given row (this should be increased if we start working
# with classes with lots of columns, like Account which has lots of
# karma_ rows, or we should not do that)
max_column_count = 10000

# the pycassa date serializer, for use when we can't set the right metadata
# to get pycassa to serialize dates for us
date_serializer = DateType()

class CassandraException(Exception):
    """Base class for Exceptions in tdb_cassandra"""
    pass

class InvariantException(CassandraException):
    """Exceptions that can only be caused by bugs in tdb_cassandra"""
    pass

class ConfigurationException(CassandraException):
    """Exceptions that are caused by incorrect configuration on the
       Cassandra server"""
    pass

class TdbException(CassandraException):
    """Exceptions caused by bugs in our callers or subclasses"""
    pass

class NotFound(CassandraException, NotFoundException):
    """Someone asked us for an ID that isn't stored in the DB at
       all. This is probably an end-user's fault."""
    pass

def will_write(fn):
    """Decorator to indicate that a given function intends to write
       out to Cassandra"""
    def _fn(*a, **kw):
        if disallow_db_writes:
            raise CassandraException("Not so fast! DB writes have been disabled")
        return fn(*a, **kw)
    return _fn

def get_manager(seeds):
    # n.b. does not retry against multiple servers
    server = seeds[0]
    return SystemManager(server)

class ThingMeta(type):
    def __init__(cls, name, bases, dct):
        type.__init__(cls, name, bases, dct)

        if cls._use_db:
            if cls._type_prefix is None:
                # default to the class name
                cls._type_prefix = name

            if '_' in cls._type_prefix:
                raise TdbException("Cannot have _ in type prefix %r (for %r)"
                                   % (cls._type_prefix, name))

            if cls._type_prefix in thing_types:
                raise InvariantException("Redefining type %r?" % (cls._type_prefix))

            # if we weren't given a specific _cf_name, we can use the
            # classes's name
            cf_name = cls._cf_name or name

            thing_types[cls._type_prefix] = cls

            if not getattr(cls, "_read_consistency_level", None):
                cls._read_consistency_level = read_consistency_level
            if not getattr(cls, "_write_consistency_level", None):
                cls._write_consistency_level = write_consistency_level

            pool_name = getattr(cls, "_connection_pool", default_connection_pool)
            connection_pool = connection_pools[pool_name]
            cassandra_seeds = connection_pool.server_list

            try:
                cls._cf = ColumnFamily(connection_pool,
                                       cf_name,
                                       read_consistency_level = cls._read_consistency_level,
                                       write_consistency_level = cls._write_consistency_level)
            except NotFoundException:
                if not db_create_tables:
                    raise

                manager = get_manager(cassandra_seeds)

                # allow subclasses to add creation args or override base class ones
                extra_creation_arguments = {}
                for c in reversed(inspect.getmro(cls)):
                    creation_args = getattr(c, "_extra_schema_creation_args", {})
                    extra_creation_arguments.update(creation_args)

                log.warning("Creating Cassandra Column Family %s" % (cf_name,))
                with make_lock("cassandra_schema", 'cassandra_schema'):
                    manager.create_column_family(keyspace, cf_name,
                                                 comparator_type = cls._compare_with,
                                                 super=getattr(cls, '_super', False),
                                                 **extra_creation_arguments
                                                 )
                log.warning("Created Cassandra Column Family %s" % (cf_name,))

                # try again to look it up
                cls._cf = ColumnFamily(connection_pool,
                                       cf_name,
                                       read_consistency_level = cls._read_consistency_level,
                                       write_consistency_level = cls._write_consistency_level)

        cls._kind = name

    def __repr__(cls):
        return '<thing: %s>' % cls.__name__

class Counter(object):
    __metaclass__ = ThingMeta

    _use_db = False
    _connection_pool = 'main'
    _extra_schema_creation_args = {
        'default_validation_class': COUNTER_COLUMN_TYPE,
        'replicate_on_write': True
    }

    _type_prefix = None
    _cf_name = None
    _compare_with = UTF8_TYPE

    @classmethod
    def _byID(cls, key):
        return cls._cf.get(key)

    @classmethod
    @will_write
    def _incr(cls, key, column, delta=1, super_column=None):
        cls._cf.add(key, column, delta, super_column)

    @classmethod
    @will_write
    def _incr_multi(cls, key, data):
        with cls._cf.batch() as b:
            b.insert(key, data)


class ThingBase(object):
    # base class for Thing and Relation

    __metaclass__ = ThingMeta

    _cf_name = None # the name of the ColumnFamily; defaults to the
                    # name of the class

    # subclasses must replace these

    _type_prefix = None # this must be present for classes with _use_db==True

    _use_db = False

    # the Cassandra column-comparator (internally orders column
    # names). In real life you can't change this without some changes
    # to tdb_cassandra to support other attr types
    _compare_with = UTF8_TYPE

    _value_type = None # if set, overrides all of the _props types
                       # below. Used for Views. One of 'int', 'float',
                       # 'bool', 'pickle', 'date', 'bytes', 'str'

    _int_props = ()
    _float_props = () # note that we can lose resolution on these
    _bool_props = ()
    _pickle_props = ()
    _date_props = () # note that we can lose resolution on these
    _bytes_props = ()
    _str_props = () # at present we never actually read out of here
                    # since it's the default if none of the previous
                    # matches

    # the value that we assume a property to have if it is not found
    # in the DB. Note that we don't do type-checking here, so if you
    # want a default to be a boolean and want it to be storable you'll
    # also have to set it in _bool_props
    _defaults = {}

    # The default TTL in seconds to add to all columns. Note: if an
    # entire object is expected to have a TTL, it should be considered
    # immutable! (You don't want to write out an object with an author
    # and date, then go update author or add a new column, then have
    # the original columns expire. Then when you go to look it up, the
    # inherent properties author and/or date will be gone and only the
    # updated columns will be present.) This is an expected convention
    # and is not enforced.
    _ttl = None
    _warn_on_partial_ttl = True

    # A per-class dictionary of default TTLs that new columns of this
    # class should have
    _default_ttls = {}

    # A per-instance property defining the TTL of individual columns
    # (that must also appear in self._dirties)
    _column_ttls = {}

    # a timestamp property that will automatically be added to newly
    # created Things (disable by setting to None)
    _timestamp_prop = None

    # a per-instance property indicating that this object was
    # partially loaded: i.e. only some properties were requested from
    # the DB
    _partial = None

    # a per-instance property that specifies that the columns backing
    # these attributes are to be removed on _commit()
    _deletes = set()

    # thrift will materialize the entire result set for a slice range
    # in memory, meaning that we need to limit the maximum number of columns
    # we receive in a single get to avoid hurting the server. if this
    # value is true, we will make sure to do extra gets to retrieve all of
    # the columns in a row when there are more than the per-call maximum.
    _fetch_all_columns = False

    def __init__(self, _id = None, _committed = False, _partial = None, **kw):
        # things that have changed
        self._dirties = kw.copy()

        # what the original properties were when we went to Cassandra to
        # get them
        self._orig = {}

        self._defaults = self._defaults.copy()

        # whether this item has ever been created
        self._committed = _committed

        self._partial = None if _partial is None else frozenset(_partial)

        self._deletes = set()
        self._column_ttls = {}

        # our row key
        self._id = _id

        if not self._use_db:
            raise TdbException("Cannot make instances of %r" % (self.__class__,))

    @classmethod
    def _byID(cls, ids, return_dict=True, properties=None):
        ids, is_single = tup(ids, True)

        if properties is not None:
            asked_properties = frozenset(properties)
            willask_properties = set(properties)

        if not len(ids):
            if is_single:
                raise InvariantException("whastis?")
            return {}

        # all keys must be strings or directly convertable to strings
        assert all(isinstance(_id, basestring) or str(_id) for _id in ids)

        def reject_bad_partials(cached, still_need):
            # tell sgm that the match it found in the cache isn't good
            # enough if it's a partial that doesn't include our
            # properties. we still need to look those items up to get
            # the properties that we're after
            stillfind = set()

            for k, v in cached.iteritems():
                if properties is None:
                    if v._partial is not None:
                        # there's a partial in the cache but we're not
                        # looking for partials
                        stillfind.add(k)
                elif v._partial is not None and not asked_properties.issubset(v._partial):
                    # we asked for a partial, and this is a partial,
                    # but it doesn't have all of the properties that
                    # we need
                    stillfind.add(k)

                    # other callers in our request are now expecting
                    # to find the properties that were on that
                    # partial, so we'll have to preserve them
                    for prop in v._partial:
                        willask_properties.add(prop)

            for k in stillfind:
                del cached[k]
                still_need.add(k)

        def lookup(l_ids):
            if properties is None:
                rows = cls._cf.multiget(l_ids, column_count=max_column_count)

                # if we got max_column_count columns back for a row, it was
                # probably clipped. in this case, we should fetch the remaining
                # columns for that row and add them to the result.
                if cls._fetch_all_columns:
                    for key, row in rows.iteritems():
                        if len(row) == max_column_count:
                            last_column_seen = next(reversed(row))
                            cols = cls._cf.xget(key,
                                                column_start=last_column_seen,
                                                buffer_size=max_column_count)
                            row.update(cols)
            else:
                rows = cls._cf.multiget(l_ids, columns = willask_properties)

            l_ret = {}
            for t_id, row in rows.iteritems():
                t = cls._from_serialized_columns(t_id, row)
                if properties is not None:
                    # make sure that the item is marked as a _partial
                    t._partial = willask_properties
                l_ret[t._id] = t

            return l_ret

        ret = cache.sgm(thing_cache, ids, lookup, prefix=cls._cache_prefix(),
                        found_fn=reject_bad_partials)

        if is_single and not ret:
            raise NotFound("<%s %r>" % (cls.__name__,
                                        ids[0]))
        elif is_single:
            assert len(ret) == 1
            return ret.values()[0]
        elif return_dict:
            return ret
        else:
            return filter(None, (ret.get(i) for i in ids))

    @property
    def _fullname(self):
        if self._type_prefix is None:
            raise TdbException("%r has no _type_prefix, so fullnames cannot be generated"
                               % self.__class__)

        return '%s_%s' % (self._type_prefix, self._id)

    @classmethod
    def _by_fullname(cls, fnames, return_dict=True):
        ids, is_single = tup(fnames, True)

        by_cls = {}
        for i in ids:
            typ, underscore, _id = i.partition('_')
            assert underscore == '_'

            by_cls.setdefault(thing_types[typ], []).append(_id)

        items = []
        for typ, ids in by_cls.iteritems():
            items.extend(typ._byID(ids).values())

        if is_single:
            return items[0]
        elif return_dict:
            return dict((x._fullname, x) for x in items)
        else:
            d = dict((x._fullname, x) for x in items)
            return [d[fullname] for fullname in fnames]

    @classmethod
    def _cache_prefix(cls):
        return 'tdbcassandra_' + cls._type_prefix + '_'

    def _cache_key(self):
        if not self._id:
            raise TdbException('no cache key for uncommitted %r' % (self,))

        return self._cache_key_id(self._id)

    @classmethod
    def _cache_key_id(cls, t_id):
        return cls._cache_prefix() + t_id

    @classmethod
    def _wcl(cls, wcl, default = None):
        if wcl is not None:
            return wcl
        elif default is not None:
            return default
        return cls._write_consistency_level

    def _rcl(cls, rcl, default = None):
        if rcl is not None:
            return rcl
        elif default is not None:
            return default
        return cls._read_consistency_level

    @classmethod
    def _get_column_validator(cls, colname):
        return cls._cf.column_validators.get(colname,
                                             cls._cf.default_validation_class)

    @classmethod
    def _deserialize_column(cls, attr, val):
        if attr in cls._int_props or (cls._value_type and cls._value_type == 'int'):
            try:
                return int(val)
            except ValueError:
                return long(val)
        elif attr in cls._float_props or (cls._value_type and cls._value_type == 'float'):
            return float(val)
        elif attr in cls._bool_props or (cls._value_type and cls._value_type == 'bool'):
            # note that only the string "1" is considered true!
            return val == '1'
        elif attr in cls._pickle_props or (cls._value_type and cls._value_type == 'pickle'):
            return pickle.loads(val)
        elif attr in cls._date_props or attr == cls._timestamp_prop or (cls._value_type and cls._value_type == 'date'):
            return cls._deserialize_date(val)
        elif attr in cls._bytes_props or (cls._value_type and cls._value_type == 'bytes'):
            return val

        # otherwise we'll assume that it's a utf-8 string
        return val if isinstance(val, unicode) else val.decode('utf-8')

    @classmethod
    def _serialize_column(cls, attr, val):
        if (attr in chain(cls._int_props, cls._float_props) or
            (cls._value_type and cls._value_type in ('float', 'int'))):
            return str(val)
        elif attr in cls._bool_props or (cls._value_type and cls._value_type == 'bool'):
            # n.b. we "truncate" this to a boolean, so truthy but
            # non-boolean values are discarded
            return '1' if val else '0'
        elif attr in cls._pickle_props or (cls._value_type and cls._value_type == 'pickle'):
            return pickle.dumps(val)
        elif (attr in cls._date_props or attr == cls._timestamp_prop or
              (cls._value_type and cls._value_type == 'date')):
            # the _timestamp_prop is handled in _commit(), not here
            if cls._get_column_validator(attr) == 'DateType':
                # pycassa will take it from here
                return val
            else:
                return cls._serialize_date(val)
        elif attr in cls._bytes_props or (cls._value_type and cls._value_type == 'bytes'):
            return val

        return unicode(val).encode('utf-8')

    @classmethod
    def _serialize_date(cls, date):
        return date_serializer.pack(date)

    @classmethod
    def _deserialize_date(cls, val):
        if isinstance(val, datetime):
            date = val
        elif len(val) == 8: # cassandra uses 8-byte integer format for this
            date = date_serializer.unpack(val)
        else: # it's probably the old-style stringified seconds since epoch
            as_float = float(val)
            date = datetime.utcfromtimestamp(as_float)

        return date.replace(tzinfo=pytz.utc)

    @classmethod
    def _from_serialized_columns(cls, t_id, columns):
        d_columns = dict((attr, cls._deserialize_column(attr, val))
                         for (attr, val)
                         in columns.iteritems())
        return cls._from_columns(t_id, d_columns)

    @classmethod
    def _from_columns(cls, t_id, columns):
        """Given a dictionary of freshly deserialized columns
           construct an instance of cls"""
        # if modifying this, check Relation._from_columns and see if
        # you should change it as well
        t = cls()
        t._orig = columns
        t._id = t_id
        t._committed = True
        return t

    @property
    def _dirty(self):
        return len(self._dirties) or len(self._deletes) or not self._committed

    @will_write
    def _commit(self, write_consistency_level = None):
        if not self._dirty:
            return

        if self._id is None:
            raise TdbException("Can't commit %r without an ID" % (self,))

        if self._committed and self._ttl and self._warn_on_partial_ttl:
            log.warning("Using a full-TTL object %r in a mutable fashion"
                        % (self,))

        if not self._committed:
            # if this has never been committed we should also consider
            # the _orig columns as dirty (but "less dirty" than the
            # _dirties)
            upd = self._orig.copy()
            self._orig.clear()
            upd.update(self._dirties)
            self._dirties = upd

        # Cassandra values are untyped byte arrays, so we need to
        # serialize everything while filtering out anything that's
        # been dirtied but doesn't actually differ from what's already
        # in the DB
        updates = dict((attr, self._serialize_column(attr, val))
                       for (attr, val)
                       in self._dirties.iteritems()
                       if (attr not in self._orig or
                           val != self._orig[attr]))

        # n.b. deleted columns are applied *after* the updates. our
        # __setattr__/__delitem__ tries to make sure that this always
        # works

        if not self._committed and self._timestamp_prop and self._timestamp_prop not in updates:
            # auto-create timestamps on classes that request them

            # this serialize/deserialize is a bit funny: the process
            # of storing and retrieving causes us to lose some
            # resolution because of the floating-point representation,
            # so this is just to make sure that we have the same value
            # that the DB does after writing it out. Note that this is
            # the only property munged this way: other timestamp and
            # floating point properties may lose resolution
            s_now = self._serialize_date(datetime.now(tz))
            now = self._deserialize_date(s_now)

            timestamp_is_typed = self._get_column_validator(self._timestamp_prop) == "DateType"
            updates[self._timestamp_prop] = now if timestamp_is_typed else s_now
            self._dirties[self._timestamp_prop] = now

        if not updates and not self._deletes:
            self._dirties.clear()
            return

        # actually write out the changes to the CF
        wcl = self._wcl(write_consistency_level)
        with self._cf.batch(write_consistency_level = wcl) as b:
            if updates:
                for k, v in updates.iteritems():
                    b.insert(self._id,
                             {k: v},
                             ttl=self._column_ttls.get(k, self._ttl))
            if self._deletes:
                b.remove(self._id, self._deletes)

        self._orig.update(self._dirties)
        self._column_ttls.clear()
        self._dirties.clear()
        for k in self._deletes:
            try:
                del self._orig[k]
            except KeyError:
                pass
        self._deletes.clear()

        if not self._committed:
            self._on_create()
        else:
            self._on_commit()

        self._committed = True

        thing_cache.set(self._cache_key(), self)

    def _revert(self):
        if not self._committed:
            raise TdbException("Revert to what?")

        self._dirties.clear()
        self._deletes.clear()
        self._column_ttls.clear()

    def __getattr__(self, attr):
        if attr.startswith('_'):
            try:
                return self.__dict__[attr]
            except KeyError:
                raise AttributeError, attr

        if attr in self._deletes:
            raise AttributeError("%r has no %r because you deleted it", (self, attr))
        elif attr in self._dirties:
            return self._dirties[attr]
        elif attr in self._orig:
            return self._orig[attr]
        elif attr in self._defaults:
            return self._defaults[attr]
        elif self._partial is not None and attr not in self._partial:
            raise AttributeError("%r has no %r but you didn't request it" % (self, attr))
        else:
            raise AttributeError('%r has no %r' % (self, attr))

    def __setattr__(self, attr, val):
        if attr == '_id' and self._committed:
            raise ValueError('cannot change _id on a committed %r' % (self.__class__))

        if attr.startswith('_'):
            return object.__setattr__(self, attr, val)

        try:
            self._deletes.remove(attr)
        except KeyError:
            pass
        self._dirties[attr] = val
        if attr in self._default_ttls:
            self._column_ttls[attr] = self._default_ttls[attr]

    def __eq__(self, other):
        if self.__class__ != other.__class__:
            return False

        if self._partial or other._partial and self._partial != other._partial:
            raise ValueError("Can't compare incompatible partials")

        return self._id == other._id and self._t == other._t

    def __ne__(self, other):
        return not (self == other)

    @property
    def _t(self):
        """Emulate the _t property from tdb_sql: a dictionary of all
           values that are or will be stored in the database, (not
           including _defaults or unrequested properties on
           partials)"""
        ret = self._orig.copy()
        ret.update(self._dirties)
        for k in self._deletes:
            try:
                del ret[k]
            except KeyError:
                pass
        return ret

    # allow the dictionary mutation syntax; it makes working some some
    # keys a bit easier. Go through our regular
    # __getattr__/__setattr__ functions where all of the appropriate
    # work is done
    def __getitem__(self, key):
        return self.__getattr__(key)

    def __setitem__(self, key, value):
        return self.__setattr__(key, value)

    def __delitem__(self, key):
        try:
            del self._dirties[key]
        except KeyError:
            pass
        try:
            del self._column_ttls[key]
        except KeyError:
            pass
        self._deletes.add(key)

    def _get(self, key, default = None):
        try:
            return self.__getattr__(key)
        except AttributeError:
            if self._partial is not None and key not in self._partial:
                raise AttributeError("_get on unrequested key from partial")
            return default

    def _set_ttl(self, key, ttl):
        assert key in self._dirties
        assert isinstance(ttl, (long, int))
        self._column_ttls[key] = ttl

    def _on_create(self):
        """A hook executed on creation, good for creation of static
           Views. Subclasses should call their parents' hook(s) as
           well"""
        pass

    def _on_commit(self):
        """Executed on _commit other than creation."""
        pass

    @classmethod
    def _all(cls):
        # returns a query object yielding every single item in a
        # column family. it probably shouldn't be used except in
        # debugging
        return Query(cls, limit=None)

    def __repr__(self):
        # it's safe for subclasses to override this to e.g. put a Link
        # title or Account name in the repr(), but they must be
        # careful to check hasattr for the properties that they read
        # out, as __getattr__ itself may call __repr__ in constructing
        # its error messages
        id_str = self._id
        comm_str = '' if self._committed else ' (uncommitted)'
        part_str = '' if self._partial is None else ' (partial)'
        return "<%s %r%s%s>" % (self.__class__.__name__,
                              id_str,
                              comm_str, part_str)

    if debug:
        # we only want this with g.debug because overriding __del__
        # can play hell with memory leaks
        def __del__(self):
                if not self._committed:
                    # normally we'd log this with g.log or something,
                    # but we can't guarantee that the thread
                    # destructing us has access to g
                    print "Warning: discarding uncomitted %r; this is usually a bug" % (self,)
                elif self._dirty:
                    print ("Warning: discarding dirty %r; this is usually a bug (_dirties=%r, _deletes=%r)"
                           % (self,self._dirties,self._deletes))

class Thing(ThingBase):
    _timestamp_prop = 'date'

class UuidThing(ThingBase):
    _timestamp_prop = 'date'
    _extra_schema_creation_args = {
        'key_validation_class': TIME_UUID_TYPE
    }

    def __init__(self, **kw):
        ThingBase.__init__(self, _id=uuid1(), **kw)

    @classmethod
    def _byID(cls, ids, **kw):
        ids, is_single = tup(ids, ret_is_single=True)

        #Convert string ids to UUIDs before retrieving
        uuids = [UUID(id) if not isinstance(id, UUID) else id for id in ids]

        if len(uuids) == 0:
            return {}
        elif is_single:
            assert len(uuids) == 1
            uuids = uuids[0]

        return super(UuidThing, cls)._byID(uuids, **kw)

    @classmethod
    def _cache_key_id(cls, t_id):
        return cls._cache_prefix() + str(t_id)

class Relation(ThingBase):
    _timestamp_prop = 'date'

    def __init__(self, thing1_id, thing2_id, **kw):
        # NB! When storing relations between postgres-backed Thing
        # objects, these IDs are actually ID36s
        ThingBase.__init__(self,
                           _id = self._rowkey(thing1_id, thing2_id),
                           **kw)
        self._orig['thing1_id'] = thing1_id
        self._orig['thing2_id'] = thing2_id

    @will_write
    def _destroy(self, write_consistency_level = None):
        # only implemented on relations right now, but at present
        # there's no technical reason for this
        self._cf.remove(self._id,
                        write_consistency_level = self._wcl(write_consistency_level))
        self._on_destroy()
        thing_cache.delete(self._cache_key())

    def _on_destroy(self):
        """Called *after* the destruction of the Thing on the
           destroyed Thing's mortal shell"""
        # only implemented on relations right now, but at present
        # there's no technical reason for this
        pass

    @classmethod
    def _fast_query(cls, thing1s, thing2s, properties = None, **kw):
        """Find all of the relations of this class between all of the
           members of thing1_ids and thing2_ids"""
        thing1s, thing1s_is_single = tup(thing1s, True)
        thing2s, thing2s_is_single = tup(thing2s, True)

        if not thing1s or not thing2s:
            return {}

        # grab the last time each thing1 modified this relation class so we can
        # know which relations not to even bother looking up
        if thing1s:
            from r2.models.last_modified import LastModified
            fullnames = [cls._thing1_cls._fullname_from_id36(thing1._id36)
                         for thing1 in thing1s]
            timestamps = LastModified.get_multi(fullnames,
                                                cls._cf.column_family)

        # build up a list of ids to look up, throwing out the ones that the
        # timestamp fetched above indicates are pointless
        ids = set()
        thing1_ids, thing2_ids = {}, {}
        for thing1 in thing1s:
            last_modification = timestamps.get(thing1._fullname)

            if not last_modification:
                continue

            for thing2 in thing2s:
                key = cls._rowkey(thing1._id36, thing2._id36)

                if key in ids:
                    continue

                if thing2._date > last_modification:
                    continue

                ids.add(key)
                thing2_ids[thing2._id36] = thing2
            thing1_ids[thing1._id36] = thing1

        # all relations must load these properties, even if unrequested
        if properties is not None:
            properties = set(properties)

            properties.add('thing1_id')
            properties.add('thing2_id')

        rels = {}
        if ids:
            rels = cls._byID(ids, properties=properties).values()

        if thing1s_is_single and thing2s_is_single:
            if rels:
                assert len(rels) == 1
                return rels[0]
            else:
                raise NotFound("<%s %r>" % (cls.__name__,
                                            cls._rowkey(thing1s[0]._id36,
                                                        thing2s[0]._id36)))

        return dict(((thing1_ids[rel.thing1_id], thing2_ids[rel.thing2_id]), rel)
                    for rel in rels)

    @classmethod
    def _from_columns(cls, t_id, columns):
        # we deserialize relations a little specially so that we can
        # throw our toys on the floor if they don't have thing1_id and
        # thing2_id
        if not ('thing1_id' in columns and 'thing2_id' in columns
                and t_id == cls._rowkey(columns['thing1_id'], columns['thing2_id'])):
            raise InvariantException("Looked up %r with unmatched IDs (%r)"
                                     % (cls, t_id))

        # if modifying this, check ThingBase._from_columns and see if
        # you should change it as well
        thing1_id, thing2_id = columns['thing1_id'], columns['thing2_id']
        t = cls(thing1_id = thing1_id, thing2_id = thing2_id)
        assert t._id == t_id
        t._orig = columns
        t._committed = True
        return t

    @staticmethod
    def _rowkey(thing1_id36, thing2_id36):
        assert isinstance(thing1_id36, basestring) and isinstance(thing2_id36, basestring)
        return '%s_%s' % (thing1_id36, thing2_id36)

    def _commit(self, *a, **kw):
        assert self._id == self._rowkey(self.thing1_id, self.thing2_id)

        retval = ThingBase._commit(self, *a, **kw)

        from r2.models.last_modified import LastModified
        fullname = self._thing1_cls._fullname_from_id36(self.thing1_id)
        LastModified.touch(fullname, self._cf.column_family)

        return retval

    @classmethod
    def _rel(cls, thing1_cls, thing2_cls):
        # should be implemented by abstract relations, like Vote
        raise NotImplementedError

    @classmethod
    def _datekey(cls, date):
        # ick
        return str(long(cls._serialize_date(date)))


def view_of(cls):
    """Register a class as a view of a DenormalizedRelation.

    Views are expected to implement two methods:

        create - called on relationship creation. takes a thing1, a list
                 of thing2s and opaque, extra data passed from above.

        delete - called on relationship destruction. takes a thing1, a list
                 of things2 and opaque.

    """
    def view_of_decorator(view_cls):
        cls._views.append(view_cls)
        return view_cls
    return view_of_decorator



class DenormalizedRelation(object):
    """A model of many-to-many relationships, indexed by thing1.

    Each thing1 is represented by a row. The relationships from that thing1 to
    a number of thing2s are represented by columns in that row. To query if
    relationships exist and what its value is ("name" in the PG model), we
    fetch the thing1's row, telling C* we're only interested in the columns
    representing the thing2s we are interested in. This allows negative lookups
    to be very fast because of the row-level bloom filter.

    This data model will generate VERY wide rows. Any column family based on
    it should have its row cache disabled.

    """
    __metaclass__ = ThingMeta
    _use_db = False
    _cf_name = None
    _compare_with = ASCII_TYPE
    _type_prefix = None
    _last_modified_name = None
    _write_last_modified = True
    _extra_schema_creation_args = dict(key_validation_class=ASCII_TYPE,
                                       default_validation_class=UTF8_TYPE)

    @classmethod
    def value_for(cls, thing1, thing2, opaque):
        """Return a value to store for a relationship between thing1/thing2."""
        raise NotImplementedError()

    @classmethod
    def create(cls, thing1, thing2s, opaque=None):
        """Create a relationship between thing1 and thing2s.

        If there are any other views of this data, they will be updated as
        well.

        Takes an optional parameter "opaque" which can be used by views
        or value_for to get additional information.

        """
        thing2s = tup(thing2s)
        values = {thing2._id36 : cls.value_for(thing1, thing2, opaque)
                  for thing2 in thing2s}
        cls._cf.insert(thing1._id36, values)

        for view in cls._views:
            view.create(thing1, thing2s, opaque)

        if cls._write_last_modified:
            from r2.models.last_modified import LastModified
            LastModified.touch(thing1._fullname, cls._last_modified_name)

    @classmethod
    def destroy(cls, thing1, thing2s):
        """Destroy relationships between thing1 and some thing2s."""
        thing2s = tup(thing2s)
        cls._cf.remove(thing1._id36, (thing2._id36 for thing2 in thing2s))

        for view in cls._views:
            view.destroy(thing1, thing2s)

    @classmethod
    def fast_query(cls, thing1, thing2s):
        """Find relationships between thing1 and various thing2s."""
        thing2s, thing2s_is_single = tup(thing2s, ret_is_single=True)

        if not thing1:
            return {}

        # don't bother looking up relationships for items that were created
        # since the last time the thing1 created a relationship of this type
        if cls._last_modified_name:
            from r2.models.last_modified import LastModified
            timestamp = LastModified.get(thing1._fullname,
                                         cls._last_modified_name)
            if timestamp:
                thing2s = [thing2 for thing2 in thing2s
                           if thing2._date <= timestamp]
            else:
                thing2s = []

        if not thing2s:
            return {}

        # fetch the row from cassandra. if it doesn't exist, thing1 has no
        # relation of this type to any thing2!
        try:
            columns = [thing2._id36 for thing2 in thing2s]
            results = cls._cf.get(thing1._id36, columns)
        except NotFoundException:
            results = {}

        # return the data in the expected format
        if not thing2s_is_single:
            # {(thing1, thing2) : value}
            thing2s_by_id = {thing2._id36 : thing2 for thing2 in thing2s}
            return {(thing1, thing2s_by_id[k]) : v
                    for k, v in results.iteritems()}
        else:
            if results:
                assert len(results) == 1
                return results[0]
            else:
                raise NotFound("<%s %r>" % (cls.__name__, (thing1._id36,
                                                           thing2._id36)))


class ColumnQuery(object):
    """
    A query across a row of a CF.
    """
    _chunk_size = 100

    def __init__(self, cls, rowkeys, column_start="", column_finish="", 
                 column_count=100, column_reversed=True, 
                 column_to_obj=None,
                 obj_to_column=None):
        self.cls = cls
        self.rowkeys = rowkeys
        self.column_start = column_start
        self.column_finish = column_finish
        self._limit = column_count
        self.column_reversed = column_reversed
        self.column_to_obj = column_to_obj or self.default_column_to_obj
        self.obj_to_column = obj_to_column or self.default_obj_to_column
        self._rules = []    # dummy parameter to mimic tdb_sql queries

        # Sorting for TimeUuid objects
        if self.cls._compare_with == TIME_UUID_TYPE:
            def sort_key(i):
                return i.time
        else:
            def sort_key(i):
                return i
        self.sort_key = sort_key

    @staticmethod
    def combine(queries):
        raise NotImplementedError

    @staticmethod
    def default_column_to_obj(columns):
        """
        Mapping from column --> object. 
        
        This default doesn't actually return the underlying object but we don't 
        know how to do that without more information. 
        """
        return columns

    @staticmethod
    def default_obj_to_column(objs):
        """
        Mapping from object --> column
        """
        objs, is_single = tup(objs, ret_is_single=True)
        columns = [{obj._id: obj._id} for obj in objs]

        if is_single:
            return columns[0]
        else:
            return columns

    def _after(self, thing):
        if thing:
            column_name = self.obj_to_column(thing).keys()[0]
            self.column_start = column_name
        else:
            self.column_start = ""

    def _after_id(self, column_name):
        self.column_start = column_name

    def _reverse(self):
        # Logic of standard reddit query is opposite of cassandra
        self.column_reversed = False

    def __iter__(self, yield_column_names=False):
        retrieved = 0
        column_start = self.column_start
        while retrieved < self._limit:
            try:
                column_count = min(self._chunk_size, self._limit - retrieved)
                if column_start:
                    column_count += 1   # cassandra includes column_start
                r = self.cls._cf.multiget(self.rowkeys,
                                          column_start=column_start,
                                          column_finish=self.column_finish,
                                          column_count=column_count,
                                          column_reversed=self.column_reversed)

                # multiget returns OrderedDict {rowkey: {column_name: column_value}}
                # combine into single OrderedDict of {column_name: column_value}
                nrows = len(r.keys())
                if nrows == 0:
                    return
                elif nrows == 1:
                    columns = r.values()[0]
                else:
                    r_combined = {}
                    for d in r.values():
                        r_combined.update(d)
                    columns = OrderedDict(sorted(r_combined.items(),
                                                 key=lambda t: self.sort_key(t[0]),
                                                 reverse=self.column_reversed))
            except NotFoundException:
                return

            retrieved += self._chunk_size

            if column_start:
                try:
                    del columns[column_start]
                except KeyError:
                    columns.popitem(last=True)  # remove extra column

            if not columns:
                return

            # Convert to list of columns
            l_columns = [{col_name: columns[col_name]} for col_name in columns]

            column_start = l_columns[-1].keys()[0]
            objs = self.column_to_obj(l_columns)

            if yield_column_names:
                column_names = [column.keys()[0] for column in l_columns]
                if len(column_names) == 1:
                    ret = (column_names[0], objs),
                else:
                    ret = zip(column_names, objs)
            else:
                ret = objs

            ret, is_single = tup(ret, ret_is_single=True)
            for r in ret:
                yield r

    def __repr__(self):
        return "<%s(%s-%r)>" % (self.__class__.__name__, self.cls.__name__, 
                                self.rowkeys)

class MultiColumnQuery(object):
    def __init__(self, queries, num, sort_key=None):
        self.num = num
        self._queries = queries
        self.sort_key = sort_key    # python doesn't sort UUID1's correctly, need to pass in a sorter
        self._rules = []            # dummy parameter to mimic tdb_sql queries

    def _after(self, thing):
        for q in self._queries:
            q._after(thing)

    def _reverse(self):
        for q in self._queries:
            q._reverse()

    def __setattr__(self, attr, val):
        # Catch _limit to set on all queries
        if attr == '_limit':
             for q in self._queries:
                 q._limit = val
        else:
            object.__setattr__(self, attr, val)

    def __iter__(self):

        if self.sort_key:
            def sort_key(tup):
                # Need to point the supplied sort key at the correct item in 
                # the (sortable, item, generator) tuple
                return self.sort_key(tup[0])
        else:
            def sort_key(tup):
                return tup[0]

        top_items = []
        for q in self._queries:
            try:
                gen = q.__iter__(yield_column_names=True)
                column_name, item = gen.next()
                top_items.append((column_name, item, gen))
            except StopIteration:
                pass
        top_items.sort(key=sort_key)

        def _update(top_items):
            # Remove the first item from combined query and update the list
            head = top_items.pop(0)
            item = head[1]
            gen = head[2]

            # Try to get a new item from the query that gave us the current one
            try:
                column_name, item = gen.next()
                top_items.append((column_name, item, gen)) # if multiple queues have the same item value the sort is somewhat undefined
                top_items.sort(key=sort_key)
            except StopIteration:
                pass

        num_ret = 0
        while top_items and num_ret < self.num:
            yield top_items[0][1]
            _update(top_items)
            num_ret += 1

class Query(object):
    """A query across a CF. Note that while you can query rows from a
       CF that has a RandomPartitioner, you won't get them in any sort
       of order"""
    def __init__(self, cls, after=None, properties=None, limit=100,
                 chunk_size=100, _max_column_count = max_column_count):
        self.cls = cls
        self.after = after
        self.properties = properties
        self.limit = limit
        self.chunk_size = chunk_size
        self.max_column_count = _max_column_count

    def __copy__(self):
        return Query(self.cls, after=self.after,
                     properties = self.properties,
                     limit=self.limit,
                     chunk_size=self.chunk_size,
                     _max_column_count = self.max_column_count)
    copy = __copy__

    def _dump(self):
        q = self.copy()
        q.after = q.limit = None

        for row in q:
            print row
            for col, val in row._t.iteritems():
                print '\t%s: %r' % (col, val)

    @will_write
    def _delete_all(self, write_consistency_level = None):
        # uncomment to use on purpose
        raise InvariantException("Nice try, FBI")

        # TODO: this could use cf.truncate instead and be *way*
        # faster, but it wouldn't flush the thing_cache at the same
        # time that way

        q = self.copy()
        q.after = q.limit = None

        # since we're just deleting it, we only need enough columns to
        # avoid reading ghost rows
        q.max_column_count = 1

        # I'm going to guess that if they are trying to flush out an
        # entire CF, they aren't that worried about how long it takes
        # to become consistent. So we'll default to the fastest way
        wcl = q.cls._wcl(write_consistency_level, CL.ONE)

        for row in q:
            print row

            # n.b. we're not calling _on_destroy!
            q.cls._cf.remove(row._id, write_consistency_level = wcl)
            thing_cache.delete(q.cls._cache_key_id(row._id))

    def __iter__(self):
        # n.b.: we aren't caching objects that we find this way in the
        # LocalCache. This may will need to be changed if we ever
        # start using OPP in Cassandra (since otherwise these types of
        # queries aren't useful for anything but debugging anyway)
        after = '' if self.after is None else self.after._id
        limit = self.limit

        if self.properties is None:
            r = self.cls._cf.get_range(start=after, row_count=limit,
                                       column_count = self.max_column_count)
        else:
            r = self.cls._cf.get_range(start=after, row_count=limit,
                                       columns = self.properties)

        for t_id, columns in r:
            if not columns:
                # a ghost row
                continue

            t = self.cls._from_serialized_columns(t_id, columns)
            yield t

class View(ThingBase):
    # Views are Things like any other, but may have special key
    # characteristics. Uses ColumnQuery for queries across a row. 

    _timestamp_prop = None
    _value_type = 'str'

    _compare_with = UTF8_TYPE   # Type of the columns - should match _key_validation_class of _view_of class
    _view_of = None
    _write_consistency_level = CL.ONE   # Is this necessary?
    _query_cls = ColumnQuery

    @classmethod
    def _rowkey(cls, obj):
        """Mapping from _view_of object --> view rowkey. No default
        implementation is provided because this is the fundamental aspect of the
        view."""
        raise NotImplementedError

    @classmethod
    def _obj_to_column(cls, objs):
        """Mapping from _view_of object --> view column. Returns a 
        single item dict {column name:column value} or list of dicts."""
        objs, is_single = tup(objs, ret_is_single=True)

        columns = [{obj._id: obj._id} for obj in objs]

        if len(columns) == 1:
            return columns[0]
        else:
            return columns

    @classmethod
    def _column_to_obj(cls, columns):
        """Mapping from view column --> _view_of object. Must be complement to
        _obj_to_column()."""
        columns, is_single = tup(columns, ret_is_single=True)

        ids = [column.keys()[0] for column in columns]

        if len(ids) == 1:
            ids = ids[0]
        return cls._view_of._byID(ids, return_dict=False)

    @classmethod
    def add_object(cls, obj, **kw):
        """Add a lookup to the view"""
        rowkey = cls._rowkey(obj)
        column = cls._obj_to_column(obj)
        cls._set_values(rowkey, column, **kw)

    @classmethod
    def query(cls, rowkeys, after=None, reverse=False, count=1000):
        """Return a query to get objects from the underlying _view_of class."""

        column_reversed = not reverse   # Reverse convention for cassandra is opposite

        q = cls._query_cls(cls, rowkeys, column_count=count, 
                           column_reversed=column_reversed,
                           column_to_obj=cls._column_to_obj,
                           obj_to_column=cls._obj_to_column)
        q._after(after)
        return q

    def _values(self):
        """Retrieve the entire contents of the view"""
        # TODO: at present this only grabs max_column_count columns
        return self._t

    @classmethod
    @will_write
    def _set_values(cls, row_key, col_values,
                    write_consistency_level = None,
                    ttl=None):
        """Set a set of column values in a row of a view without
           looking up the whole row first"""
        # col_values =:= dict(col_name -> col_value)

        updates = dict((col_name, cls._serialize_column(col_name, col_val))
                       for (col_name, col_val) in col_values.iteritems())

        # if they didn't give us a TTL, use the default TTL for the
        # class. This will be further overwritten below per-column
        # based on the _default_ttls class dict. Note! There is no way
        # to use this API to express that you don't want a TTL if
        # there is a default set on either the row or the column
        default_ttl = ttl or cls._ttl

        with cls._cf.batch(write_consistency_level = cls._wcl(write_consistency_level)) as b:
            # with some quick tweaks we could have a version that
            # operates across multiple row keys, but this is not it
            for k, v in updates.iteritems():
                b.insert(row_key, {k: v},
                         ttl=cls._default_ttls.get(k, default_ttl))

        # can we be smarter here?
        thing_cache.delete(cls._cache_key_id(row_key))
    
    @classmethod
    @will_write
    def _remove(cls, key, columns):
        cls._cf.remove(key, columns)
        thing_cache.delete(cls._cache_key_id(key))

class DenormalizedView(View):
    """Store the entire underlying object inside the View column."""

    @classmethod
    def is_date_prop(cls, attr):
        view_cls = cls._view_of
        return (view_cls._value_type == 'date' or
                attr in view_cls._date_props or
                view_cls._timestamp_prop and attr == view_cls._timestamp_prop)

    @classmethod
    def _thing_dumper(cls, thing):
        serialize_fn = cls._view_of._serialize_column
        serialized_columns = dict((attr, serialize_fn(attr, val)) for
            (attr, val) in thing._orig.iteritems())

        # Encode date props which may be binary
        for attr, val in serialized_columns.items():
            if cls.is_date_prop(attr):
                serialized_columns[attr] = base64.b64encode(val)

        dump = json.dumps(serialized_columns)
        return dump

    @classmethod
    def _thing_loader(cls, _id, dump):
        serialized_columns = json.loads(dump)

        # Decode date props
        for attr, val in serialized_columns.items():
            if cls.is_date_prop(attr):
                serialized_columns[attr] = base64.b64decode(val)

        obj = cls._view_of._from_serialized_columns(_id, serialized_columns)
        return obj

    @classmethod
    def _obj_to_column(cls, objs):
        objs = tup(objs)
        columns = []
        for o in objs:
            _id = o._id
            dump = cls._thing_dumper(o)
            columns.append({_id: dump})

        if len(columns) == 1:
            return columns[0]
        else:
            return columns

    @classmethod
    def _column_to_obj(cls, columns):
        columns = tup(columns)
        objs = []
        for column in columns:
            _id, dump = column.items()[0]
            obj = cls._thing_loader(_id, dump)
            objs.append(obj)

        if len(objs) == 1:
            return objs[0]
        else:
            return objs

def schema_report():
    manager = get_manager()
    print manager.describe_keyspace(keyspace)

def ring_report():
    # uses a silly algorithm to pick natural endpoints that requires N>=RF+1

    sizes = {}
    nodes = {} # token -> node

    manager = get_manager()

    ring = manager.describe_ring(keyspace)
    ring.sort(key=lambda tr: long(tr.start_token))

    for x, tr in enumerate(ring):
        next = ring[x+1] if x < len(ring)-1 else ring[0]

        # tr = ring1[x]
        # next = ring1[x+1]

        s = long(tr.start_token)
        e = long(tr.end_token)

        if e > s:
            # a regular range
            l = e-s
        else:
            # range that overlaps 0
            l = e+2**127-s

        for ep in tr.endpoints:
            sizes.setdefault(ep, []).append(float(l)/2**127)

        natural = set(tr.endpoints) - set(next.endpoints)
        assert len(natural) == 1
        natural = natural.pop()

        nodes[e] = natural

    totalsize = sum(map(sum, sizes.values()))
    for token, ip in sorted(nodes.items(),
                              key = lambda x: x[0]):
        size = sizes[ip]
        name = gethostbyaddr(ip)[0]

        fmt_perc = lambda num: '%s%2.2f%%' % (' ' if num < 10 else '',
                                              num)
        maxtoklen = len(str(2**127))

        print '%16s\t%s\t%s\t%s' % (ip, name,
                                    fmt_perc(sum(size)/totalsize * 100),
                                    str(token).rjust(maxtoklen))
