import json
from typing import Sequence

import click

from lib.amazon import save_event_file
from lib.ce_utils import get_events, are_you_sure
from lib.cli import cli
from lib.env import Config

ADS_FORMAT = '{: <5} {: <10} {: <20}'


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
