import contextlib
import glob
import hashlib
import itertools
import json
import os
import re
import shutil
import subprocess
import tempfile
from collections import defaultdict
from enum import Enum, unique
from pathlib import Path
from typing import Dict, Any, List, Optional, Generator, TextIO

import requests

from lib.rust_crates import RustCrate

from lib.amazon import get_ssm_param
from lib.amazon_properties import get_properties_compilers_and_libraries
from lib.library_build_config import LibraryBuildConfig

build_supported_os = ['Linux']
build_supported_buildtype = ['Debug']
build_supported_arch = ['x86_64']
build_supported_stdver = ['']
build_supported_stdlib = ['']
build_supported_flags = ['']
build_supported_flagscollection = [['']]

_propsandlibs: Dict[str, Any] = defaultdict(lambda: [])

GITCOMMITHASH_RE = re.compile(r'^(\w*)\s.*')
CONANINFOHASH_RE = re.compile(r'\s+ID:\s(\w*)')


@unique
class BuildStatus(Enum):
    Ok = 0
    Failed = 1
    Skipped = 2
    TimedOut = 3


build_timeout = 600

conanserver_url = "https://conan.compiler-explorer.com"


@contextlib.contextmanager
def open_script(script: Path) -> Generator[TextIO, None, None]:
    with script.open('w', encoding='utf-8') as f:
        yield f
    script.chmod(0o755)


class RustLibraryBuilder:
    def __init__(self, logger, language: str, libname: str, target_name: str, install_context,
                 buildconfig: LibraryBuildConfig):
        self.logger = logger
        self.language = language
        self.libname = libname
        self.buildconfig = buildconfig
        self.install_context = install_context
        self.target_name = target_name
        self.forcebuild = False
        self.current_buildparameters_obj: Dict[str, Any] = defaultdict(lambda: [])
        self.current_buildparameters: List[str] = []
        self.needs_uploading = 0
        self.libid = self.libname  # TODO: CE libid might be different from yaml libname
        self.conanserverproxy_token = None

        if self.language in _propsandlibs:
            [self.compilerprops, self.libraryprops] = _propsandlibs[self.language]
        else:
            [self.compilerprops, self.libraryprops] = get_properties_compilers_and_libraries(self.language, self.logger)
            _propsandlibs[self.language] = [self.compilerprops, self.libraryprops]

        self.completeBuildConfig()

    def completeBuildConfig(self):
        if 'description' in self.libraryprops[self.libid]:
            self.buildconfig.description = self.libraryprops[self.libid]['description']
        if 'name' in self.libraryprops[self.libid]:
            self.buildconfig.description = self.libraryprops[self.libid]['name']
        if 'url' in self.libraryprops[self.libid]:
            self.buildconfig.url = self.libraryprops[self.libid]['url']

    # pylint: disable=unused-argument
    def writebuildscript(self, buildfolder, sourcefolder, compiler, compileroptions, compilerexe, compilerType,
                         toolchain, buildos, buildtype, arch, stdver, stdlib, flagscombination, ldPath):
        rustbinpath = os.path.dirname(compilerexe)
        rustpath = os.path.dirname(rustbinpath)
        extraflags = ''
        libcxx = ''

        with open_script(Path(sourcefolder) / "build.sh") as f:
            f.write('#!/bin/sh\n\n')

            f.write(f'RUSTPATH={rustpath}\n')
            f.write(f'CARGO={rustbinpath}/cargo\n')
            f.write(f'PATH={rustbinpath}\n')

            for line in self.buildconfig.prebuild_script:
                f.write(f'{line}\n')

            if self.buildconfig.build_type == "cargo":
                cargoline = f'$CARGO build --target-dir {buildfolder} >buildlog.txt 2>&1\n'
                f.write(cargoline)
            else:
                raise RuntimeError('Unknown build_type {self.buildconfig.build_type}')

        self.setCurrentConanBuildParameters(buildos, buildtype, compilerType, compiler, libcxx, arch, stdver,
                                            extraflags)

    def setCurrentConanBuildParameters(self, buildos, buildtype, compilerTypeOrGcc, compiler, libcxx, arch, stdver,
                                       extraflags):
        self.current_buildparameters_obj['os'] = buildos
        self.current_buildparameters_obj['buildtype'] = buildtype
        self.current_buildparameters_obj['compiler'] = compilerTypeOrGcc
        self.current_buildparameters_obj['compiler_version'] = compiler
        self.current_buildparameters_obj['libcxx'] = libcxx
        self.current_buildparameters_obj['arch'] = arch
        self.current_buildparameters_obj['stdver'] = stdver
        self.current_buildparameters_obj['flagcollection'] = extraflags
        self.current_buildparameters_obj['library'] = self.libid
        self.current_buildparameters_obj['library_version'] = self.target_name

        self.current_buildparameters = ['-s', f'os={buildos}',
                                        '-s', f'build_type={buildtype}',
                                        '-s', f'compiler={compilerTypeOrGcc}',
                                        '-s', f'compiler.version={compiler}',
                                        '-s', f'compiler.libcxx={libcxx}',
                                        '-s', f'arch={arch}',
                                        '-s', f'stdver={stdver}',
                                        '-s', f'flagcollection={extraflags}']

    def writeconanscript(self, buildfolder):
        conanparamsstr = ' '.join(self.current_buildparameters)
        with open_script(Path(buildfolder) / "conanexport.sh") as f:
            f.write('#!/bin/sh\n\n')
            f.write(f'conan export-pkg . {self.libname}/{self.target_name} -f {conanparamsstr}\n')

    def writeconanfile(self, buildfolder):
        with (Path(buildfolder) / 'conanfile.py').open(mode='w', encoding='utf-8') as f:
            f.write('from conans import ConanFile, tools\n')
            f.write(f'class {self.libname}Conan(ConanFile):\n')
            f.write(f'    name = "{self.libname}"\n')
            f.write(f'    version = "{self.target_name}"\n')
            f.write('    settings = "os", "compiler", "build_type", "arch", "stdver", "flagcollection"\n')
            f.write(f'    description = "{self.buildconfig.description}"\n')
            f.write(f'    url = "{self.buildconfig.url}"\n')
            f.write('    license = "None"\n')
            f.write('    author = "None"\n')
            f.write('    topics = None\n')
            f.write('    def package(self):\n')
            f.write(f'        self.copy("build/*.*", dst="{self.libname}", keep_path=True)\n')

    def countValidLibraryBinaries(self, buildfolder, arch, stdlib):
        filesfound = 1

        return filesfound

    def executeconanscript(self, buildfolder, arch, stdlib):
        filesfound = self.countValidLibraryBinaries(buildfolder, arch, stdlib)
        if filesfound != 0:
            if subprocess.call(['./conanexport.sh'], cwd=buildfolder) == 0:
                self.logger.info('Export succesful')
                return BuildStatus.Ok
            else:
                return BuildStatus.Failed
        else:
            self.logger.info('No binaries found to export')
            return BuildStatus.Failed

    def executebuildscript(self, buildfolder):
        try:
            if subprocess.call(['./build.sh'], cwd=buildfolder, timeout=build_timeout) == 0:
                self.logger.info(f'Build succeeded in {buildfolder}')
                return BuildStatus.Ok
            else:
                return BuildStatus.Failed
        except subprocess.TimeoutExpired:
            self.logger.info(f'Build timed out and was killed ({buildfolder})')
            return BuildStatus.TimedOut

    def makebuildhash(self, compiler, options, toolchain, buildos, buildtype, arch, stdver, stdlib, flagscombination):
        hasher = hashlib.sha256()
        flagsstr = '|'.join(x for x in flagscombination)
        hasher.update(
            bytes(f'{compiler},{options},{toolchain},{buildos},{buildtype},{arch},{stdver},{stdlib},{flagsstr}',
                  'utf-8'))

        self.logger.info(
            f'Building {self.libname} {self.target_name} for [{compiler},{options},{toolchain},{buildos},{buildtype},{arch},{stdver},{stdlib},{flagsstr}]')

        return compiler + '_' + hasher.hexdigest()

    def get_conan_hash(self, buildfolder: str) -> Optional[str]:
        if not self.install_context.dry_run:
            self.logger.debug(['conan', 'info', '.'] + self.current_buildparameters)
            conaninfo = subprocess.check_output(['conan', 'info', '-r', 'ceserver', '.'] + self.current_buildparameters,
                                                cwd=buildfolder).decode('utf-8', 'ignore')
            self.logger.debug(conaninfo)
            match = CONANINFOHASH_RE.search(conaninfo, re.MULTILINE)
            if match:
                return match[1]
        return None

    def conanproxy_login(self):
        url = f'{conanserver_url}/login'

        login_body = defaultdict(lambda: [])
        login_body['password'] = get_ssm_param('/compiler-explorer/conanpwd')

        request = requests.post(url, data=json.dumps(login_body), headers={"Content-Type": "application/json"})
        if not request.ok:
            self.logger.info(request.text)
            raise RuntimeError(f'Post failure for {url}: {request}')
        else:
            response = json.loads(request.content)
            self.conanserverproxy_token = response['token']

    def save_build_logging(self, builtok, build_folder, source_folder):
        if builtok == BuildStatus.Failed:
            url = f'{conanserver_url}/buildfailed'
        elif builtok == BuildStatus.Ok:
            url = f'{conanserver_url}/buildsuccess'
        elif builtok == BuildStatus.TimedOut:
            url = f'{conanserver_url}/buildfailed'
        else:
            return

        loggingfiles = []
        loggingfiles += glob.glob(source_folder + '/buildlog.txt')

        logging_data = ""
        for logfile in loggingfiles:
            logging_data += Path(logfile).read_text(encoding='utf-8')

        if builtok == BuildStatus.TimedOut:
            logging_data = logging_data + '\n\n' + 'BUILD TIMED OUT!!'

        buildparameters_copy = self.current_buildparameters_obj.copy()
        buildparameters_copy['logging'] = logging_data

        headers = {"Content-Type": "application/json", "Authorization": "Bearer " + self.conanserverproxy_token}

        request = requests.post(url, data=json.dumps(buildparameters_copy), headers=headers)
        if not request.ok:
            raise RuntimeError(f'Post failure for {url}: {request}')

    def get_build_annotations(self, buildfolder):
        conanhash = self.get_conan_hash(buildfolder)
        if conanhash is None:
            return defaultdict(lambda: [])

        url = f'{conanserver_url}/annotations/{self.libname}/{self.target_name}/{conanhash}'
        with tempfile.TemporaryFile() as fd:
            request = requests.get(url, stream=True)
            if not request.ok:
                raise RuntimeError(f'Fetch failure for {url}: {request}')
            for chunk in request.iter_content(chunk_size=4 * 1024 * 1024):
                fd.write(chunk)
            fd.flush()
            fd.seek(0)
            buffer = fd.read()
            return json.loads(buffer)

    def get_commit_hash(self, source_folder) -> str:
        if os.path.exists(f'{source_folder}/.git'):
            lastcommitinfo = subprocess.check_output(
                ['git', '-C', source_folder, 'log', '-1', '--oneline', '--no-color']).decode('utf-8', 'ignore')
            self.logger.debug(lastcommitinfo)
            match = GITCOMMITHASH_RE.match(lastcommitinfo)
            if match:
                return match[1]
            else:
                return self.target_name
        else:
            return self.target_name

    def has_failed_before(self):
        headers = {"Content-Type": "application/json"}

        url = f'{conanserver_url}/hasfailedbefore'
        request = requests.post(url, data=json.dumps(self.current_buildparameters_obj), headers=headers)
        if not request.ok:
            raise RuntimeError(f'Post failure for {url}: {request}')
        else:
            response = json.loads(request.content)
            return response['response']

    def is_already_uploaded(self, buildfolder, source_folder):
        annotations = self.get_build_annotations(buildfolder)

        if 'commithash' in annotations:
            commithash = self.get_commit_hash(source_folder)

            return commithash == annotations['commithash']
        else:
            return False

    def set_as_uploaded(self, buildfolder, source_folder):
        conanhash = self.get_conan_hash(buildfolder)
        if conanhash is None:
            raise RuntimeError(f'Error determining conan hash in {buildfolder}')

        self.logger.info(f'commithash: {conanhash}')

        annotations = self.get_build_annotations(buildfolder)
        if 'commithash' not in annotations:
            self.upload_builds()
        annotations['commithash'] = self.get_commit_hash(source_folder)

        self.logger.info(annotations)

        headers = {"Content-Type": "application/json", "Authorization": "Bearer " + self.conanserverproxy_token}

        url = f'{conanserver_url}/annotations/{self.libname}/{self.target_name}/{conanhash}'
        request = requests.post(url, data=json.dumps(annotations), headers=headers)
        if not request.ok:
            raise RuntimeError(f'Post failure for {url}: {request}')

    def clone_branch(self, dest):
        subprocess.check_call(['git', 'clone', '-q', f'{self.buildconfig.domainurl}/{self.buildconfig.repo}.git', dest],
                                cwd=self.install_context.staging)
        subprocess.check_call(['git', '-C', dest, 'checkout', '-q', self.target_name],
                                cwd=self.install_context.staging)

    def download_library(self, build_folder):
        source_folder = os.path.join(build_folder, 'source')

        if self.buildconfig.repo:
            self.clone_branch(source_folder)
        else:
            crate = RustCrate(self.libname, self.target_name)
            url = crate.GetDownloadUrl()
            tar_cmd = ['tar', 'zxf', '-']
            tar_cmd += ['--strip-components', '1']
            self.install_context.fetch_url_and_pipe_to(f'{url}', tar_cmd, source_folder)

        return source_folder

    def makebuildfor(self, compiler, options, exe, compiler_type, toolchain, buildos, buildtype, arch, stdver, stdlib,
                     flagscombination, ld_path):
        combined_hash = self.makebuildhash(compiler, options, toolchain, buildos, buildtype, arch, stdver, stdlib,
                                           flagscombination)

        build_folder = os.path.join(self.install_context.staging, combined_hash)
        if os.path.exists(build_folder):
            shutil.rmtree(build_folder, ignore_errors=True)
        os.makedirs(build_folder, exist_ok=True)

        self.logger.debug(f'Buildfolder: {build_folder}')

        source_folder = self.download_library(build_folder)

        real_build_folder = os.path.join(build_folder, 'build')
        self.writebuildscript(
            real_build_folder, source_folder, compiler, options, exe, compiler_type, toolchain, buildos, buildtype,
            arch, stdver, stdlib, flagscombination, ld_path)
        self.writeconanfile(build_folder)

        if not self.forcebuild and self.has_failed_before():
            self.logger.info("Build has failed before, not re-attempting")
            return BuildStatus.Skipped

        if self.is_already_uploaded(build_folder, source_folder):
            self.logger.info("Build already uploaded")
            if not self.forcebuild:
                return BuildStatus.Skipped

        if not self.install_context.dry_run and not self.conanserverproxy_token:
            self.conanproxy_login()

        build_status = self.executebuildscript(source_folder)
        if build_status == BuildStatus.Ok:
            self.writeconanscript(build_folder)
            if not self.install_context.dry_run:
                build_status = self.executeconanscript(build_folder, arch, stdlib)
                if build_status == BuildStatus.Ok:
                    self.needs_uploading += 1
                    self.set_as_uploaded(build_folder, source_folder)
            else:
                filesfound = self.countValidLibraryBinaries(build_folder, arch, stdlib)
                self.logger.debug(f'Number of valid library binaries {filesfound}')

        if not self.install_context.dry_run:
            self.save_build_logging(build_status, build_folder, source_folder)

        if build_status == BuildStatus.Ok:
            self.build_cleanup(build_folder)

        return build_status

    def build_cleanup(self, buildfolder):
        if self.install_context.dry_run:
            self.logger.info(f'Would remove directory {buildfolder} but in dry-run mode')
        else:
            shutil.rmtree(buildfolder, ignore_errors=True)
            self.logger.info(f'Removing {buildfolder}')

    def upload_builds(self):
        if self.needs_uploading > 0:
            if not self.install_context.dry_run:
                self.logger.info('Uploading cached builds')
                subprocess.check_call(
                    ['conan', 'upload', f'{self.libname}/{self.target_name}', '--all', '-r=ceserver', '-c'])
                self.logger.debug('Clearing cache to speed up next upload')
                subprocess.check_call(['conan', 'remove', '-f', f'{self.libname}/{self.target_name}'])
            self.needs_uploading = 0

    def makebuild(self, buildfor):
        builds_failed = 0
        builds_succeeded = 0
        builds_skipped = 0

        if buildfor != "":
            self.forcebuild = True

        checkcompiler = buildfor
        if checkcompiler not in self.compilerprops:
            self.logger.error(f'Unknown compiler {checkcompiler}')

        for compiler in self.compilerprops:
            if checkcompiler != "" and compiler != checkcompiler:
                continue

            if compiler in self.buildconfig.skip_compilers:
                self.logger.info(f'Skipping {compiler}')
                continue

            if 'compilerType' in self.compilerprops[compiler]:
                compilerType = self.compilerprops[compiler]['compilerType']
            else:
                raise RuntimeError(f'Something is wrong with {compiler}')

            exe = self.compilerprops[compiler]['exe']
            options = self.compilerprops[compiler]['options']
            toolchain = ''

            stdlibs = ['']
            archs = build_supported_arch
            stdvers = build_supported_stdver
            ldPath = ''

            for args in itertools.product(
                    build_supported_os, build_supported_buildtype, archs, stdvers, stdlibs,
                    build_supported_flagscollection):
                buildstatus = self.makebuildfor(compiler, options, exe, compilerType, toolchain,
                                                *args, ldPath)
                if buildstatus == BuildStatus.Ok:
                    builds_succeeded = builds_succeeded + 1
                elif buildstatus == BuildStatus.Skipped:
                    builds_skipped = builds_skipped + 1
                else:
                    builds_failed = builds_failed + 1

            if builds_succeeded > 0:
                self.upload_builds()

        return [builds_succeeded, builds_skipped, builds_failed]
