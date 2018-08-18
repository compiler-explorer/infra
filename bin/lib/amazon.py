import boto3
from operator import attrgetter

ec2 = boto3.resource('ec2')
s3 = boto3.resource('s3')
as_client = boto3.client('autoscaling')
elb_client = boto3.client('elbv2')
s3_client = boto3.client('s3')
dynamodb_client = boto3.client('dynamodb')
LINKS_TABLE = 'links'

class Hash(object):
    def __init__(self, hash):
        self.hash = hash

    def __repr__(self):
        return self.hash

    def __str__(self):
        return self.hash[:6] + ".." + self.hash[-6:]


class Release(object):
    def __init__(self, version, branch, key, info_key, size, hash):
        self.version = version
        self.branch = branch
        self.key = key
        self.info_key = info_key
        self.size = size
        self.hash = hash

    def __repr__(self):
        return 'Release({}, {}, {}, {}, {})'.format(self.version, self.branch, self.key, self.size, self.hash)


# TODO document aws policy needed.
# S3-compiler-explorer-access seems to be fairly minimal. XaniaBlog seems too open

def target_group_arn_for(args):
    if args['env'] == 'prod':
        return 'arn:aws:elasticloadbalancing:us-east-1:052730242331:targetgroup/GccExplorerNodes/84e7c7626fd50397'
    else:
        return 'arn:aws:elasticloadbalancing:us-east-1:052730242331:targetgroup/Beta/07d45244520b84c4'


def get_autoscaling_group(group_name):
    result = as_client.describe_auto_scaling_groups(AutoScalingGroupNames=[group_name])
    return result['AutoScalingGroups'][0]


def remove_release(release):
    s3_client.delete_objects(
        Bucket='compiler-explorer',
        Delete={'Objects': [{'Key': release.key}, {'Key': release.info_key}]}
    )


def get_releases():
    paginator = s3_client.get_paginator('list_objects_v2')
    PREFIX = 'dist/travis/'
    result_iterator = paginator.paginate(
        Bucket='compiler-explorer',
        Prefix=PREFIX
    )
    releases = []
    for result in result_iterator.search('[Contents][]'):
        key = result['Key']
        if not key.endswith(".tar.xz"):
            continue
        split_key = key.split('/')
        branch = split_key[-2]
        version = split_key[-1].split('.')[0]
        size = result['Size']
        info_key = "/".join(split_key[:-1]) + "/" + version + ".txt"
        o = s3_client.get_object(
            Bucket='compiler-explorer',
            Key=info_key
        )
        hash = o['Body'].read().strip()
        releases.append(Release(int(version), branch, key, info_key, size, Hash(hash)))
    return releases


def find_release(version):
    for r in get_releases():
        if r.version == version:
            return r
    return None


def find_latest_release(branch):
    releases = [release for release in get_releases() if branch == '' or release.branch == branch]
    return max(releases, key=attrgetter('version')) if len(releases) > 0 else None


def branch_for_env(args):
    if args['env'] == 'prod':
        return 'release'
    elif args['env'] == 'beta':
        return 'beta'
    else:
        return 'master'


def version_key_for_env(env):
    return 'version/{}'.format(branch_for_env(env))


def get_current_key(args):
    try:
        o = s3_client.get_object(
            Bucket='compiler-explorer',
            Key=version_key_for_env(args)
        )
        return o['Body'].read().strip()
    except s3_client.exceptions.NoSuchKey:
        return None


def get_all_current():
    versions = []
    for branch in ['release', 'beta', 'master']:
        try:
            o = s3_client.get_object(
                Bucket='compiler-explorer',
                Key='version/{}'.format(branch)
            )
            versions.append(o['Body'].read().strip())
        except s3_client.exceptions.NoSuchKey:
            pass
    return versions


def set_current_key(args, key):
    s3_key = version_key_for_env(args)
    print 'Setting {} to {}'.format(s3_key, key)
    s3_client.put_object(
        Bucket='compiler-explorer',
        Key=s3_key,
        Body=key,
        ACL='public-read'
    )


def release_for(releases, s3_key):
    for r in releases:
        if r.key == s3_key:
            return r
    return None


def get_events_file(args):
    try:
        o = s3_client.get_object(
            Bucket='compiler-explorer',
            Key=events_file_for(args)
        )
        return o['Body'].read()
    except s3_client.exceptions.NoSuchKey:
        pass


def save_event_file(args, contents):
    s3_client.put_object(
        Bucket='compiler-explorer',
        Key=events_file_for(args),
        Body=contents,
        ACL='public-read',
        CacheControl='public, max-age=60'
    )


def events_file_for(args):
    events_file = 'motd/motd-{}.json'.format(args['env'])
    return events_file


def get_short_link(short_id):
    result = dynamodb_client.get_item(TableName=LINKS_TABLE, Key={
        'prefix': {'S': short_id[:6]},
        'unique_subhash': {'S': short_id}
    }, ConsistentRead=True)
    return result.get('Item')


def put_short_link(item):
    dynamodb_client.put_item(TableName=LINKS_TABLE, Item=item)


def delete_short_link(item):
    dynamodb_client.delete_item(TableName=LINKS_TABLE, Key={'prefix': {'S': item[:6]}, 'unique_subhash': {'S': item}})


def delete_s3_links(items):
    s3_client.delete_objects(
        Bucket='storage.godbolt.org',
        Delete={'Objects': [{'Key': item} for item in items]}
    )


def list_short_links():
    s3_paginator = s3_client.get_paginator('list_objects_v2')
    db_paginator = dynamodb_client.get_paginator('scan')
    return (s3_paginator.paginate(Bucket='storage.godbolt.org', Prefix='state/'),
            db_paginator.paginate(TableName=LINKS_TABLE, ProjectionExpression='unique_subhash, full_hash, creation_ip'))
