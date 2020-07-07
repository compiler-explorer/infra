#!/usr/bin/env python3
# coding=utf-8

import datetime
import itertools
import json
import logging
import os
import re
import subprocess
import sys
import tempfile
import time
from argparse import ArgumentParser
from pprint import pprint

import requests

from lib.amazon import target_group_arn_for, get_autoscaling_group, get_releases, find_release, get_current_key, \
    set_current_key, as_client, release_for, find_latest_release, get_all_current, remove_release, get_events_file, \
    save_event_file, get_short_link, put_short_link, delete_short_link, list_short_links, delete_s3_links, \
    get_autoscaling_groups_for, download_release_file, download_release_fileobj, log_new_build, list_all_build_logs, \
    list_period_build_logs, get_ssm_param
from lib.cdn import DeploymentJob
from lib.instance import ConanInstance, AdminInstance, BuilderInstance, Instance, print_instances
from lib.ssh import run_remote_shell, exec_remote, exec_remote_all, exec_remote_to_stdout

logger = logging.getLogger('ce')

RELEASE_FORMAT = '{: <5} {: <10} {: <10} {: <10} {: <14}'
ADS_FORMAT = '{: <5} {: <10} {: <20}'
DECORATION_FORMAT = '{: <10} {: <15} {: <30} {: <50}'


def dispatch_global(sub, args):
    globals()['{}_{}_cmd'.format(sub, args['{}_sub'.format(sub)])](args)


def pick_instance(args):
    instances = Instance.elb_instances(target_group_arn_for(args))
    if len(instances) == 1:
        return instances[0]
    while True:
        print_instances(instances, number=True)
        inst = input('Which instance? ')
        try:
            return instances[int(inst)]
        except (ValueError, IndexError):
            pass


def pick_instances(args):
    # TODO, maybe something in args to select only some?
    return Instance.elb_instances(target_group_arn_for(args))


def sizeof_fmt(num, suffix='B'):
    for unit in ['', 'Ki', 'Mi', 'Gi', 'Ti', 'Pi', 'Ei', 'Zi']:
        if abs(num) < 1024.0:
            return "%3.1f%s%s" % (num, unit, suffix)
        num /= 1024.0
    return "%.1f%s%s" % (num, 'Yi', suffix)


def describe_current_release(args):
    current = get_current_key(args)
    if not current:
        return "none"
    r = release_for(get_releases(), current)
    if r:
        return str(r)
    else:
        "non-standard release with s3 key '{}'".format(current)


def wait_for_autoscale_state(instance, state):
    logger.info("Waiting for %s to reach autoscale lifecycle '%s'...", instance, state)
    while True:
        cur_state = instance.describe_autoscale()['LifecycleState']
        logger.debug("State is %s", cur_state)
        if cur_state == state:
            logger.info("...done")
            return
        time.sleep(5)


def get_events(args):
    events = json.loads(get_events_file(args))
    if 'ads' not in events:
        events['ads'] = []
    if 'decorations' not in events:
        events['decorations'] = []
    if 'motd' not in events:
        events['motd'] = ''
    return events


def save_events(args, events):
    save_event_file(args, json.dumps(events))


def wait_for_elb_state(instance, state):
    logger.info("Waiting for %s to reach ELB state '%s'...", instance, state)
    while True:
        instance.update()
        instance_state = instance.instance.state['Name']
        if instance_state != 'running':
            raise RuntimeError('Instance no longer running (state {})'.format(instance_state))
        logger.debug("State is %s", instance.elb_health)
        if instance.elb_health == state:
            logger.info("...done")
            return
        time.sleep(5)


def are_you_sure(name, args):
    env = args['env']
    while True:
        typed = input(
            'Confirm operation: "{}" in env {}\nType the name of the environment to proceed: '.format(name, env))
        if typed == env:
            return True


def confirm_branch(release):
    branch = release.branch
    while True:
        typed = input('Confirm build branch "{}"\nType the name of the branch: '.format(branch))
        if typed == branch:
            return True


def confirm_action(description):
    typed = input('{}: [Y/N]\n'.format(description))
    return typed.upper() == 'Y'


def is_everything_awesome(instance):
    try:
        response = exec_remote(instance, ['curl', '-s', '--max-time', '2', 'http://127.0.0.1/healthcheck'])
        return response.strip() == "Everything is awesome"
    except subprocess.CalledProcessError:
        return False


def wait_for_healthok(instance):
    logger.info("Waiting for instance to be Online %s", instance)
    sys.stdout.write('Waiting')
    while not is_everything_awesome(instance):
        sys.stdout.write('.')
        # Flush stdout so tmux updates
        sys.stdout.flush()
        time.sleep(10)
    print("Ok, Everything is awesome!")


def restart_one_instance(as_group_name, instance, modified_groups):
    instance_id = instance.instance.instance_id
    logger.info("Enabling instance protection for %s", instance)
    as_client.set_instance_protection(AutoScalingGroupName=as_group_name,
                                      InstanceIds=[instance_id],
                                      ProtectedFromScaleIn=True)
    as_group = get_autoscaling_group(as_group_name)
    adjustment_required = as_group['DesiredCapacity'] == as_group['MinSize']
    if adjustment_required:
        logger.info("Group '%s' needs to be adjusted to keep enough nodes", as_group_name)
        modified_groups[as_group['AutoScalingGroupName']] = as_group['DesiredCapacity']
    logger.info("Putting %s into standby", instance)
    as_client.enter_standby(
        InstanceIds=[instance_id],
        AutoScalingGroupName=as_group_name,
        ShouldDecrementDesiredCapacity=not adjustment_required)
    wait_for_autoscale_state(instance, 'Standby')
    logger.info("Restarting service on %s", instance)
    restart_response = exec_remote(instance, ['sudo', 'systemctl', 'restart', 'compiler-explorer'])
    if restart_response:
        logger.warning("Restart gave some output: %s", restart_response)
    wait_for_healthok(instance)
    logger.info("Moving %s out of standby", instance)
    as_client.exit_standby(
        InstanceIds=[instance_id],
        AutoScalingGroupName=as_group_name)
    wait_for_autoscale_state(instance, 'InService')
    wait_for_elb_state(instance, 'healthy')
    logger.info("Disabling instance protection for %s", instance)
    as_client.set_instance_protection(AutoScalingGroupName=as_group_name,
                                      InstanceIds=[instance_id],
                                      ProtectedFromScaleIn=False)
    logger.info("Instance restarted ok")


def admin_cmd(args):
    run_remote_shell(args, AdminInstance.instance())


def conan_login_cmd(args):
    instance = ConanInstance.instance()
    run_remote_shell(args, instance)


def conan_exec_cmd(args):
    instance = ConanInstance.instance()
    exec_remote_to_stdout(instance, args['remote_cmd'])


def conan_reload_cmd(_):
    instance = ConanInstance.instance()
    exec_remote(instance, ["sudo", "service", "ce-conan", "restart"])


def builder_cmd(args):
    dispatch_global('builder', args)


def builder_login_cmd(args):
    instance = BuilderInstance.instance()
    run_remote_shell(args, instance)


def builder_exec_cmd(args):
    instance = BuilderInstance.instance()
    exec_remote_to_stdout(instance, args['remote_cmd'])


def builder_start_cmd(_):
    instance = BuilderInstance.instance()
    if instance.status() == 'stopped':
        print("Starting builder instance...")
        instance.start()
        for _ in range(60):
            if instance.status() == 'running':
                break
            time.sleep(1)
        else:
            raise RuntimeError("Unable to start instance, still in state: {}".format(instance.status()))
    for _ in range(60):
        try:
            r = exec_remote(instance, ["echo", "hello"])
            if r.strip() == "hello":
                break
        except subprocess.CalledProcessError as e:
            print("Still waiting for SSH: got: {}".format(e))
        time.sleep(1)
    else:
        raise RuntimeError("Unable to get SSH access")
    res = exec_remote(instance,
                      ["bash", "-c", "cd infra && git pull && sudo ./setup-builder-startup.sh"])
    print(res)
    print("Builder started OK")


def builder_stop_cmd(_):
    BuilderInstance.instance().stop()


def builder_status_cmd(_):
    print("Builder status: {}".format(BuilderInstance.instance().status()))


def instances_cmd(args):
    dispatch_global('instances', args)


def instances_exec_all_cmd(args):
    remote_cmd = args['remote_cmd']
    if not are_you_sure(f'exec command {remote_cmd} in all instances', args):
        return

    print("Running '{}' on all instances".format(' '.join(remote_cmd)))
    exec_remote_all(pick_instances(args), remote_cmd)


def instances_login_cmd(args):
    instance = pick_instance(args)
    run_remote_shell(args, instance)


def instances_restart_one_cmd(args):
    instance = pick_instance(args)
    as_instance_status = instance.describe_autoscale()
    as_group_name = as_instance_status['AutoScalingGroupName']
    modified_groups = {}
    try:
        restart_one_instance(as_group_name, instance, modified_groups)
    except RuntimeError as e:
        logger.error("Failed restarting %s - skipping: %s", instance, e)


def instances_start_cmd(args):
    print("Starting version %s", describe_current_release(args))
    exec_remote_all(pick_instances(args), ['sudo', 'systemctl', 'start', 'compiler-explorer'])


def instances_stop_cmd(args):
    if not are_you_sure('stop all instances', args):
        return
    exec_remote_all(pick_instances(args), ['sudo', 'systemctl', 'stop', 'compiler-explorer'])


def instances_restart_cmd(args):
    if not are_you_sure('restart all instances with version {}'.format(describe_current_release(args)), args):
        return
    # Store old motd
    begin_time = datetime.datetime.now()
    events = get_events(args)
    old_motd = events['motd']
    events['motd'] = old_motd if args['motd'] == '' else args['motd']
    save_events(args, events)
    modified_groups = {}
    failed = False
    for instance in pick_instances(args):
        logger.info("Restarting %s...", instance)
        as_instance_status = instance.describe_autoscale()
        as_group_name = as_instance_status['AutoScalingGroupName']
        if as_instance_status['LifecycleState'] != 'InService':
            logger.error("Skipping %s as it is not InService (%s)", instance, as_instance_status)
            continue

        try:
            restart_one_instance(as_group_name, instance, modified_groups)
        except RuntimeError as e:
            logger.error("Failed restarting %s - skipping: %s", instance, e)
            failed = True
            # TODO, what here?

    for group, desired in iter(modified_groups.items()):
        logger.info("Putting desired instances for %s back to %s", group, desired)
        as_client.update_auto_scaling_group(AutoScalingGroupName=group, DesiredCapacity=desired)
    # Events might have changed, re-fetch
    events = get_events(args)
    events['motd'] = old_motd
    save_events(args, events)
    end_time = datetime.datetime.now()
    delta_time = end_time - begin_time
    print(f'Instances restarted in {delta_time.total_seconds()} seconds')
    sys.exit(1 if failed else 0)


def instances_status_cmd(args):
    print_instances(Instance.elb_instances(target_group_arn_for(args)), number=False)


def builds_cmd(args):
    dispatch_global('builds', args)


def builds_current_cmd(args):
    print(describe_current_release(args))


def old_deploy_staticfiles(branch, versionfile):
    print("Deploying static files")
    downloadfile = versionfile
    filename = 'deploy.tar.xz'
    remotefile = branch + '/' + downloadfile
    download_release_file(remotefile[1:], filename)
    os.mkdir('deploy')
    subprocess.call(['tar', '-C', 'deploy', '-Jxf', filename])
    os.remove(filename)
    subprocess.call(['aws', 's3', 'sync', 'deploy/out/dist/dist', 's3://compiler-explorer/dist/cdn'])
    subprocess.call(['rm', '-Rf', 'deploy'])


def deploy_staticfiles(release) -> bool:
    print("Deploying static files to cdn")
    cc = f'public, max-age={int(datetime.timedelta(days=365).total_seconds())}'

    with tempfile.NamedTemporaryFile(suffix=os.path.basename(release.static_key)) as f:
        download_release_fileobj(release.static_key, f)
        with DeploymentJob(f.name, 'ce-cdn.net', version=release.version, cache_control=cc) as job:
            return job.run()


def builds_set_current_cmd(args):
    to_set = None
    release = None
    if args['raw']:
        to_set = args['version']
    else:
        setting_latest = args['version'] == 'latest'
        release = find_latest_release(args['branch']) if setting_latest else find_release(int(args['version']))
        if not release:
            print("Unable to find version " + args['version'])
            if setting_latest and args['branch'] != '':
                print('Branch {} has no available versions (Bad branch/No image yet built)'.format(args['branch']))
        elif are_you_sure('change current version to {}'.format(release.key), args) and confirm_branch(release):
            print('Found release {}'.format(release))
            to_set = release.key
    if to_set is not None:
        log_new_build(args, to_set)
        if release and release.static_key:
            if not deploy_staticfiles(release):
                print("...aborted due to deployment failure!")
                sys.exit(1)
        else:
            old_deploy_staticfiles(args['branch'], to_set)
        set_current_key(args, to_set)
        if release:
            print("Marking as a release in sentry...")
            token = get_ssm_param("/compiler-explorer/sentryAuthToken")
            result = requests.post(
                f"https://sentry.io/api/0/organizations/compiler-explorer/releases/{release.version}/deploys/",
                data=dict(environment=args['env']),
                headers=dict(Authorization=f'Bearer {token}'))
            if not result.ok:
                raise RuntimeError(f"Failed to send to sentry: {result} {result.content}")
            print("...done", json.loads(result.content.decode()))


def builds_rm_old_cmd(args):
    current = get_all_current()
    all_releases = get_releases()
    max_build = max(x.version for x in all_releases)
    for release in get_releases():
        if release.key in current:
            print("Skipping {} as it is a current version".format(release))
        else:
            age = max_build - release.version
            if age > args['age']:
                if args['dry_run']:
                    print("Would remove build {}".format(release))
                else:
                    print("Removing build {}".format(release))
                    remove_release(release)
            else:
                print("Keeping build {}".format(release))


def builds_list_cmd(args):
    current = get_current_key(args)
    releases = get_releases()
    filter_branches = set(args['branch'].split(',') if args['branch'] is not None else [])
    print(RELEASE_FORMAT.format('Live', 'Branch', 'Version', 'Size', 'Hash'))
    for _, releases in itertools.groupby(releases, lambda r: r.branch):
        for release in releases:
            if len(filter_branches) == 0 or release.branch in filter_branches:
                print(
                    RELEASE_FORMAT.format(
                        ' -->' if release.key == current else '',
                        release.branch, release.version, sizeof_fmt(release.size), str(release.hash))
                )


def builds_history_cmd(args):
    from_time = args['from']
    until_time = args['until']
    if from_time is None and until_time is None:
        if confirm_action(
                'Do you want list all builds for {}? It might be an expensive operation:'.format(args['env'])):
            list_all_build_logs(args)
    else:
        list_period_build_logs(args, from_time, until_time)


def ads_cmd(args):
    dispatch_global('ads', args)


def ads_list_cmd(args):
    events = get_events(args)
    print(ADS_FORMAT.format('ID', 'Filters', 'HTML'))
    for ad in events['ads']:
        print(ADS_FORMAT.format(ad['id'], str(ad['filter']), ad['html']))


def ads_add_cmd(args):
    events = get_events(args)
    new_ad = {
        'html': args['html'],
        'filter': args['filter'].split(',') if len(args['filter']) > 0 else [],
        'id': max([x['id'] for x in events['ads']]) + 1 if len(events['ads']) > 0 else 0
    }
    if are_you_sure('add ad: {}'.format(ADS_FORMAT.format(new_ad['id'], str(new_ad['filter']), new_ad['html'])), args):
        events['ads'].append(new_ad)
        save_event_file(args, json.dumps(events))


def ads_remove_cmd(args):
    events = get_events(args)
    for i, ad in enumerate(events['ads']):
        if ad['id'] == args['id']:
            if args['force'] or \
                    are_you_sure('remove ad: {}'.format(ADS_FORMAT.format(ad['id'], str(ad['filter']), ad['html'])),
                                 args):
                del events['ads'][i]
                save_event_file(args, json.dumps(events))
            break


def ads_clear_cmd(args):
    events = get_events(args)
    if are_you_sure('clear all ads (count: {})'.format(len(events['ads'])), args):
        events['ads'] = []
        save_event_file(args, json.dumps(events))


def ads_edit_cmd(args):
    events = get_events(args)
    for i, ad in enumerate(events['ads']):
        if ad['id'] == args['id']:
            new_ad = {
                'id': ad['id'],
                'filter': (args['filter'].split(',') if len(args['filter']) > 0 else [])
                if args['filter'] is not None else ad['filter'],
                'html': args['html'] or ad['html']
            }
            print('{}\n{}\n{}'.format(ADS_FORMAT.format('Event', 'Filter(s)', 'HTML'),
                                      ADS_FORMAT.format('<FROM', str(ad['filter']), ad['html']),
                                      ADS_FORMAT.format('>TO', str(new_ad['filter']), new_ad['html'])))
            if are_you_sure('edit ad id: {}'.format(ad['id']), args):
                events['ads'][i] = new_ad
                save_event_file(args, json.dumps(events))
            break


def decorations_cmd(args):
    dispatch_global('decorations', args)


def decorations_list_cmd(args):
    events = get_events(args)
    print(DECORATION_FORMAT.format('Name', 'Filters', 'Regex', 'Decoration'))
    for dec in events['decorations']:
        print(DECORATION_FORMAT.format(dec['name'], str(dec['filter']), dec['regex'], json.dumps(dec['decoration'])))


def check_dec_args(regex, decoration):
    try:
        re.compile(regex)
    except re.error as re_err:
        raise RuntimeError(f"Unable to validate regex '{regex}' : {re_err}")
    try:
        decoration = json.loads(decoration)
    except json.decoder.JSONDecodeError as json_err:
        raise RuntimeError(f"Unable to parse decoration '{decoration}' : {json_err}")
    return regex, decoration


def decorations_add_cmd(args):
    events = get_events(args)
    if args['name'] in [d['name'] for d in events['decorations']]:
        raise RuntimeError(f'Duplicate decoration name {args["name"]}')
    regex, decoration = check_dec_args(args['regex'], args['decoration'])

    new_decoration = {
        'name': args['name'],
        'filter': args['filter'].split(',') if len(args['filter']) > 0 else [],
        'regex': regex,
        'decoration': decoration
    }
    if are_you_sure('add decoration: {}'.format(
            DECORATION_FORMAT.format(new_decoration['name'], str(new_decoration['filter']), new_decoration['regex'],
                                     json.dumps(new_decoration['decoration']))), args):
        events['decorations'].append(new_decoration)
        save_event_file(args, json.dumps(events))


def decorations_remove_cmd(args):
    events = get_events(args)
    for i, dec in enumerate(events['decorations']):
        if dec['name'] == args['name']:
            if args['force'] or \
                    are_you_sure('remove decoration: {}'.format(
                        DECORATION_FORMAT.format(dec['name'], str(dec['filter']), dec['regex'],
                                                 json.dumps(dec['decoration']))), args):
                del events['decorations'][i]
                save_event_file(args, json.dumps(events))
            break


def decorations_clear_cmd(args):
    events = get_events(args)
    if are_you_sure('clear all decorations (count: {})'.format(len(events['decorations'])), args):
        events['decorations'] = []
        save_event_file(args, json.dumps(events))


def decorations_edit_cmd(args):
    events = get_events(args)

    for i, dec in enumerate(events['decorations']):
        if dec['name'] == args['name']:
            regex, decoration = check_dec_args(args['regex'] or dec['regex'],
                                               args['decoration'] or json.dumps(dec['decoration']))
            new_dec = {
                'name': dec['name'],
                'filter': (args['filter'].split(',') if len(args['filter']) > 0 else [])
                if args['filter'] is not None else dec['filter'],
                'regex': regex,
                'decoration': decoration
            }
            print('{}\n{}\n{}'.format(DECORATION_FORMAT.format('Name', 'Filters', 'Regex', 'Decoration'),
                                      DECORATION_FORMAT.format('<FROM', str(dec['filter']), dec['regex'],
                                                               json.dumps(dec['decoration'])),
                                      DECORATION_FORMAT.format('>TO', str(new_dec['filter']), new_dec['regex'],
                                                               json.dumps(new_dec['decoration']))))
            if are_you_sure('edit decoration: {}'.format(dec['name']), args):
                events['decoration'][i] = new_dec
                save_event_file(args, json.dumps(events))
            break


def motd_cmd(args):
    dispatch_global('motd', args)


def motd_show_cmd(args):
    events = get_events(args)
    print('Current motd: "{}"'.format(events['motd']))


def motd_update_cmd(args):
    events = get_events(args)
    if are_you_sure('update motd from: {} to: {}'.format(events['motd'], args['message']), args):
        events['motd'] = args['message']
        save_event_file(args, json.dumps(events))


def motd_clear_cmd(args):
    events = get_events(args)
    if are_you_sure('clear current motd: {}'.format(events['motd']), args):
        events['motd'] = ''
        save_events(args, events)


def events_cmd(args):
    dispatch_global('events', args)


def events_to_raw_cmd(args):
    print(get_events_file(args))


def events_from_raw_cmd(args):
    raw = input()
    save_event_file(args, json.dumps(json.loads(raw)))


def events_to_file_cmd(args):
    with open(args['path'], mode='w') as f:
        f.write(get_events_file(args))


def events_from_file_cmd(args):
    with open(args['path'], mode='r') as f:
        new_contents = f.read()
        if are_you_sure('load from file {}', args):
            save_event_file(args, json.loads(new_contents))


def links_cmd(args):
    dispatch_global('links', args)


def links_name_cmd(args):
    link_from = args['from']
    if len(link_from) < 6:
        raise RuntimeError('from length must be at least 6')
    if len(args['to']) < 6:
        raise RuntimeError('to length must be at least 6')
    base_link = get_short_link(link_from)
    if not base_link:
        raise RuntimeError('Couldn\'t find base link {}'.format(link_from))
    base_link['prefix']['S'] = args['to'][0:6]
    base_link['unique_subhash']['S'] = args['to']
    base_link['stats']['M']['clicks']['N'] = '0'
    base_link['creation_ip']['S'] = '0.0.0.0'
    # It's us, so we don't care about "anonymizing" the time
    base_link['creation_date']['S'] = datetime.datetime.utcnow().isoformat()
    title = input('Link title: ')
    author = input('Author(s): ')
    if len(author) == 0:
        # We explicitly ignore author = . in the site code
        author = '.'
    project = input('Project: ')
    description = input('Description: ')
    base_link['named_metadata'] = {'M': {
        'title': {'S': title},
        'author': {'S': author},
        'project': {'S': project},
        'description': {'S': description}
    }}
    print('New link: {}'.format(pprint(base_link)))
    if are_you_sure('create new link named {}'.format(args['to']), args):
        put_short_link(base_link)


def links_update_cmd(args):
    link_to = args['to']
    link_from = args['from']
    if len(link_from) < 6:
        raise RuntimeError('from length must be at least 6')
    if len(args['to']) < 6:
        raise RuntimeError('to length must be at least 6')
    base_link = get_short_link(link_from)
    if not base_link:
        raise RuntimeError('Couldn\'t find base link {}'.format(link_from))
    link_to_update = get_short_link(link_to)
    if not link_to_update:
        raise RuntimeError('Couldn\'t find existing short link {}'.format(link_to))
    link_to_update['full_hash'] = base_link['full_hash']
    print('New link: {}'.format(pprint(link_to_update)))
    if are_you_sure('update link named {}'.format(link_to), args):
        put_short_link(link_to_update)


def links_maintenance_cmd(args):
    s3links, dblinks = list_short_links()
    s3keys_set = set()
    dbkeys_set = set()
    dbhashes_set = set()
    s3dirty_set = set()
    dbdirty_set = set()
    for page in s3links:
        for state in page['Contents']:
            if len(state['Key'][6:]) > 1:
                s3keys_set.add(state['Key'][6:])
    for page in dblinks:
        for item in page['Items']:
            unique_subhash = item['unique_subhash']['S']
            full_hash = item['full_hash']['S']
            dbkeys_set.add((unique_subhash, full_hash))
            dbhashes_set.add(full_hash)
    for dbkey in dbkeys_set:
        if dbkey[1] not in s3keys_set:
            dbdirty_set.add(dbkey)
    for s3key in s3keys_set:
        if s3key not in dbhashes_set:
            s3dirty_set.add(s3key)

    if are_you_sure('delete {} db elements:\n{}\n'.format(len(dbdirty_set), dbdirty_set), args) and not args['dry_run']:
        for item in dbdirty_set:
            print('Deleting {}'.format(item))
            delete_short_link(item)
    if are_you_sure('delete {} s3 elements:\n{}\n'.format(len(s3dirty_set), s3dirty_set), args) and not args['dry_run']:
        delete_s3_links(s3dirty_set)


def add_required_sub_parsers(parser, dest):
    sub_parser = parser.add_subparsers(dest=dest)
    sub_parser.required = True  # docs say I can pass required=True in add_subparsers but that seems to be a lie
    return sub_parser


def environment_cmd(args):
    dispatch_global('environment', args)


def environment_status_cmd(args):
    for asg in get_autoscaling_groups_for(args):
        group_name = asg['AutoScalingGroupName']
        instances = asg['DesiredCapacity']
        print(f"Found ASG {group_name} with desired instances {instances}")


def environment_start_cmd(args):
    for asg in get_autoscaling_groups_for(args):
        group_name = asg['AutoScalingGroupName']
        if asg['MinSize'] > 0:
            print(f"Skipping ASG {group_name} as it has a non-zero min size")
            continue
        prev = asg['DesiredCapacity']
        if prev:
            print(f"Skipping ASG {group_name} as it has non-zero desired capacity")
            continue
        print(f"Updating {group_name} to have desired capacity 1 (from {prev})")
        as_client.update_auto_scaling_group(AutoScalingGroupName=group_name, DesiredCapacity=1)


def environment_stop_cmd(args):
    if are_you_sure('stop environment', args):
        for asg in get_autoscaling_groups_for(args):
            group_name = asg['AutoScalingGroupName']
            if asg['MinSize'] > 0:
                print(f"Skipping ASG {group_name} as it has a non-zero min size")
                continue
            prev = asg['DesiredCapacity']
            if not prev:
                print(f"Skipping ASG {group_name} as it already zero desired capacity")
                continue
            print(f"Updating {group_name} to have desired capacity 0 (from {prev})")
            as_client.update_auto_scaling_group(AutoScalingGroupName=group_name, DesiredCapacity=0)


def main():
    parser = ArgumentParser(prog='ce', description='Administrate Compiler Explorer instances')
    parser.add_argument('--env', choices=['prod', 'beta', 'staging'], default='staging', metavar='ENV',
                        help='Select environment ENV')
    parser.add_argument('--mosh', action='store_true', help='Use mosh for interactive shells')
    parser.add_argument('--debug', action='store_true', help='Increase debug information')

    subparsers = add_required_sub_parsers(parser, 'command')
    subparsers.add_parser('admin')

    builder_parser = subparsers.add_parser('builder')
    builder_sub = add_required_sub_parsers(builder_parser, 'builder_sub')
    builder_sub.required = True
    builder_sub.add_parser('start')
    builder_sub.add_parser('stop')
    builder_sub.add_parser('status')
    builder_sub.add_parser('login')
    builder_exec = builder_sub.add_parser('exec')
    builder_exec.add_argument('remote_cmd', nargs='+', help='command to run on builder node')

    conan_parser = subparsers.add_parser('conan')
    conan_sub = add_required_sub_parsers(conan_parser, 'conan_sub')
    conan_sub.required = True
    conan_sub.add_parser('reload')
    conan_sub.add_parser('login')
    conan_exec = conan_sub.add_parser('exec')
    conan_exec.add_argument('remote_cmd', nargs='+', help='command to run on conan node')

    builds_parser = subparsers.add_parser('builds')
    builds_sub = add_required_sub_parsers(builds_parser, 'builds_sub')
    list_parser = builds_sub.add_parser('list')
    list_parser.add_argument('-b', '--branch', type=str, help='show only selected branches')
    builds_sub.add_parser('current')
    set_current = builds_sub.add_parser('set_current')
    set_current.add_argument('version', help='version to set')
    set_current.add_argument('--branch', help='if version == latest, branch to get latest version from', type=str,
                             default='')
    set_current.add_argument('--raw', action='store_true', help='Set a raw path for a version')
    expire = builds_sub.add_parser('rm_old', help='delete old versions')
    expire.add_argument('age', help='keep the most recent AGE builds (as well as current builds)', metavar='AGE',
                        type=int)
    expire.add_argument('--dry-run', help='dry run only', action='store_true')
    history_parser = builds_sub.add_parser('history')
    history_parser.add_argument('--from', help='timestamp filter')
    history_parser.add_argument('--until', help='timestamp filter')

    instances_parser = subparsers.add_parser('instances')
    instances_sub = add_required_sub_parsers(instances_parser, 'instances_sub')
    instances_sub.add_parser('status')
    instances_sub.add_parser('restart_one')
    instances_sub.add_parser('login')
    exec_all_parser = instances_sub.add_parser('exec_all')
    exec_all_parser.add_argument('remote_cmd', nargs='+', help='command to run on all nodes')
    instances_sub.add_parser('start')
    instances_sub.add_parser('stop')
    instances_restart_parser = instances_sub.add_parser('restart')
    instances_restart_parser.add_argument('--motd', type=str, default='Site is being updated')

    ads_parser = subparsers.add_parser('ads')
    ads_sub = add_required_sub_parsers(ads_parser, 'ads_sub')
    ads_sub.add_parser('list')
    ads_add_parser = ads_sub.add_parser('add')
    ads_add_parser.add_argument('html', type=str, help='message contents')
    ads_add_parser.add_argument('--filter', type=str, help='target languages', default="")
    ads_remove_parser = ads_sub.add_parser('remove')
    ads_remove_parser.add_argument('id', type=int, help='remove ad by id')
    ads_remove_parser.add_argument('-f', '--force', action='store_true', default=False, help='no confirmation needed')
    ads_sub.add_parser('clear')
    ads_edit_parser = ads_sub.add_parser('edit')
    ads_edit_parser.add_argument('id', type=int, help='event to edit')
    ads_edit_parser.add_argument('--html', type=str, help='new ad contents')
    ads_edit_parser.add_argument('--filter', type=str, help='new ad filter(s)')

    decorations_parser = subparsers.add_parser('decorations')
    decorations_sub = add_required_sub_parsers(decorations_parser, 'decorations_sub')
    decorations_sub.add_parser('list')
    decorations_add_parser = decorations_sub.add_parser('add')
    decorations_add_parser.add_argument('name', type=str, help='name')
    decorations_add_parser.add_argument('regex', type=str, help='regex')
    decorations_add_parser.add_argument('decoration', type=str, help='decoration (JSON format)')
    decorations_add_parser.add_argument('--filter', type=str, help='target languages', default="")
    decorations_remove_parser = decorations_sub.add_parser('remove')
    decorations_remove_parser.add_argument('name', type=str, help='remove decoration by name')
    decorations_remove_parser.add_argument('-f', '--force', action='store_true', default=False,
                                           help='no confirmation needed')
    decorations_sub.add_parser('clear')
    decorations_edit_parser = decorations_sub.add_parser('edit')
    decorations_edit_parser.add_argument('name', type=str, help='decoration to edit')
    decorations_edit_parser.add_argument('--regex', type=str, help='new regex')
    decorations_edit_parser.add_argument('--decoration', type=str, help='new decoration')
    decorations_edit_parser.add_argument('--filter', type=str, help='new decoration filter(s)')

    motd_parser = subparsers.add_parser('motd')
    motd_sub = add_required_sub_parsers(motd_parser, 'motd_sub')
    motd_sub.add_parser('show')
    motd_update_parser = motd_sub.add_parser('update')
    motd_update_parser.add_argument('message', type=str, help='new motd')
    motd_sub.add_parser('clear')

    events_parser = subparsers.add_parser('events')
    events_sub = add_required_sub_parsers(events_parser, 'events_sub')
    events_from_file_parser = events_sub.add_parser('from_file')
    events_from_file_parser.add_argument('path', type=str, help='location of file to load from')
    events_to_file_parser = events_sub.add_parser('to_file')
    events_to_file_parser.add_argument('path', type=str, help='location of file to save to')
    events_sub.add_parser('from_raw')
    events_sub.add_parser('to_raw')

    links_parser = subparsers.add_parser('links')
    links_sub = add_required_sub_parsers(links_parser, 'links_sub')
    links_name_parser = links_sub.add_parser('name')
    links_name_parser.add_argument('from', type=str, help='unique subhash to base the link from')
    links_name_parser.add_argument('to', type=str, help='name of the link')
    links_update_parser = links_sub.add_parser('update')
    links_update_parser.add_argument('from', type=str, help='short link to copy from')
    links_update_parser.add_argument('to', type=str, help='named short link to update')
    links_maintenance_parser = links_sub.add_parser('maintenance')
    links_maintenance_parser.add_argument('--dry-run', action='store_true', help='dry run')

    env_parser = subparsers.add_parser('environment')
    env_sub = add_required_sub_parsers(env_parser, 'environment_sub')
    env_sub.add_parser('start')
    env_sub.add_parser('stop')
    env_sub.add_parser('status')

    kwargs = vars(parser.parse_args())
    if kwargs['debug']:
        logging.basicConfig(level=logging.DEBUG)
    else:
        logging.basicConfig(level=logging.INFO)
        logging.getLogger('boto3').setLevel(logging.WARNING)
        logging.getLogger('botocore').setLevel(logging.WARNING)
    cmd = kwargs.pop('command')
    if cmd not in ('admin', 'builder', 'links'):
        if cmd != 'events' or not kwargs['events_sub'].endswith('_raw'):
            print("Running in {}".format(kwargs['env']))
    try:
        globals()[cmd + "_cmd"](kwargs)
    except (KeyboardInterrupt, SystemExit):
        # print empty line so terminal prompt doesn't end up on the end of some
        # of our own program output
        print()
