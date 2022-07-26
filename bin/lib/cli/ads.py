import json
from typing import Sequence, Optional

import click
import dateutil.parser

from lib.amazon import save_event_file
from lib.ce_utils import get_events, are_you_sure
from lib.cli import cli
from lib.env import Config

ADS_FORMAT = '{: <5} {: <10} {: <10} {: <20}'


def format_ad(ad):
    valid_from = ad['valid_from'] if 'valid_from' in ad else ''
    valid_until = ad['valid_until'] if 'valid_until' in ad else ''
    return ADS_FORMAT.format(ad['id'], str(ad['filter']), f"{valid_from} - {valid_until}", ad['html'])


@cli.group()
def ads():
    """Community advert manipulation features."""


@ads.command(name='list')
@click.pass_obj
def ads_list(cfg: Config):
    """List the existing community adverts."""
    events = get_events(cfg)
    print(ADS_FORMAT.format('ID', 'Filters', 'Valid dates', 'HTML'))
    for ad in events['ads']:
        print(format_ad(ad))


@ads.command(name='add')
@click.pass_obj
@click.option("--filter", 'lang_filter', help='Filter to these languages (default all)', multiple=True)
@click.option("--from", 'valid_from', help='Ad valid from this date', default=None)
@click.option("--until", 'valid_until', help='Ad valid until this date', default=None)
@click.argument("html")
def ads_add(cfg: Config, lang_filter: Sequence[str], valid_from: Optional[str], valid_until: Optional[str], html: str):
    """Add a community advert with HTML."""
    events = get_events(cfg)
    new_ad = {
        'html': html,
        'filter': lang_filter,
        'id': max([x['id'] for x in events['ads']]) + 1 if len(events['ads']) > 0 else 0
    }
    if valid_from is not None:
        parsed_from = ''
        try:
            parsed_from = dateutil.parser.parse(valid_from).isoformat()
        except:
            print(f'Could not parse valid_from {valid_from} date, aborting')
            return
        finally:
            new_ad['valid_from'] = parsed_from
    if valid_until is not None:
        parsed_until = ''
        try:
            parsed_until = dateutil.parser.parse(valid_until).isoformat()
        except:
            print(f'Could not parse valid_until {valid_until} date, aborting')
            return
        finally:
            new_ad['valid_until'] = parsed_until
    if are_you_sure('add ad: {}'.format(format_ad(new_ad)), cfg):
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
            if force or are_you_sure('remove ad: {}'.format(format_ad(ad)), cfg):
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
@click.option("--from", 'valid_from', help='Ad valid from this date', default=None)
@click.option("--until", 'valid_until', help='Ad valid until this date', default=None)
@click.argument('ad_id', type=int)
@click.pass_obj
def ads_edit(cfg: Config, ad_id: int, html: str, lang_filter: Sequence[str], valid_from: Optional[str], valid_until: Optional[str]):
    """Edit community ad AD_ID."""
    events = get_events(cfg)
    for i, ad in enumerate(events['ads']):
        if ad['id'] == ad_id:
            new_ad = {
                'id': ad['id'],
                'filter': lang_filter or ad['filter'],
                'html': html or ad['html']
            }
            if valid_from is not None:
                parsed_from = ''
                try:
                    parsed_from = dateutil.parser.parse(valid_from).isoformat()
                except:
                    print(f'Could not parse valid_from {valid_from} date, aborting')
                    break
                finally:
                    new_ad['valid_from'] = parsed_from
            if valid_until is not None:
                parsed_until = ''
                try:
                    parsed_until = dateutil.parser.parse(valid_until).isoformat()
                except:
                    print(f'Could not parse valid_until {valid_until} date, aborting')
                    break
                finally:
                    new_ad['valid_until'] = parsed_until
            print('\t{}\n<FROM\t{}\n>TO\t{}'.format(ADS_FORMAT.format('Event', 'Filter(s)', 'Valid date', 'HTML'),
                                                    format_ad(ad),
                                                    format_ad(new_ad)))
            if are_you_sure('edit ad id: {}'.format(ad['id']), cfg):
                events['ads'][i] = new_ad
                save_event_file(cfg, json.dumps(events))
            break
