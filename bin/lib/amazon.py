from datetime import datetime
from operator import attrgetter

from lib.releases import Version, Release, Hash, VersionSource


class LazyObjectWrapper:
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


# this is a free function to avoid potentially shadowing any underlying members
# which could happen if this was itself placed as a member of LazyObjectWrapper
def force_lazy_init(lazy):
    # pylint: disable=W0212
    lazy._LazyObjectWrapper__ensure_setup()


def _import_boto():
    obj = __import__('boto3')

    if not obj.session.Session().region_name:
        obj.setup_default_session(region_name='us-east-1')

    return obj


botocore = LazyObjectWrapper(lambda: __import__('botocore'))
boto3 = LazyObjectWrapper(_import_boto)


def _create_anon_s3_client():
    # https://github.com/boto/botocore/issues/1395
    obj = boto3.client('s3', aws_access_key_id='', aws_secret_access_key='')
    # pylint: disable=W0212
    obj._request_signer.sign = (lambda *args, **kwargs: None)
    return obj


ec2 = LazyObjectWrapper(lambda: boto3.resource('ec2'))
s3 = LazyObjectWrapper(lambda: boto3.resource('s3'))
as_client = LazyObjectWrapper(lambda: boto3.client('autoscaling'))
elb_client = LazyObjectWrapper(lambda: boto3.client('elbv2'))
s3_client = LazyObjectWrapper(lambda: boto3.client('s3'))
anon_s3_client = LazyObjectWrapper(_create_anon_s3_client)
dynamodb_client = LazyObjectWrapper(lambda: boto3.client('dynamodb'))
ssm_client = LazyObjectWrapper(lambda: boto3.client('ssm'))
LINKS_TABLE = 'links'
VERSIONS_LOGGING_TABLE = 'versionslog'


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
        Delete={'Objects': [{'Key': release.key}, {'Key': release.static_key}, {'Key': release.info_key}]}
    )


def _get_releases(source: VersionSource, prefix: str):
    paginator = s3_client.get_paginator('list_objects_v2')
    result_iterator = paginator.paginate(
        Bucket='compiler-explorer',
        Prefix=prefix
    )

    staticfiles = {}
    releases = {}
    for result in result_iterator.search('[Contents][]'):
        key = result['Key']
        if not key.endswith(".tar.xz"):
            continue
        split_key = key.split('/')
        branch = '/'.join(split_key[2:-1])
        version_str = split_key[-1].split('.')[0]
        version = Version(source, int(version_str))

        if key.endswith('.static.tar.xz'):
            staticfiles[version] = key
            continue

        size = result['Size']
        info_key = "/".join(split_key[:-1]) + "/" + version_str + ".txt"
        o = s3_client.get_object(
            Bucket='compiler-explorer',
            Key=info_key
        )
        release_hash = Hash(o['Body'].read().decode("utf-8").strip())
        releases[version] = Release(version, branch, key, info_key, size, release_hash)

    for ver, key in staticfiles.items():
        r = releases.get(ver)
        if r:
            r.static_key = key

    return list(releases.values())


def get_releases():
    return _get_releases(VersionSource.TRAVIS, 'dist/travis') + _get_releases(VersionSource.GITHUB, 'dist/gh')


def download_release_file(file, destination):
    s3_client.download_file('compiler-explorer', file, destination)


def download_release_fileobj(key, fobj):
    s3_client.download_fileobj('compiler-explorer', key, fobj)


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
    for branch in ['release', 'beta', 'staging']:
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
    current_time = datetime.utcnow().isoformat()
    new_item = {
        'buildId': {'S': new_version},
        'timestamp': {'S': current_time},
        'env': {'S': args['env']}
    }
    dynamodb_client.put_item(TableName=VERSIONS_LOGGING_TABLE, Item=new_item)


def print_version_logs(items):
    for item in items:
        print('{} (from {}) at {}'.format(item['buildId']['S'], item['env']['S'], item['timestamp']['S']))


def list_all_build_logs(args):
    result = dynamodb_client.scan(TableName=VERSIONS_LOGGING_TABLE,
                                  FilterExpression='env = :environment',
                                  ExpressionAttributeValues={':environment': {'S': args['env']}})
    print_version_logs(result.get('Items', []))


def list_period_build_logs(args, from_time, until_time):
    result = None
    if from_time is None and until_time is None:
        #  Our only calling site already checks this, but added as fallback just in case
        list_all_build_logs(args)
    elif from_time is None:
        assert (until_time is not None), "Required field --until is missing"
        result = dynamodb_client.scan(TableName=VERSIONS_LOGGING_TABLE,
                                      FilterExpression='#ts <= :until and env = :environment',
                                      ExpressionAttributeValues={':until': {'S': until_time},
                                                                 ':environment': {'S': args['env']}},
                                      ExpressionAttributeNames={'#ts': 'timestamp'})
    elif until_time is None:
        assert (from_time is not None), "Required field --from is missing"
        result = dynamodb_client.scan(TableName=VERSIONS_LOGGING_TABLE,
                                      FilterExpression='#ts >= :from and env = :environment',
                                      ExpressionAttributeValues={':from': {'S': from_time},
                                                                 ':environment': {'S': args['env']}},
                                      ExpressionAttributeNames={'#ts': 'timestamp'})
    else:
        assert (until_time is not None and from_time is not None), "Expected both --until and --from to be filled"
        result = dynamodb_client.scan(TableName=VERSIONS_LOGGING_TABLE,
                                      FilterExpression='#ts BETWEEN :from AND :until and env = :environment',
                                      ExpressionAttributeValues={':until': {'S': until_time},
                                                                 ':from': {'S': from_time},
                                                                 ':environment': {'S': args['env']}},
                                      ExpressionAttributeNames={'#ts': 'timestamp'})
    if result is not None:
        print_version_logs(result.get('Items', []))


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
    s3_paginator = anon_s3_client.get_paginator('list_objects_v2')
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


def list_s3_artifacts(bucket, prefix):
    s3_paginator = anon_s3_client.get_paginator('list_objects_v2')
    for page in s3_paginator.paginate(Bucket=bucket, Prefix=prefix):
        if page['KeyCount']:
            for match in page['Contents']:
                yield match['Key']


def get_ssm_param(param):
    return ssm_client.get_parameter(Name=param)['Parameter']['Value']
