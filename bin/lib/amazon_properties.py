import os
import tempfile
import urllib.parse
from collections import defaultdict

import requests


def get_properties_compilers_and_libraries(language, logger):
    _compilers = defaultdict(lambda: [])
    _libraries = defaultdict(lambda: [])

    encoded_language = urllib.parse.quote(language)
    url = f'https://raw.githubusercontent.com/mattgodbolt/compiler-explorer/master/etc/config/{encoded_language}.amazon.properties'
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
                groups[group]['options'] = ""
                groups[group]['compilerType'] = ""
                groups[group]['compilers'] = []
                groups[group]['supportsBinary'] = True

            if key[2] == "compilers":
                groups[group]['compilers'] = val.split(':')
            elif key[2] == "options":
                groups[group]['options'] = val
            elif key[2] == "compilerType":
                groups[group]['compilerType'] = val
            elif key[2] == "supportsBinary":
                groups[group]['supportsBinary'] = val == 'true'
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
                _libraries[libid]['liblink'] = val
            elif key[2] == 'staticliblink':
                _libraries[libid]['staticliblink'] = val
            elif key[2] == 'versions':
                if len(key) > 3:
                    versionid = key[3]
                    if not 'versionprops' in _libraries[libid]:
                        _libraries[libid]['versionprops'] = defaultdict(lambda: [])
                    if not versionid in _libraries[libid]['versionprops']:
                        _libraries[libid]['versionprops'][versionid] = defaultdict(lambda: [])
                    if key[4] == 'path':
                        _libraries[libid]['versionprops'][versionid][key[4]] = val.split(':')
                    if key[4] == 'libpath':
                        _libraries[libid]['versionprops'][versionid][key[4]] = val.split(':')
                else:
                    _libraries[libid]['versions'] = val

    logger.debug('Setting default values for compilers')
    for group in groups:
        for compiler in groups[group]['compilers']:
            if not compiler in _compilers:
                _compilers[compiler] = defaultdict(lambda: [])
            _compilers[compiler]['options'] = groups[group]['options']
            _compilers[compiler]['compilerType'] = groups[group]['compilerType']
            _compilers[compiler]['supportsBinary'] = groups[group]['supportsBinary']
            _compilers[compiler]['group'] = group

    logger.debug('Reading properties for compilers')
    for line in lines:
        sline = line.decode('utf-8').rstrip('\n')
        if sline.startswith('compiler.'):
            keyval = sline.split('=', 1)
            key = keyval[0].split('.')
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
            keysToRemove[compiler] = True
        elif _compilers[compiler] == 'wine-vc':
            keysToRemove[compiler] = True
        elif 'exe' in _compilers[compiler]:
            exe = _compilers[compiler]['exe']
            if not os.path.exists(exe):
                keysToRemove[compiler] = True
        else:
            keysToRemove[compiler] = True

    for compiler in keysToRemove:
        del _compilers[compiler]

    return [_compilers, _libraries]
