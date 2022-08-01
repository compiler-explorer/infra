
from pyparsing import Regex
from .cli import cli
from lib.amazon import get_current_key
from lib.cli.builds import __builds_set_current
from lib.cli.runner import runner_discovery, runner_pull, runner_start, runner_stop, runner_uploaddiscovery
from lib.env import Config, Environment

@cli.group()
def maintenance():
    """Maintenance commands."""

@maintenance.command(name='rediscovery')
def maintenance_rediscovery():
    """Rediscovery"""
    cfgprod = Config(env = Environment('prod'))
    cfgrunner = Config(env = Environment('runner'))
    print("a")
    current_release_path = get_current_key(cfgprod) or ''
    re = Regex(r"dist\/gh\/.*\/(\d*).tar.xz")
    current = "gh-" + re.re_match(current_release_path)[1]
    print(current)
    print("b")
    __builds_set_current(cfgrunner, 'main', current, False, True)
    print("c")
    runner_start()
    print("d")
    runner_pull()
    print("e")
    runner_discovery()
    print("f")
    runner_uploaddiscovery(cfgprod, current)
    print("g")
    runner_stop()
    print("h")
    # restart prod instances
