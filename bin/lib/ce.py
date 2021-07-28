#!/usr/bin/env python3
# coding=utf-8

import datetime
import itertools
import json
import logging
import os
import re
import shlex
import socket
import subprocess
import sys
import tempfile
import time
from collections import defaultdict
from pathlib import Path
from pprint import pformat
from tempfile import TemporaryDirectory
from typing import TextIO, Optional, Dict, Sequence, Set, List, Union

import click
import requests

from lib.amazon import target_group_arn_for, get_autoscaling_group, get_releases, find_release, get_current_key, \
    set_current_key, as_client, release_for, find_latest_release, get_all_current, remove_release, get_events_file, \
    save_event_file, get_short_link, put_short_link, delete_short_link, list_short_links, delete_s3_links, \
    get_autoscaling_groups_for, download_release_file, download_release_fileobj, log_new_build, list_all_build_logs, \
    list_period_build_logs, get_ssm_param, get_tools_releases
from lib.cdn import DeploymentJob
from lib.env import Environment, Config
from lib.instance import ConanInstance, AdminInstance, BuilderInstance, Instance, print_instances
from lib.releases import Version, Release, Hash, VersionSource
from lib.ssh import run_remote_shell, exec_remote, exec_remote_all, exec_remote_to_stdout

CE_TOOLS_LOCATION = '/opt/compiler-explorer/demanglers/'

logger = logging.getLogger('ce')

ADS_FORMAT = '{: <5} {: <10} {: <20}'
DECORATION_FORMAT = '{: <10} {: <15} {: <30} {: <50}'


@click.group()
@click.option("--env", type=click.Choice([env.value for env in Environment]),
              default=Environment.STAGING.value, metavar='ENV',
              help='Select environment ENV')
@click.option("--debug/--no-debug", help='Turn on debugging')
@click.pass_context
def cli(ctx: click.Context, env: str, debug: bool):
    ctx.obj = Config(env=Environment(env))
    if debug:
        logging.basicConfig(level=logging.DEBUG)
    else:
        logging.basicConfig(level=logging.INFO)
        logging.getLogger('boto3').setLevel(logging.WARNING)
        logging.getLogger('botocore').setLevel(logging.WARNING)
        logging.getLogger('paramiko').setLevel(logging.WARNING)


def pick_instance(cfg: Config):
    elb_instances = Instance.elb_instances(target_group_arn_for(cfg))
    if len(elb_instances) == 1:
        return elb_instances[0]
    while True:
        print_instances(elb_instances, number=True)
        inst = input('Which instance? ')
        try:
            return elb_instances[int(inst)]
        except (ValueError, IndexError):
            pass


def pick_instances(cfg: Config):
    return Instance.elb_instances(target_group_arn_for(cfg))


def sizeof_fmt(num, suffix='B'):
    for unit in ['', 'Ki', 'Mi', 'Gi', 'Ti', 'Pi', 'Ei', 'Zi']:
        if abs(num) < 1024.0:
            return "%3.1f%s%s" % (num, unit, suffix)
        num /= 1024.0
    return "%.1f%s%s" % (num, 'Yi', suffix)


def describe_current_release(cfg: Config):
    current = get_current_key(cfg)
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
        autoscale = instance.describe_autoscale()
        if not autoscale:
            logger.error("Instance is not longer in an ASG: stopping")
            return
        cur_state = autoscale['LifecycleState']
        logger.debug("State is %s", cur_state)
        if cur_state == state:
            logger.info("...done")
            return
        time.sleep(5)


def get_events(cfg: Config):
    events = json.loads(get_events_file(cfg))
    if 'ads' not in events:
        events['ads'] = []
    if 'decorations' not in events:
        events['decorations'] = []
    if 'motd' not in events:
        events['motd'] = ''
    return events


def save_events(cfg: Config, events):
    save_event_file(cfg, json.dumps(events))


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


def are_you_sure(name: str, cfg: Optional[Config] = None) -> bool:
    env_name = cfg.env.value if cfg else 'global'
    while True:
        typed = input(
            f'Confirm operation: "{name}" in env {env_name}\nType the name of the environment to proceed: ')
        if typed == env_name:
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


def restart_one_instance(as_group_name: str, instance: Instance, modified_groups: Dict[str, int]):
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


@cli.group()
def admin():
    """
    Administrative instance commands
    """


@admin.command(name='login')
@click.option('--mosh/--ssh', help='Use mosh to connect')
def admin_login(mosh: bool):
    """Log in to the administrative instance."""
    run_remote_shell(AdminInstance.instance(), use_mosh=mosh)


@admin.command(name='exec')
@click.argument('command', nargs=-1)
def admin_exec(command: List[str]):
    """Execute a command on the admin instance."""
    exec_remote_to_stdout(AdminInstance.instance(), command)


@admin.command(name='info')
def admin_info():
    """Shows address of the admin instance."""
    click.echo(f"Admin instance is at: {AdminInstance.instance().address}")


@admin.command(name='gotty')
def admin_gotty():
    """Runs gotty on the admin instance to allow external viewers to watch the tmux session."""
    instance = AdminInstance.instance()
    port = 5986  # happens to be open in the firewall...
    click.echo(f"Will be PUBLICALLY accessible at: http://{instance.address}:{port}...")
    exec_remote_to_stdout(instance, [
        "./gotty", "--port", str(port), "tmux", "attach"
    ])


@cli.group()
def conan():
    """Conan instance management commands."""


@conan.command(name='login')
def conan_login():
    """Log in to the conan instance."""
    instance = ConanInstance.instance()
    run_remote_shell(instance)


@conan.command(name='exec')
@click.argument('remote_cmd', required=True, nargs=-1)
def conan_exec(remote_cmd: Sequence[str]):
    """Execute the REMOTE_CMD on the conan instance."""
    instance = ConanInstance.instance()
    exec_remote_to_stdout(instance, remote_cmd)


@conan.command(name='restart')
def conan_restart():
    """Restart the conan instance."""
    instance = ConanInstance.instance()
    exec_remote(instance, ["sudo", "service", "ce-conan", "restart"])


@conan.command(name='reloadwww')
def conan_reloadwww():
    """Reload the conan web."""
    instance = ConanInstance.instance()
    exec_remote(instance, ["sudo", "git", "-C", "/home/ubuntu/ceconan/conanproxy", "pull"])


@cli.group()
def builder():
    """Builder machine manipulation commands."""


@builder.command(name='login')
def builder_login():
    """Log in to the builder machine."""
    instance = BuilderInstance.instance()
    run_remote_shell(instance)


@builder.command(name='exec')
@click.argument('remote_cmd', required=True, nargs=-1)
def builder_exec(remote_cmd: Sequence[str]):
    """Execute REMOTE_CMD on the builder instance."""
    instance = BuilderInstance.instance()
    exec_remote_to_stdout(instance, remote_cmd)


@builder.command(name='start')
def builder_start():
    """Start the builder instance."""
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
        except:
            print("Still waiting for SSH")
        time.sleep(1)
    else:
        raise RuntimeError("Unable to get SSH access")
    res = exec_remote(instance,
                      ["bash", "-c", "cd infra && git pull && sudo ./setup-builder-startup.sh"], True)
    print(res)
    for _ in range(30):
        try:
            r = exec_remote(instance, ["sudo", "systemctl", "status", "docker"])
            if "active (running)" in r:
                break
        except:
            print("Still waiting for Docker")
        time.sleep(1)
    else:
        raise RuntimeError("Unable to launch docker")
    print("Builder started OK")


@builder.command(name='stop')
def builder_stop():
    """Stop the builder instance."""
    BuilderInstance.instance().stop()


@builder.command(name='status')
def builder_status():
    """Get the builder status (running or otherwise)."""
    print("Builder status: {}".format(BuilderInstance.instance().status()))


@cli.group()
def instances():
    """Instance management commands."""


@instances.command(name='exec_all')
@click.pass_obj
@click.argument('remote_cmd', required=True, nargs=-1)
def instances_exec_all(cfg: Config, remote_cmd: Sequence[str]):
    """Execute REMOTE_CMD on all the instances."""
    escaped = shlex.join(remote_cmd)
    if not are_you_sure(f'exec command {escaped} in all instances', cfg):
        return

    print("Running '{}' on all instances".format(escaped))
    exec_remote_all(pick_instances(cfg), remote_cmd)


@instances.command(name='login')
@click.pass_obj
def instances_login(cfg: Config):
    """Log in to one of the instances."""
    instance = pick_instance(cfg)
    run_remote_shell(instance)


@instances.command(name='restart_one')
@click.pass_obj
def instances_restart_one(cfg: Config):
    """Restart one of the instances."""
    instance = pick_instance(cfg)
    as_instance_status = instance.describe_autoscale()
    if not as_instance_status:
        logger.error("Failed restarting %s - was not in ASG", instance)
        return
    as_group_name = as_instance_status['AutoScalingGroupName']
    modified_groups: Dict[str, int] = {}
    try:
        restart_one_instance(as_group_name, instance, modified_groups)
    except RuntimeError as e:
        logger.error("Failed restarting %s - skipping: %s", instance, e)


@instances.command(name='start')
@click.pass_obj
def instances_start(cfg: Config):
    """Start up the instances."""
    print("Starting version %s", describe_current_release(cfg))
    exec_remote_all(pick_instances(cfg), ['sudo', 'systemctl', 'start', 'compiler-explorer'])


@instances.command(name='stop')
@click.pass_obj
def instances_stop(cfg: Config):
    """Stop the instances."""
    if cfg.env == Environment.PROD:
        print('Operation aborted. This would bring down the site')
        print('If you know what you are doing, edit the code in bin/lib/ce.py, function instances_stop_cmd')
    elif are_you_sure('stop all instances', cfg):
        exec_remote_all(pick_instances(cfg), ['sudo', 'systemctl', 'stop', 'compiler-explorer'])


@instances.command(name='restart')
@click.option('--motd', type=str, default='Site is being updated',
              help='Set the message of the day used during update', show_default=True)
@click.pass_obj
def instances_restart(cfg: Config, motd: str):
    """Restart the instances, picking up new code."""
    if not are_you_sure('restart all instances with version {}'.format(describe_current_release(cfg)), cfg):
        return
    # Store old motd
    begin_time = datetime.datetime.now()
    events = get_events(cfg)
    old_motd = events['motd']
    events['motd'] = old_motd if motd == '' else motd
    save_events(cfg, events)
    modified_groups: Dict[str, int] = {}
    failed = False
    to_restart = pick_instances(cfg)

    for index, instance in enumerate(to_restart):
        logger.info("Restarting %s (%d of %d)...", instance, index + 1, len(to_restart))
        as_instance_status = instance.describe_autoscale()
        if not as_instance_status:
            logger.warning("Skipping %s as it is no longer in the ASG", instance)
            continue
        as_group_name = as_instance_status['AutoScalingGroupName']
        if as_instance_status['LifecycleState'] != 'InService':
            logger.warning("Skipping %s as it is not InService (%s)", instance, as_instance_status)
            continue

        try:
            restart_one_instance(as_group_name, instance, modified_groups)
        except RuntimeError as e:
            logger.error("Failed restarting %s - skipping: %s", instance, e)
            failed = True
            # TODO, what here?

    for group, desired in iter(modified_groups.items()):
        logger.info("Putting desired instances for %s back to %d", group, desired)
        as_client.update_auto_scaling_group(AutoScalingGroupName=group, DesiredCapacity=desired)
    # Events might have changed, re-fetch
    events = get_events(cfg)
    events['motd'] = old_motd
    save_events(cfg, events)
    end_time = datetime.datetime.now()
    delta_time = end_time - begin_time
    print(f'Instances restarted in {delta_time.total_seconds()} seconds')
    sys.exit(1 if failed else 0)


@instances.command(name='status')
@click.pass_obj
def instances_status(cfg: Config):
    """Get the status of the instances."""
    print_instances(Instance.elb_instances(target_group_arn_for(cfg)), number=False)


@cli.group()
def builds():
    """Build manipulation commands."""


@builds.command(name="current")
@click.pass_obj
def builds_current(cfg: Config):
    """Print the current release."""
    print(describe_current_release(cfg))


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


@builds.command(name='set_current')
@click.pass_obj
@click.option('--branch', help='if version == latest, branch to get latest version from')
@click.option('--raw/--no-raw', help='Set a raw path for a version')
@click.argument('version')
def builds_set_current(cfg: Config, branch: Optional[str], version: str, raw: bool):
    """Set the current version to VERSION for this environment.

    If VERSION is "latest" then the latest version (optionally filtered by --branch), is set.
    """
    to_set = None
    release = None
    if raw:
        to_set = version
    else:
        setting_latest = version == 'latest'
        release = find_latest_release(branch) if setting_latest else find_release(
            Version.from_string(version))
        if not release:
            print("Unable to find version " + version)
            if setting_latest and branch != '':
                print('Branch {} has no available versions (Bad branch/No image yet built)'.format(branch))
        elif are_you_sure('change current version to {}'.format(release.key), cfg) and confirm_branch(release):
            print(f'Found release {release}')
            to_set = release.key
    if to_set is not None:
        log_new_build(cfg, to_set)
        if release and release.static_key:
            if not deploy_staticfiles(release):
                print("...aborted due to deployment failure!")
                sys.exit(1)
        else:
            old_deploy_staticfiles(branch, to_set)
        set_current_key(cfg, to_set)
        if release:
            print("Marking as a release in sentry...")
            token = get_ssm_param("/compiler-explorer/sentryAuthToken")
            result = requests.post(
                f"https://sentry.io/api/0/organizations/compiler-explorer/releases/{release.version}/deploys/",
                data=dict(environment=cfg.env.value),
                headers=dict(Authorization=f'Bearer {token}'))
            if not result.ok:
                raise RuntimeError(f"Failed to send to sentry: {result} {result.content.decode('utf-8')}")
            print("...done", json.loads(result.content.decode()))


@builds.command(name="rm_old")
@click.option('--dry-run/--no-dry-run', help='dry run only')
@click.argument('max_age', type=int)
def builds_rm_old(dry_run: bool, max_age: int):
    """Remove all but the last MAX_AGE builds."""
    current = get_all_current()
    max_builds: Dict[str, int] = defaultdict(int)
    for release in get_releases():
        max_builds[release.version.source] = max(release.version.number, max_builds[release.version.source])
    for release in get_releases():
        if release.key in current:
            print("Skipping {} as it is a current version".format(release))
        else:
            age = max_builds[release.version.source] - release.version.number
            if age > max_age:
                if dry_run:
                    print("Would remove build {}".format(release))
                else:
                    print("Removing build {}".format(release))
                    remove_release(release)
            else:
                print("Keeping build {}".format(release))


@builds.command(name='list')
@click.pass_obj
@click.option('-b', '--branch', type=str, help='show only BRANCH (may be specified more than once)',
              metavar='BRANCH', multiple=True)
def builds_list(cfg: Config, branch: Sequence[str]):
    """List available builds.

    The --> indicates the build currently deployed in this environment."""
    current = get_current_key(cfg) or ''
    releases = get_releases()
    display_releases(current, set(branch), releases)


def display_releases(current: Union[str, Hash], filter_branches: Set[str], releases: List[Release]):
    max_branch_len = max(10, max((len(release.branch) for release in releases), default=10))
    release_format = '{: <5} {: <' + str(max_branch_len) + '} {: <10} {: <10} {: <14}'
    click.echo(release_format.format('Live', 'Branch', 'Version', 'Size', 'Hash'))
    for _, grouped_releases in itertools.groupby(releases, lambda r: r.branch):
        for release in grouped_releases:
            if not filter_branches or release.branch in filter_branches:
                click.echo(
                    release_format.format(
                        ' -->' if (release.key == current or release.hash == current) else '',
                        release.branch, str(release.version), sizeof_fmt(release.size), str(release.hash))
                )


@builds.command(name='history')
@click.option('--from', 'from_time')
@click.option('--until', 'until_time')
@click.pass_obj
def builds_history(cfg: Config, from_time: Optional[str], until_time: Optional[str]):
    """Show the history of current versions for this environment."""
    if from_time is None and until_time is None:
        if confirm_action(
                'Do you want list all builds for {}? It might be an expensive operation:'.format(cfg.env.value)):
            list_all_build_logs(cfg)
    else:
        list_period_build_logs(cfg, from_time, until_time)


@cli.group()
def ads():
    """Community advert manipulation features."""


@ads.command(name='list')
@click.pass_obj
def ads_list(cfg: Config):
    """List the existing community adverts."""
    events = get_events(cfg)
    print(ADS_FORMAT.format('ID', 'Filters', 'HTML'))
    for ad in events['ads']:
        print(ADS_FORMAT.format(ad['id'], str(ad['filter']), ad['html']))


@ads.command(name='add')
@click.pass_obj
@click.option("--filter", 'lang_filter', help='Filter to these languages (default all)', multiple=True)
@click.argument("html")
def ads_add(cfg: Config, lang_filter: Sequence[str], html: str):
    """Add a community advert with HTML."""
    events = get_events(cfg)
    new_ad = {
        'html': html,
        'filter': lang_filter,
        'id': max([x['id'] for x in events['ads']]) + 1 if len(events['ads']) > 0 else 0
    }
    if are_you_sure('add ad: {}'.format(ADS_FORMAT.format(new_ad['id'], str(new_ad['filter']), new_ad['html'])), cfg):
        events['ads'].append(new_ad)
        save_event_file(cfg, json.dumps(events))


@ads.command(name='remove')
@click.pass_obj
@click.option('--force/--no-force', help='Force remove (no confirmation)')
@click.argument('ad_id', type=int)
def ads_remove(cfg: Config, ad_id: int, force: bool):
    """Remove community ad number AD_ID."""
    events = get_events(cfg)
    for i, ad in enumerate(events['ads']):
        if ad['id'] == ad_id:
            if force or \
                    are_you_sure('remove ad: {}'.format(ADS_FORMAT.format(ad['id'], str(ad['filter']), ad['html'])),
                                 cfg):
                del events['ads'][i]
                save_event_file(cfg, json.dumps(events))
            break


@ads.command(name='clear')
@click.pass_obj
def ads_clear(cfg: Config):
    """Clear all community ads."""
    events = get_events(cfg)
    if are_you_sure('clear all ads (count: {})'.format(len(events['ads'])), cfg):
        events['ads'] = []
        save_event_file(cfg, json.dumps(events))


@ads.command(name='edit')
@click.option("--filter", 'lang_filter', help='Change filters to these languages', multiple=True)
@click.option("--html", help='Change html to HTML')
@click.argument('ad_id', type=int)
@click.pass_obj
def ads_edit(cfg: Config, ad_id: int, html: str, lang_filter: Sequence[str]):
    """Edit community ad AD_ID."""
    events = get_events(cfg)
    for i, ad in enumerate(events['ads']):
        if ad['id'] == ad_id:
            new_ad = {
                'id': ad['id'],
                'filter': lang_filter or ad['filter'],
                'html': html or ad['html']
            }
            print('{}\n{}\n{}'.format(ADS_FORMAT.format('Event', 'Filter(s)', 'HTML'),
                                      ADS_FORMAT.format('<FROM', str(ad['filter']), ad['html']),
                                      ADS_FORMAT.format('>TO', str(new_ad['filter']), new_ad['html'])))
            if are_you_sure('edit ad id: {}'.format(ad['id']), cfg):
                events['ads'][i] = new_ad
                save_event_file(cfg, json.dumps(events))
            break


@cli.group()
def decorations():
    """Manage the decorations (ok, Easter Eggs)."""


@decorations.command(name='list')
@click.pass_obj
def decorations_list(cfg: Config):
    events = get_events(cfg)
    print(DECORATION_FORMAT.format('Name', 'Filters', 'Regex', 'Decoration'))
    for dec in events['decorations']:
        print(DECORATION_FORMAT.format(dec['name'], str(dec['filter']), dec['regex'], json.dumps(dec['decoration'])))


def check_dec_args(regex, decoration):
    try:
        re.compile(regex)
    except re.error as re_err:
        raise RuntimeError(f"Unable to validate regex '{regex}' : {re_err}") from re_err
    try:
        decoration = json.loads(decoration)
    except json.decoder.JSONDecodeError as json_err:
        raise RuntimeError(f"Unable to parse decoration '{decoration}' : {json_err}") from json_err
    return regex, decoration


@decorations.command(name='add')
@click.pass_obj
@click.option('--filter', 'lang_filter', help='filter for this language', multiple=True)
@click.argument('name')
@click.argument('regex')
@click.argument('decoration')
def decorations_add(cfg: Config, lang_filter: Sequence[str], name: str, regex: str, decoration: str):
    """
    Add a decoration called NAME matching REGEX resulting in json DECORATION.
    """
    events = get_events(cfg)
    if name in [d['name'] for d in events['decorations']]:
        raise RuntimeError(f'Duplicate decoration name {name}')
    regex, decoration = check_dec_args(regex, decoration)

    new_decoration = {
        'name': name,
        'filter': lang_filter,
        'regex': regex,
        'decoration': decoration
    }
    if are_you_sure('add decoration: {}'.format(
            DECORATION_FORMAT.format(new_decoration['name'], str(new_decoration['filter']), new_decoration['regex'],
                                     json.dumps(new_decoration['decoration']))), cfg):
        events['decorations'].append(new_decoration)
        save_event_file(cfg, json.dumps(events))


@decorations.command(name='remove')
@click.pass_obj
@click.option("--force/--no-force", help="force without confirmation")
@click.argument('name')
def decorations_remove(cfg: Config, name: str, force: bool):
    """Remove a decoration."""
    events = get_events(cfg)
    for i, dec in enumerate(events['decorations']):
        if dec['name'] == name:
            if force or \
                    are_you_sure('remove decoration: {}'.format(
                        DECORATION_FORMAT.format(dec['name'], str(dec['filter']), dec['regex'],
                                                 json.dumps(dec['decoration']))), cfg):
                del events['decorations'][i]
                save_event_file(cfg, json.dumps(events))
            break


@decorations.command(name='clear')
@click.pass_obj
def decorations_clear(cfg: Config):
    """Clear all decorations."""
    events = get_events(cfg)
    if are_you_sure('clear all decorations (count: {})'.format(len(events['decorations'])), cfg):
        events['decorations'] = []
        save_event_file(cfg, json.dumps(events))


@decorations.command(name='edit')
@click.pass_obj
@click.option('--filter', 'lang_filter', help='filter for this language', multiple=True)
@click.option('--regex', help='match REGEX')
@click.option('--decoration', help='evaluate to DECORATION (json syntax)')
@click.argument('name')
def decorations_edit(cfg: Config, lang_filter: Sequence[str], name: str, regex: str, decoration: str):
    """Edit existing decoration NAME."""
    events = get_events(cfg)

    for i, dec in enumerate(events['decorations']):
        if dec['name'] == name:
            regex, decoration = check_dec_args(regex or dec['regex'],
                                               decoration or json.dumps(dec['decoration']))
            new_dec = {
                'name': dec['name'],
                'filter': lang_filter or dec['filter'],
                'regex': regex,
                'decoration': decoration
            }
            print('{}\n{}\n{}'.format(DECORATION_FORMAT.format('Name', 'Filters', 'Regex', 'Decoration'),
                                      DECORATION_FORMAT.format('<FROM', str(dec['filter']), dec['regex'],
                                                               json.dumps(dec['decoration'])),
                                      DECORATION_FORMAT.format('>TO', str(new_dec['filter']), new_dec['regex'],
                                                               json.dumps(new_dec['decoration']))))
            if are_you_sure('edit decoration: {}'.format(dec['name']), cfg):
                events['decoration'][i] = new_dec
                save_event_file(cfg, json.dumps(events))
            break


@cli.group(name='motd')
def motd_group():
    """Message of the day manipulation functions."""


@motd_group.command(name='show')
@click.pass_obj
def motd_show(cfg: Config):
    """Prints the message of the day."""
    events = get_events(cfg)
    print('Current motd: "{}"'.format(events['motd']))


@motd_group.command(name='update')
@click.argument('message', type=str)
@click.pass_obj
def motd_update(cfg: Config, message: str):
    """Updates the message of the day to MESSAGE."""
    events = get_events(cfg)
    if are_you_sure('update motd from: {} to: {}'.format(events['motd'], message), cfg):
        events['motd'] = message
        save_event_file(cfg, json.dumps(events))


@motd_group.command(name='clear')
@click.pass_obj
def motd_clear(cfg: Config):
    """Clears the message of the day."""
    events = get_events(cfg)
    if are_you_sure('clear current motd: {}'.format(events['motd']), cfg):
        events['motd'] = ''
        save_events(cfg, events)


@cli.group(name='events')
def events_group():
    """Low-level manipulation of ads and events."""


@events_group.command(name='to_raw')
@click.pass_obj
def events_to_raw(cfg: Config):
    """Dumps the events file as raw JSON."""
    print(get_events_file(cfg))


@events_group.command(name='from_raw')
@click.pass_obj
def events_from_raw(cfg: Config):
    """Reloads the events file as raw JSON from console input."""
    raw = input()
    save_event_file(cfg, json.dumps(json.loads(raw)))


@events_group.command(name='to_file')
@click.argument("file", type=click.File(mode='w'))
@click.pass_obj
def events_to_file(cfg: Config, file: TextIO):
    """Saves the raw events file as FILE."""
    file.write(get_events_file(cfg))


@events_group.command(name='from_file')
@click.argument("file", type=click.File(mode='r'))
@click.pass_obj
def events_from_file(cfg: Config, file: TextIO):
    """Reads FILE and replaces the events file with its contents."""
    new_contents = json.loads(file.read())
    if are_you_sure(f'load events from file {file.name}', cfg):
        save_event_file(cfg, new_contents)


@cli.group()
def link():
    """Link manipulation commands."""


@link.command(name='name')
@click.argument("link_from")
@click.argument("link_to")
def links_name(link_from: str, link_to: str):
    """Give link LINK_FROM a new name LINK_TO."""
    if len(link_from) < 6:
        raise RuntimeError('from length must be at least 6')
    if len(link_to) < 6:
        raise RuntimeError('to length must be at least 6')
    base_link = get_short_link(link_from)
    if not base_link:
        raise RuntimeError('Couldn\'t find base link {}'.format(link_from))
    base_link['prefix']['S'] = link_to[0:6]
    base_link['unique_subhash']['S'] = link_to
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
    print('New link: {}'.format(pformat(base_link)))
    if are_you_sure('create new link named {}'.format(link_to)):
        put_short_link(base_link)


@link.command(name='update')
@click.argument("link_from")
@click.argument("link_to")
def links_update(link_from: str, link_to: str):
    """Update a link; point LINK_FROM to existing LINK_TO."""
    if len(link_from) < 6:
        raise RuntimeError('from length must be at least 6')
    if len(link_to) < 6:
        raise RuntimeError('to length must be at least 6')
    base_link = get_short_link(link_from)
    if not base_link:
        raise RuntimeError('Couldn\'t find base link {}'.format(link_from))
    link_to_update = get_short_link(link_to)
    if not link_to_update:
        raise RuntimeError('Couldn\'t find existing short link {}'.format(link_to))
    link_to_update['full_hash'] = base_link['full_hash']
    print('New link: {}'.format(pformat(link_to_update)))
    if are_you_sure('update link named {}'.format(link_to)):
        put_short_link(link_to_update)


@link.command(name='maintenance')
@click.option("--dry-run/--no-dry-run", help="dry run only")
def links_maintenance(dry_run: bool):
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

    if are_you_sure('delete {} db elements:\n{}\n'.format(len(dbdirty_set), dbdirty_set)) and not dry_run:
        for item in dbdirty_set:
            print('Deleting {}'.format(item))
            delete_short_link(item)
    if are_you_sure('delete {} s3 elements:\n{}\n'.format(len(s3dirty_set), s3dirty_set)) and not dry_run:
        delete_s3_links(s3dirty_set)


def add_required_sub_parsers(parser, dest):
    sub_parser = parser.add_subparsers(dest=dest)
    sub_parser.required = True  # docs say I can pass required=True in add_subparsers but that seems to be a lie
    return sub_parser


@cli.group()
def environment():
    """Environment manipulation commands."""


@environment.command(name='status')
@click.pass_obj
def environment_status(cfg: Config):
    """Gets the status of an environment."""
    for asg in get_autoscaling_groups_for(cfg):
        print(f"Found ASG {asg['AutoScalingGroupName']} with desired instances {asg['DesiredCapacity']}")


@environment.command(name='start')
@click.pass_obj
def environment_start(cfg: Config):
    """Starts up an environment by ensure its ASGs have capacity."""
    for asg in get_autoscaling_groups_for(cfg):
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


@environment.command(name='refresh')
@click.option("--min-healthy-percent", type=click.IntRange(min=0, max=100), metavar='PERCENT',
              help='While updating, ensure at least PERCENT are healthy', default=75, show_default=True)
@click.pass_obj
def environment_refresh(cfg: Config, min_healthy_percent: int):
    """Refreshes an environment.

    This replaces all the instances in the ASGs associated with an environment with
    new instances (with the latest code), while ensuring there are some left to handle
    the traffic while we update."""
    # TODO motd like the restart
    for asg in get_autoscaling_groups_for(cfg):
        group_name = asg['AutoScalingGroupName']
        if asg['DesiredCapacity'] == 0:
            print(f"Skipping ASG {group_name} as it has a zero size")
            continue
        describe_state = as_client.describe_instance_refreshes(
            AutoScalingGroupName=group_name
        )
        existing_refreshes = [x for x in describe_state['InstanceRefreshes'] if
                              x['Status'] in ('Pending', 'InProgress')]
        if existing_refreshes:
            refresh_id = existing_refreshes[0]['InstanceRefreshId']
            print(f"  Found existing refresh {refresh_id} for {group_name}")
        else:
            if not are_you_sure(f'Refresh instances in {group_name} with version {describe_current_release(cfg)}',
                                cfg):
                return
            print("  Starting new refresh...")
            refresh_result = as_client.start_instance_refresh(
                AutoScalingGroupName=group_name,
                Preferences=dict(MinHealthyPercentage=min_healthy_percent)
            )
            refresh_id = refresh_result['InstanceRefreshId']
            print(f"  id {refresh_id}")

        last_log = ""
        while True:
            time.sleep(5)
            describe_state = as_client.describe_instance_refreshes(
                AutoScalingGroupName=group_name,
                InstanceRefreshIds=[refresh_id]
            )
            refresh = describe_state['InstanceRefreshes'][0]
            status = refresh['Status']
            if status == 'InProgress':
                log = f"  {status}, {refresh['PercentageComplete']}%, " \
                      f"{refresh['InstancesToUpdate']} to update. " \
                      f"{refresh.get('StatusReason', '')}"
            else:
                log = f"  Status: {status}"
            if log != last_log:
                print(log)
                last_log = log
            if status in ('Successful', 'Failed', 'Cancelled'):
                break


@environment.command(name='stop')
@click.pass_obj
def environment_stop(cfg: Config):
    """Stops an environment."""
    if cfg.env == Environment.PROD:
        print('Operation aborted. This would bring down the site')
        print('If you know what you are doing, edit the code in bin/lib/ce.py, function environment_stop_cmd')
    elif are_you_sure('stop environment', cfg):
        for asg in get_autoscaling_groups_for(cfg):
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


@cli.group()
def tools():
    """Tool installation commands."""


@tools.command(name='list')
@click.option('--destination', type=click.Path(file_okay=False, dir_okay=True),
              default=CE_TOOLS_LOCATION)
@click.option('-b', '--branch', type=str, help='show only BRANCH (may be specified more than once)',
              metavar='BRANCH', multiple=True)
def tools_list(destination: str, branch: List[str]):
    current_version = Hash('')
    hash_file = Path(destination) / 'git_hash'
    if hash_file.exists():
        current_version = Hash(hash_file.read_text(encoding='utf-8').strip())
    display_releases(current_version, set(branch), get_tools_releases())


@tools.command(name='install')
@click.option('--destination', type=click.Path(file_okay=False, dir_okay=True),
              default=CE_TOOLS_LOCATION)
@click.argument('version')
def tools_install(version: str, destination: str):
    """
    Install demangling tools version VERSION.
    """
    releases = get_tools_releases()
    version = Version.from_string(version, assumed_source=VersionSource.GITHUB)
    for release in releases:
        if release.version == version:
            if not are_you_sure("deploy tools"):
                return
            with TemporaryDirectory(prefix='ce-tools-') as td_str:
                td = Path(td_str)
                tar_dest = td / 'tarball.tar.xz'
                unpack_dest = td / 'tools'
                unpack_dest.mkdir()
                download_release_file(release.key, str(tar_dest))
                subprocess.check_call([
                    'tar',
                    '--strip-components', '1',
                    '-C', str(unpack_dest),
                    '-Jxf', str(tar_dest)
                ])
                subprocess.check_call([
                    'rsync',
                    '-a',
                    '--delete-after',
                    f'{unpack_dest}/',
                    f'{destination}/'
                ])
            click.echo(f'Tools updated to {version}')
            return
    click.echo(f'Unable to find version {version}')


def main():
    try:
        cli(prog_name='ce')  # pylint: disable=unexpected-keyword-arg,no-value-for-parameter
    except (KeyboardInterrupt, SystemExit):
        # print empty line so terminal prompt doesn't end up on the end of some
        # of our own program output
        print()


if __name__ == '__main__':
    main()
