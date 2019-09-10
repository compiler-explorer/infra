from operator import attrgetter
import time


class LazyObjectWrapper(object):
    def __init__(self, fn):
        self.__fn = fn
        self.__setup = False
        self.__obj = None

    def __ensure_setup(self):
        if not self.__setup:
            self.__obj = self.__fn()
            self.__setup = True

    def __getattr__(self, attr):
        self.__ensure_setup()
        return getattr(self.__obj, attr)


def _import_boto():
    obj = __import__('boto3')

    if not obj.session.Session().region_name:
        obj.setup_default_session(region_name='us-east-1')

    return obj


boto3 = LazyObjectWrapper(_import_boto)
ec2 = LazyObjectWrapper(lambda: boto3.resource('ec2'))
s3 = LazyObjectWrapper(lambda: boto3.resource('s3'))
as_client = LazyObjectWrapper(lambda: boto3.client('autoscaling'))
elb_client = LazyObjectWrapper(lambda: boto3.client('elbv2'))
s3_client = LazyObjectWrapper(lambda: boto3.client('s3'))
dynamodb_client = LazyObjectWrapper(lambda: boto3.client('dynamodb'))
LINKS_TABLE = 'links'
VERSIONS_LOGGING_TABLE = 'versionslog'


class Hash(object):
    def __init__(self, hash):
        self.hash = hash

    def __repr__(self):
        return self.hash

    def __str__(self):
        return f'{str(self.hash[:6])}..{str(self.hash[-6:])}'


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


def target_group_for(args):
    result = elb_client.describe_target_groups(Names=[args['env'].title()])
    if len(result['TargetGroups']) != 1:
        raise RuntimeError(f"Invalid environment {args['env']}")
    return result['TargetGroups'][0]


def target_group_arn_for(args):
    return target_group_for(args)['TargetGroupArn']


def get_autoscaling_group(group_name):
    result = as_client.describe_auto_scaling_groups(AutoScalingGroupNames=[group_name])
    return result['AutoScalingGroups'][0]


def get_autoscaling_groups_for(args):
    def finder(r):
        for k in r['Tags']:
            if k['Key'] == 'Name' and k['Value'] == args['env'].title():
                return r

    result = list(filter(finder, as_client.describe_auto_scaling_groups()['AutoScalingGroups']))
    if not result:
        raise RuntimeError(f"Invalid environment {args['env']}")
    return result


def remove_release(release):
    s3_client.delete_objects(
        Bucket='compiler-explorer',
        Delete={'Objects': [{'Key': release.key}, {'Key': release.info_key}]}
    )


def get_releases():
    paginator = s3_client.get_paginator('list_objects_v2')
    prefix = 'dist/travis/'
    result_iterator = paginator.paginate(
        Bucket='compiler-explorer',
        Prefix=prefix
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
        hash = o['Body'].read().decode("utf-8").strip()
        releases.append(Release(int(version), branch, key, info_key, size, Hash(hash)))
    return releases


def download_release_file(file, destination):
    s3_client.download_file('compiler-explorer', file, destination)


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
    return args['env']


def version_key_for_env(env):
    return 'version/{}'.format(branch_for_env(env))


def get_current_key(args):
    try:
        o = s3_client.get_object(
            Bucket='compiler-explorer',
            Key=version_key_for_env(args)
        )
        return o['Body'].read().decode("utf-8").strip()
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
            versions.append(o['Body'].read().decode("utf-8").strip())
        except s3_client.exceptions.NoSuchKey:
            pass
    return versions


def set_current_key(args, key):
    s3_key = version_key_for_env(args)
    print('Setting {} to {}'.format(s3_key, key))
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
        return o['Body'].read().decode("utf-8")
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


def log_new_build(args, new_version):
    current_time = int(time.time())
    new_item = {
        'buildId': new_version,
        'timestamp': current_time,
        'branch': args['branch'],
        'env': args['env']
    }
    dynamodb_client.put_item(TableName=VERSIONS_LOGGING_TABLE, Item=new_item)


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


def list_compilers(with_extension=False):
    s3_paginator = s3_client.get_paginator('list_objects_v2')
    prefix = 'opt/'
    for page in s3_paginator.paginate(Bucket='compiler-explorer', Prefix=prefix):
        for compiler in page['Contents']:
            name = compiler['Key'][len(prefix):]
            if with_extension:
                yield name
            else:
                name = name[:name.find(".tar")]
                if not name:
                    continue
                yield name
