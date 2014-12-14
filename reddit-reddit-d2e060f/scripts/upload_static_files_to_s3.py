#!/usr/bin/python
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


import os
import boto
import mimetypes
import ConfigParser

NEVER = 'Thu, 31 Dec 2037 23:59:59 GMT'

mimetypes.encodings_map['.gzip'] = 'gzip'

def upload(config_file):
    # grab the configuration
    parser = ConfigParser.RawConfigParser()
    with open(config_file, "r") as cf:
        parser.readfp(cf)
    aws_access_key_id = parser.get("static_files", "aws_access_key_id")
    aws_secret_access_key = parser.get("static_files",
                                       "aws_secret_access_key")
    static_root = parser.get("static_files", "static_root")
    bucket_name = parser.get("static_files", "bucket")

    # start up the s3 connection
    s3 = boto.connect_s3(aws_access_key_id, aws_secret_access_key)
    bucket = s3.get_bucket(bucket_name)

    # build a list of files already in the bucket
    remote_files = {key.name : key.etag.strip('"') for key in bucket.list()}

    # upload local files not already in the bucket
    for root, dirs, files in os.walk(static_root):
        for file in files:
            absolute_path = os.path.join(root, file)

            key_name = os.path.relpath(absolute_path, start=static_root)

            type, encoding = mimetypes.guess_type(file)
            if not type:
                continue
            headers = {}
            headers['Expires'] = NEVER
            headers['Content-Type'] = type
            if encoding:
                headers['Content-Encoding'] = encoding

            key = bucket.new_key(key_name)
            with open(absolute_path, 'rb') as f:
                etag, base64_tag = key.compute_md5(f)

                # don't upload the file if it already exists unmodified in the bucket
                if remote_files.get(key_name, None) == etag:
                    continue

                print "uploading", key_name, "to S3..."
                key.set_contents_from_file(
                    f,
                    headers=headers,
                    policy='public-read',
                    md5=(etag, base64_tag),
                )


if __name__ == "__main__":
    import sys

    if len(sys.argv) != 2:
        print >> sys.stderr, "USAGE: %s /path/to/config-file.ini" % sys.argv[0]
        sys.exit(1)

    upload(sys.argv[1])
