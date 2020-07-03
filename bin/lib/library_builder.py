import re
import os
import glob
import json
import hashlib
import shutil
import subprocess
import requests
import tempfile
from lib.amazon import get_ssm_param
from lib.amazon_properties import get_specific_library_version_details, get_properties_compilers_and_libraries
from lib.library_build_config import LibraryBuildConfig
from lib.binary_info import BinaryInfo
from collections import defaultdict
from typing import Dict, Any, List

build_supported_os = ['Linux']
build_supported_buildtype = ['Debug']
build_supported_arch = ['x86_64', 'x86']
build_supported_stdver = ['']
build_supported_stdlib = ['', 'libc++']
build_supported_flags = ['']
build_supported_flagscollection = [['']]

_propsandlibs: Dict[str, Any] = defaultdict(lambda: [])


GITCOMMITHASH_RE = re.compile(r'^(\w*)\s.*')
CONANINFOHASH_RE = re.compile(r'\s+ID:\s(\w*)')

c_BuildOk = 0
c_BuildFailed = 1
c_BuildSkipped = 2

conanserver_url = "https://conan.compiler-explorer.com"

class LibraryBuilder:
    def __init__(self, logger, language: str, libname: str, target_name: str, sourcefolder: str, install_context, buildconfig: LibraryBuildConfig):
        self.logger = logger
        self.language = language
        self.libname = libname
        self.buildconfig = buildconfig
        self.install_context = install_context
        self.sourcefolder = sourcefolder
        self.target_name = target_name
        self.forcebuild = False
        self.current_buildparameters_obj: Dict[str, Any] = defaultdict(lambda: [])
        self.current_buildparameters: List[str] = []
        self.needs_uploading = 0
        self.libid = self.libname    # TODO: CE libid might be different from yaml libname
        self.conanserverproxy_token = False

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

        if 'staticliblink' in self.libraryprops[self.libid]:
            self.buildconfig.staticliblink = self.libraryprops[self.libid]['staticliblink']

        if 'liblink' in self.libraryprops[self.libid]:
            self.buildconfig.sharedliblink = self.libraryprops[self.libid]['liblink']

        specificVersionDetails = get_specific_library_version_details(self.libraryprops, self.libid, self.target_name)
        if specificVersionDetails:
            if 'staticliblink' in specificVersionDetails:
                self.buildconfig.staticliblink = specificVersionDetails['staticliblink']
                
            if 'liblink' in specificVersionDetails:
                self.buildconfig.sharedliblink = specificVersionDetails['liblink']

        if self.buildconfig.lib_type == "static":
            if self.buildconfig.staticliblink == []:
                self.buildconfig.staticliblink = [f'{self.libname}']
        elif self.buildconfig.lib_type == "shared":
            if self.buildconfig.sharedliblink == []:
                self.buildconfig.sharedliblink = [f'{self.libname}']

        alternatelibs = []
        for lib in self.buildconfig.staticliblink:
            if lib.endswith('d'):
                alternatelibs += [lib[:-1]]
            else:
                alternatelibs += [f'{lib}d']
        self.buildconfig.staticliblink += alternatelibs

    def getToolchainPathFromOptions(self, options):
        match = re.search(r"--gcc-toolchain=(\S*)", options)
        if match:
            return match[1]
        else:
            match = re.search(r"--gxx-name=(\S*)", options)
            if match:
                return os.path.realpath(os.path.join(os.path.dirname(match[1]), ".."))
        return False

    def getStdVerFromOptions(self, options):
        match = re.search(r"-std=(\S*)", options)
        if match:
            return match[1]
        return False
    
    def getStdLibFromOptions(self, options):
        match = re.search(r"-stdlib=(\S*)", options)
        if match:
            return match[1]
        return False

    def getTargetFromOptions(self, options):
        match = re.search(r"-target (\S*)", options)
        if match:
            return match[1]
        return False

    def does_compiler_support(self, exe, compilerType, arch, options):
        fixedTarget = self.getTargetFromOptions(options)
        if fixedTarget:
            return fixedTarget == arch

        if compilerType == "":
            if 'icc' in exe:
                output = subprocess.check_output([exe, '--help']).decode('utf-8', 'ignore')
                if arch == 'x86':
                    arch = "-m32"
                elif arch == 'x86_64':
                    arch = "-m64"
            else:
                if 'zapcc' in exe:
                    return arch == 'x86' or arch == 'x86_64'
                else:
                    output = subprocess.check_output([exe, '--target-help']).decode('utf-8', 'ignore')
        elif compilerType == "clang":
            folder = os.path.dirname(exe)
            llcexe = os.path.join(folder, 'llc')
            if os.path.exists(llcexe):
                try:
                    output = subprocess.check_output([llcexe, '--version']).decode('utf-8', 'ignore')
                except subprocess.CalledProcessError as e:
                    output = e.output.decode('utf-8', 'ignore')
            else:
                output = ""
        else:
            output = ""

        if arch in output:
            self.logger.debug(f'Compiler {exe} supports {arch}')
            return True
        else:
            self.logger.debug(f'Compiler {exe} does not support {arch}')
            return False

    def does_compiler_support_x86(self, exe, compilerType, options):
        return self.does_compiler_support(exe, compilerType, 'x86', options)

    def writebuildscript(self, buildfolder, sourcefolder, compiler, compileroptions, compilerexe, compilerType, toolchain, buildos, buildtype, arch, stdver, stdlib, flagscombination):
        scriptfile = os.path.join(buildfolder, "build.sh")

        f = open(scriptfile, 'w')
        f.write('#!/bin/sh\n\n')
        compilerexecc = compilerexe[:-2]
        if compilerexe.endswith('clang++'):
            compilerexecc = f'{compilerexecc}'
        elif compilerexe.endswith('g++'):
            compilerexecc = f'{compilerexecc}cc'

        f.write(f'export CC={compilerexecc}\n')
        f.write(f'export CXX={compilerexe}\n')

        ldlibpaths = []
        archflag = ''
        if arch == '':
            # note: native arch for the compiler, so most of the time 64, but not always
            if os.path.exists(f'{toolchain}/lib64'):
                ldlibpaths.append(f'{toolchain}/lib64')
                ldlibpaths.append(f'{toolchain}/lib')
            else:
                ldlibpaths.append(f'{toolchain}/lib')
        elif arch == 'x86':
            ldlibpaths.append(f'{toolchain}/lib')
            if os.path.exists(f'{toolchain}/lib32'):
                ldlibpaths.append(f'{toolchain}/lib32')

            if compilerType == 'clang':
                archflag = '-m32'
            elif compilerType == '':
                archflag = '-march=i386 -m32'

        rpathflags = ''
        ldflags = ''
        for path in ldlibpaths:
            rpathflags += f'-Wl,-rpath={path} '

        for path in ldlibpaths:
            ldflags += f'-L{path} '

        ldlibpathsstr = ':'.join(ldlibpaths)
        f.write(f'export LD_LIBRARY_PATHS="{ldlibpathsstr}"\n')
        f.write(f'export LDFLAGS="{ldflags} {rpathflags}"\n')

        stdverflag = ''
        if stdver != '':
            stdverflag = f'-std={stdver}'
        
        stdlibflag = ''
        if stdlib != '' and compilerType == 'clang':
            libcxx = stdlib
            stdlibflag = f'-stdlib={stdlib}'
            if stdlibflag in compileroptions:
                stdlibflag = ''
        else:
            libcxx = "libstdc++"

        extraflags = ' '.join(x for x in flagscombination)

        if compilerType == "":
            compilerTypeOrGcc = "gcc"
        else:
            compilerTypeOrGcc = compilerType

        cxx_flags = f'{compileroptions} {archflag} {stdverflag} {stdlibflag} {rpathflags} {extraflags}'
        configure_flags = ''

        if len(self.buildconfig.prebuildscript) > 0:
            for line in self.buildconfig.prebuildscript:
                f.write(f'{line}\n')

        if self.buildconfig.build_type == "cmake":
            extracmakeargs = ' '.join(self.buildconfig.extra_cmake_arg)
            if compilerTypeOrGcc == "clang" and "--gcc-toolchain=" not in compileroptions:
                toolchainparam = ""
            else:
                toolchainparam = f'"-DCMAKE_CXX_COMPILER_EXTERNAL_TOOLCHAIN={toolchain}"'
            cmakeline = f'cmake -DCMAKE_BUILD_TYPE={buildtype} {toolchainparam} "-DCMAKE_CXX_FLAGS_DEBUG={cxx_flags}" {extracmakeargs} {sourcefolder} > cecmakelog.txt 2>&1\n'
            self.logger.debug(cmakeline)
            f.write(cmakeline)
        else:
            if os.path.exists(os.path.join(sourcefolder, 'Makefile')):
                f.write('make clean\n')
            f.write('rm *.so*\n')
            f.write('rm *.a\n')
            f.write(f'export CXXFLAGS="{cxx_flags}"\n')
            if self.buildconfig.build_type == "make":
                configurepath = os.path.join(sourcefolder, 'configure')
                if os.path.exists(configurepath):
                    f.write(f'./configure {configure_flags} > ceconfiglog.txt 2>&1\n')

        if len(self.buildconfig.make_targets) != 0:
            lognum = 0 
            for target in self.buildconfig.make_targets:
                f.write(f'make {target} > cemakelog_{lognum}.txt 2>&1\n')
                lognum += 1
        else:
            lognum = 0 
            if len(self.buildconfig.staticliblink) != 0:
                for lib in self.buildconfig.staticliblink:
                    f.write(f'make {lib} > cemakelog_{lognum}.txt 2>&1\n')
                    lognum += 1

            if len(self.buildconfig.sharedliblink) != 0:
                for lib in self.buildconfig.sharedliblink:
                    f.write(f'make {lib} > cemakelog_{lognum}.txt 2>&1\n')
                    lognum += 1

            if len(self.buildconfig.staticliblink) != 0:
                f.write('libsfound=$(find . -iname \'lib*.a\')\n')
            elif len(self.buildconfig.sharedliblink) != 0:
                f.write('libsfound=$(find . -iname \'lib*.so*\')\n')

            f.write('if [ "$libsfound" = "" ]; then\n')
            f.write('  make all > cemakelog_{lognum}.txt 2>&1\n')
            f.write('fi\n')

        for lib in self.buildconfig.staticliblink:
            f.write(f'find . -iname \'lib{lib}*.a\' -type f -exec mv {{}} . \\;\n')

        for lib in self.buildconfig.sharedliblink:
            f.write(f'find . -iname \'lib{lib}*.so*\' -type f,l -exec mv {{}} . \\;\n')

        f.close()
        subprocess.check_call(['/bin/chmod','+x', scriptfile])

        self.setCurrentConanBuildParameters(buildos, buildtype, compilerTypeOrGcc, compiler, libcxx, arch, stdver, extraflags)

    def setCurrentConanBuildParameters(self, buildos, buildtype, compilerTypeOrGcc, compiler, libcxx, arch, stdver, extraflags):
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
        scriptfile = os.path.join(buildfolder, "conanexport.sh")
        conanparamsstr = ' '.join(self.current_buildparameters)

        f = open(scriptfile, 'w')
        f.write('#!/bin/sh\n\n')
        f.write(f'conan export-pkg . {self.libname}/{self.target_name} -f {conanparamsstr}\n')
        f.close()
        subprocess.check_call(['/bin/chmod','+x', scriptfile])

    def writeconanfile(self, buildfolder):
        scriptfile = os.path.join(buildfolder, "conanfile.py")

        libsum = ''
        for lib in self.buildconfig.staticliblink:
            libsum += f'"{lib}",'

        for lib in self.buildconfig.sharedliblink:
            libsum += f'"{lib}",'

        libsum = libsum[:-1]

        f = open(scriptfile, 'w')
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
        for lib in self.buildconfig.staticliblink:
            f.write(f'        self.copy("lib{lib}*.a", dst="lib", keep_path=False)\n')
        for lib in self.buildconfig.sharedliblink:
            f.write(f'        self.copy("lib{lib}*.so*", dst="lib", keep_path=False)\n')
        f.write('    def package_info(self):\n')
        f.write(f'        self.cpp_info.libs = [{libsum}]\n')
        f.close()

    def executeconanscript(self, buildfolder, arch, stdlib):
        filesfound = 0

        for lib in self.buildconfig.staticliblink:
            filepath = os.path.join(buildfolder, f'lib{lib}.a')
            if os.path.exists(filepath):
                bininfo = BinaryInfo(self.logger, buildfolder, filepath)
                cxxinfo = bininfo.cxx_info_from_binary()
                if (stdlib == "") or (stdlib == "libc++" and not cxxinfo['has_maybecxx11abi']):
                    if arch == "x86" and 'ELF32' in bininfo.readelf_header_details:
                        filesfound+=1
                    elif arch == "x86_64" and 'ELF64' in bininfo.readelf_header_details:
                        filesfound+=1
            else:
                self.logger.debug(f'lib{lib}.a not found')

        for lib in self.buildconfig.sharedliblink:
            filepath = os.path.join(buildfolder, f'lib{lib}.so')
            bininfo = BinaryInfo(self.logger, buildfolder, filepath)
            if (stdlib == "" and 'libstdc++.so' in bininfo.ldd_details) or (stdlib != "" and f'{stdlib}.so' in bininfo.ldd_details):
                if arch == "":
                    filesfound+=1
                elif arch == "x86" and 'ELF32' in bininfo.readelf_header_details:
                    filesfound+=1
                elif arch == "x86_64" and 'ELF64' in bininfo.readelf_header_details:
                    filesfound+=1

        if filesfound != 0:
            if subprocess.call(['./conanexport.sh'], cwd=buildfolder) == 0:
                self.logger.info('Export succesful')
                return c_BuildOk
            else:
                return c_BuildFailed
        else:
            self.logger.info('No binaries found to export')
            return c_BuildFailed

    def executebuildscript(self, buildfolder):
        if subprocess.call(['./build.sh'], cwd=buildfolder) == 0:
            self.logger.info(f'Build succeeded in {buildfolder}')
            return c_BuildOk
        else:
            return c_BuildFailed

    def makebuildhash(self, compiler, options, toolchain, buildos, buildtype, arch, stdver, stdlib, flagscombination):
        hasher = hashlib.sha256()
        flagsstr = '|'.join(x for x in flagscombination)
        hasher.update(bytes(f'{compiler},{options},{toolchain},{buildos},{buildtype},{arch},{stdver},{stdlib},{flagsstr}', 'utf-8'))

        self.logger.info(f'Building {self.libname} for [{compiler},{options},{toolchain},{buildos},{buildtype},{arch},{stdver},{stdlib},{flagsstr}]')

        return compiler + '_' + hasher.hexdigest()

    def get_conan_hash(self, buildfolder):
        self.logger.debug(['conan', 'info', '.'] + self.current_buildparameters)
        conaninfo = subprocess.check_output(['conan', 'info', '-r', 'ceserver', '.'] + self.current_buildparameters, cwd=buildfolder).decode('utf-8', 'ignore')
        self.logger.debug(conaninfo)
        match = CONANINFOHASH_RE.search(conaninfo, re.MULTILINE)
        if match:
            return match[1]
        return None

    def conanproxy_login(self):
        url = f'{conanserver_url}/login'

        login_body = defaultdict(lambda: [])
        login_body['password'] = get_ssm_param('/compiler-explorer/conanpwd')

        request = requests.post(url, data = json.dumps(login_body), headers={"Content-Type": "application/json"})
        if not request.ok:
            self.logger.info(request.text)
            raise RuntimeError(f'Post failure for {url}: {request}')
        else:
            response = json.loads(request.content)
            self.conanserverproxy_token = response['token']

    def save_build_logging(self, builtok, buildfolder):
        if builtok == c_BuildFailed:
            url = f'{conanserver_url}/buildfailed'
        elif builtok == c_BuildOk:
            url = f'{conanserver_url}/buildsuccess'
        else:
            return

        loggingfiles = []
        loggingfiles += glob.glob(buildfolder + '/cecmake*.txt')
        loggingfiles += glob.glob(buildfolder + '/ceconfiglog.txt')
        loggingfiles += glob.glob(buildfolder + '/cemake*.txt')

        logging_data = ""
        for logfile in loggingfiles:
            f = open(logfile, 'r')
            logging_data = logging_data + '\n'.join(f.readlines())
            f.close()

        buildparameters_copy = self.current_buildparameters_obj.copy()
        buildparameters_copy['logging'] = logging_data

        headers={"Content-Type": "application/json", "Authorization": "Bearer " + self.conanserverproxy_token}

        request = requests.post(url, data = json.dumps(buildparameters_copy), headers=headers)
        if not request.ok:
            raise RuntimeError(f'Post failure for {url}: {request}')

    def get_build_annotations(self, buildfolder):
        conanhash = self.get_conan_hash(buildfolder)
        if conanhash == None:
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

    def get_commit_hash(self):
        if os.path.exists(f'{self.sourcefolder}/.git'):
            lastcommitinfo = subprocess.check_output(['git', '-C', self.sourcefolder, 'log', '-1', '--oneline', '--no-color']).decode('utf-8', 'ignore')
            self.logger.debug(lastcommitinfo)
            match = GITCOMMITHASH_RE.match(lastcommitinfo)
            if match:
                return match[1]
            else:
                return self.target_name
        else:
            return self.target_name

    def is_already_uploaded(self, buildfolder):
        annotations = self.get_build_annotations(buildfolder)

        if 'commithash' in annotations:
            commithash = self.get_commit_hash()

            return commithash == annotations['commithash']
        else:
            return False

    def set_as_uploaded(self, buildfolder):
        conanhash = self.get_conan_hash(buildfolder)
        if conanhash == None:
            raise RuntimeError(f'Error determining conan hash in {buildfolder}')

        self.logger.info(f'commithash: {conanhash}')

        annotations = self.get_build_annotations(buildfolder)
        if not 'commithash' in annotations:
            self.upload_builds()
        annotations['commithash'] = self.get_commit_hash()

        for lib in self.buildconfig.staticliblink:
            if os.path.exists(os.path.join(buildfolder, f'lib{lib}.a')):
                bininfo = BinaryInfo(self.logger, buildfolder, os.path.join(buildfolder, f'lib{lib}.a'))
                libinfo = bininfo.cxx_info_from_binary()
                archinfo = bininfo.arch_info_from_binary()
                annotations['cxx11'] = libinfo['has_maybecxx11abi']
                annotations['machine'] = archinfo['elf_machine']
                annotations['osabi'] = archinfo['elf_osabi']

        for lib in self.buildconfig.sharedliblink:
            if os.path.exists(os.path.join(buildfolder, f'lib{lib}.a')):
                bininfo = BinaryInfo(self.logger, buildfolder, os.path.join(buildfolder, f'lib{lib}.a'))
                libinfo = bininfo.cxx_info_from_binary()
                archinfo = bininfo.arch_info_from_binary()
                annotations['cxx11'] = libinfo['has_maybecxx11abi']
                annotations['machine'] = archinfo['elf_machine']
                annotations['osabi'] = archinfo['elf_osabi']

        self.logger.info(annotations)

        headers={"Content-Type": "application/json", "Authorization": "Bearer " + self.conanserverproxy_token}

        url = f'{conanserver_url}/annotations/{self.libname}/{self.target_name}/{conanhash}'
        request = requests.post(url, data = json.dumps(annotations), headers=headers)
        if not request.ok:
            raise RuntimeError(f'Post failure for {url}: {request}')

    def makebuildfor(self, compiler, options, exe, compilerType, toolchain, buildos, buildtype, arch, stdver, stdlib, flagscombination):
        combinedhash = self.makebuildhash(compiler, options, toolchain, buildos, buildtype, arch, stdver, stdlib, flagscombination)

        buildfolder = ""
        if self.buildconfig.build_type == "cmake":
            buildfolder = os.path.join(self.install_context.staging, combinedhash)
            if os.path.exists(buildfolder):
                shutil.rmtree(buildfolder, ignore_errors=True)
            os.makedirs(buildfolder, exist_ok=True)
        else:
            buildfolder = os.path.join(self.install_context.staging, combinedhash)
            if os.path.exists(buildfolder):
                shutil.rmtree(buildfolder, ignore_errors=True)
            shutil.copytree(self.sourcefolder, buildfolder)

        self.logger.debug(f'Buildfolder: {buildfolder}')

        self.writebuildscript(buildfolder, self.sourcefolder, compiler, options, exe, compilerType, toolchain, buildos, buildtype, arch, stdver, stdlib, flagscombination)
        self.writeconanfile(buildfolder)

        if self.is_already_uploaded(buildfolder):
            self.logger.info("Build already uploaded")
            if not self.forcebuild:
                return c_BuildSkipped

        if not self.install_context.dry_run and not self.conanserverproxy_token:
            self.conanproxy_login()

        builtok = self.executebuildscript(buildfolder)
        if builtok == c_BuildOk:
            if not self.install_context.dry_run:
                self.writeconanscript(buildfolder)
                builtok = self.executeconanscript(buildfolder, arch, stdlib)
                if builtok == c_BuildOk:
                    self.needs_uploading += 1
                    self.set_as_uploaded(buildfolder)

        if not self.install_context.dry_run:
            self.save_build_logging(builtok, buildfolder)

        if builtok == c_BuildOk:
            if self.buildconfig.build_type == "cmake":
                self.build_cleanup(buildfolder)
            elif self.buildconfig.build_type == "make":
                subprocess.call(['make', 'clean'], cwd=buildfolder)

        return builtok

    def build_cleanup(self, buildfolder):
        if self.install_context.dry_run:
            self.logger.info(f'Would remove directory {buildfolder} but in dry-run mode')
        else:
            shutil.rmtree(buildfolder, ignore_errors=True)
            self.logger.info(f'Removing {buildfolder}')

    def upload_builds(self):
        if self.needs_uploading > 0:
            self.logger.info('Uploading cached builds')
            subprocess.check_call(['conan', 'upload', f'{self.libname}/{self.target_name}', '--all', '-r=ceserver', '-c'])
            self.logger.debug('Clearing cache to speed up next upload')
            subprocess.check_call(['conan', 'remove', '-f', f'{self.libname}/{self.target_name}'])
            self.needs_uploading = 0

    def makebuild(self, buildfor):
        builds_failed = 0
        builds_succeeded = 0
        builds_skipped = 0

        for compiler in self.compilerprops:
            if buildfor != "" and compiler != buildfor:
                continue

            if 'compilerType' in self.compilerprops[compiler]:
                compilerType = self.compilerprops[compiler]['compilerType']
            else:
                raise RuntimeError(f'Something is wrong with {compiler}')

            exe = self.compilerprops[compiler]['exe']
            options = self.compilerprops[compiler]['options']

            toolchain = self.getToolchainPathFromOptions(options)
            fixedStdver = self.getStdVerFromOptions(options)
            fixedStdlib = self.getStdLibFromOptions(options)

            if not toolchain:
                toolchain = os.path.realpath(os.path.join(os.path.dirname(exe), '..'))

            stdlibs = ['']
            if fixedStdlib:
                self.logger.debug(f'Fixed stdlib {fixedStdlib}')
                stdlibs = [fixedStdlib]
            else:
                if self.buildconfig.build_fixed_stdlib != "":
                    if self.buildconfig.build_fixed_stdlib != "libstdc++":
                        stdlibs = [self.buildconfig.build_fixed_stdlib]
                else:
                    if compilerType == "":
                        self.logger.debug('Gcc-like compiler')
                    elif compilerType == "clang":
                        self.logger.debug('Clang-like compiler')
                        stdlibs = build_supported_stdlib
                    else:
                        self.logger.debug('Some other compiler')

            archs = build_supported_arch

            if self.buildconfig.build_fixed_arch != "":
                if not self.does_compiler_support(exe, compilerType, self.buildconfig.build_fixed_arch, self.compilerprops[compiler]['options']):
                    self.logger.debug(f'Compiler {compiler} does not support fixed arch {self.buildconfig.build_fixed_arch}')
                    return False
                else:
                    archs = [self.buildconfig.build_fixed_arch]

            if not self.does_compiler_support_x86(exe, compilerType, self.compilerprops[compiler]['options']):
                archs = ['']

            stdvers = build_supported_stdver
            if fixedStdver:
                stdvers = [fixedStdver]

            for buildos in build_supported_os:
                for buildtype in build_supported_buildtype:
                    for arch in archs:
                        for stdver in stdvers:
                            for stdlib in stdlibs:
                                for flagscombination in build_supported_flagscollection:
                                    buildstatus = self.makebuildfor(compiler, options, exe, compilerType, toolchain, buildos, buildtype, arch, stdver, stdlib, flagscombination)
                                    if buildstatus == c_BuildOk:
                                        builds_succeeded = builds_succeeded + 1
                                    elif buildstatus == c_BuildSkipped:
                                        builds_skipped = builds_skipped + 1
                                    else:
                                        builds_failed = builds_failed + 1

            if builds_succeeded > 0:
                self.upload_builds()

        return [builds_succeeded, builds_skipped, builds_failed]
