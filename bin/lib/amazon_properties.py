import os
import tempfile
import re
import urllib.parse
from collections import defaultdict

import requests


def get_specific_library_version_details(libraries, libid, libraryVersion):
    if 'versionprops' in libraries[libid]:
        for verid in libraries[libid]['versionprops']:
            versionProps = libraries[libid]['versionprops'][verid]
            if versionProps['version'] == libraryVersion or versionProps['lookupversion'] == libraryVersion:
                return versionProps

    return False


COMPILEROPT_RE = re.compile(r'(\w*)\.(.*)\.(\w*)')

def get_properties_compilers_and_libraries(language, logger):
    _compilers = defaultdict(lambda: [])
    _libraries = defaultdict(lambda: [])

    encoded_language = urllib.parse.quote(language)
    url = f'https://raw.githubusercontent.com/compiler-explorer/compiler-explorer/main/etc/config/{encoded_language}.amazon.properties'
    lines = []
    with tempfile.TemporaryFile() as fd:
        request = requests.get(url, stream=True)
        if not request.ok:
            raise RuntimeError(f'Fetch failure for {url}: {request}')
        for chunk in request.iter_content(chunk_size=4 * 1024 * 1024):
            fd.write(chunk)
        fd.flush()
        fd.seek(0)
        lines = fd.readlines()

    logger.debug('Reading properties for groups')
    groups = defaultdict(lambda: [])
    for line in lines:
        sline = line.decode('utf-8').rstrip('\n')
        if sline.startswith('group.'):
            keyval = sline.split('=', 1)
            key = keyval[0].split('.')
            val = keyval[1]
            group = key[1]
            if not group in groups:
                groups[group] = defaultdict(lambda: [])

            if key[2] == "compilers":
                groups[group]['compilers'] = val.split(':')
            elif key[2] == "options":
                groups[group]['options'] = val
            elif key[2] == "compilerType":
                groups[group]['compilerType'] = val
            elif key[2] == "supportsBinary":
                groups[group]['supportsBinary'] = val == 'true'
            elif key[2] == "ldPath":
                groups[group]['ldPath'] = val
        elif sline.startswith('libs.'):
            keyval = sline.split('=', 1)
            key = keyval[0].split('.')
            val = keyval[1]
            libid = key[1]
            if not libid in _libraries:
                _libraries[libid] = defaultdict(lambda: [])

            if key[2] == 'description':
                _libraries[libid]['description'] = val
            elif key[2] == 'name':
                _libraries[libid]['name'] = val
            elif key[2] == 'url':
                _libraries[libid]['url'] = val
            elif key[2] == 'liblink':
                _libraries[libid]['liblink'] = val.split(':')
            elif key[2] == 'staticliblink':
                _libraries[libid]['staticliblink'] = val.split(':')
            elif key[2] == 'versions':
                if len(key) > 3:
                    versionid = key[3]
                    if not 'versionprops' in _libraries[libid]:
                        _libraries[libid]['versionprops'] = defaultdict(lambda: [])
                    if not versionid in _libraries[libid]['versionprops']:
                        _libraries[libid]['versionprops'][versionid] = defaultdict(lambda: [])
                    if len(key) > 4:
                        if key[4] == 'version':
                            _libraries[libid]['versionprops'][versionid][key[4]] = val
                        if key[4] == 'lookupversion':
                            _libraries[libid]['versionprops'][versionid][key[4]] = val
                        if key[4] == 'path':
                            _libraries[libid]['versionprops'][versionid][key[4]] = val.split(':')
                        if key[4] == 'libpath':
                            _libraries[libid]['versionprops'][versionid][key[4]] = val.split(':')
                        if key[4] == 'staticliblink':
                            _libraries[libid]['versionprops'][versionid][key[4]] = val.split(':')
                        if key[4] == 'liblink':
                            _libraries[libid]['versionprops'][versionid][key[4]] = val.split(':')
                else:
                    _libraries[libid]['versions'] = val

    logger.debug('Setting default values for compilers')
    for group in groups:
        for compiler in groups[group]['compilers']:
            if '&' in compiler:
                subgroupname = compiler[1:]
                if not 'options' in groups[subgroupname] and 'options' in groups[group]:
                    groups[subgroupname]['options'] = groups[group]['options']
                if not 'compilerType' in groups[subgroupname] and 'compilerType' in groups[group]:
                    groups[subgroupname]['compilerType'] = groups[group]['compilerType']
                if not 'supportsBinary' in groups[subgroupname] and 'supportsBinary' in groups[group]:
                    groups[subgroupname]['supportsBinary'] = groups[group]['supportsBinary']
                if not 'ldPath' in groups[subgroupname] and 'ldPath' in groups[group]:
                    groups[subgroupname]['ldPath'] = groups[group]['ldPath']

            if not compiler in _compilers:
                _compilers[compiler] = defaultdict(lambda: [])

            if 'options' in groups[group]:
                _compilers[compiler]['options'] = groups[group]['options']
            else:
                _compilers[compiler]['options'] = ""

            if 'compilerType' in groups[group]:
                _compilers[compiler]['compilerType'] = groups[group]['compilerType']
            else:
                _compilers[compiler]['compilerType'] = ""

            if 'supportsBinary' in groups[group]:
                _compilers[compiler]['supportsBinary'] = groups[group]['supportsBinary']
            else:
                _compilers[compiler]['supportsBinary'] = True

            if 'ldPath' in groups[group]:
                _compilers[compiler]['ldPath'] = groups[group]['ldPath']
            else:
                _compilers[compiler]['ldPath'] = ""

            _compilers[compiler]['group'] = group

    logger.debug('Reading properties for compilers')
    for line in lines:
        sline = line.decode('utf-8').rstrip('\n')
        if sline.startswith('compiler.'):
            keyval = sline.split('=', 1)
            matches = COMPILEROPT_RE.match(keyval[0])
            if not matches:
                raise RuntimeError(f'Not a valid compiler? {keyval}')
            key = [matches[1], matches[2], matches[3]]
            val = keyval[1]
            if not key[1] in _compilers:
                _compilers[key[1]] = defaultdict(lambda: [])

            if key[2] == "supportsBinary":
                _compilers[key[1]][key[2]] = val == 'true'
            else:
                _compilers[key[1]][key[2]] = val

    logger.debug('Removing compilers that are not available or do not support binaries')
    keysToRemove = defaultdict(lambda: [])
    for compiler in _compilers:
        if 'supportsBinary' in _compilers[compiler] and not _compilers[compiler]['supportsBinary']:
            logger.debug(compiler + ' does not supportsBinary')
            keysToRemove[compiler] = True
        elif 'compilerType' in _compilers[compiler] and _compilers[compiler]['compilerType'] == 'wine-vc':
            keysToRemove[compiler] = True
        elif 'exe' in _compilers[compiler]:
            exe = _compilers[compiler]['exe']
            if not os.path.exists(exe):
                keysToRemove[compiler] = True
        else:
            keysToRemove[compiler] = True

    for compiler in keysToRemove:
        logger.debug('removing ' + compiler)
        del _compilers[compiler]

    return [_compilers, _libraries]
