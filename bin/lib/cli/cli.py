import logging

import click

from lib.env import Environment, Config


@click.group()
@click.option(
    "--env",
    type=click.Choice([env.value for env in Environment]),
    default=Environment.STAGING.value,
    metavar="ENV",
    help="Select environment ENV",
)
@click.option("--debug/--no-debug", help="Turn on debugging")
@click.pass_context
def cli(ctx: click.Context, env: str, debug: bool):
    ctx.obj = Config(env=Environment(env))
    if debug:
        logging.basicConfig(level=logging.DEBUG)
    else:
        logging.basicConfig(level=logging.INFO)
        logging.getLogger("boto3").setLevel(logging.WARNING)
        logging.getLogger("botocore").setLevel(logging.WARNING)
        logging.getLogger("paramiko").setLevel(logging.WARNING)
