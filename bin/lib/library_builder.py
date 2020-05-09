import re
import os
import hashlib
import shutil
import subprocess
from lib.amazon_properties import *
from lib.library_build_config import *
from collections import defaultdict, ChainMap

build_supported_os = ['Linux']
build_supported_buildtype = ['Debug']
build_supported_arch = ['x86_64', 'x86']
build_supported_stdver = ['']
build_supported_stdlib = ['', 'libc++']
build_supported_flags = ['']
build_supported_flagscollection = [['']]

_propsandlibs = defaultdict(lambda: [])

class LibraryBuilder:
    def __init__(self, logger, language: str, libname: str, target_name: str, sourcefolder: str, install_context, buildconfig: LibraryBuildConfig):
        self.logger = logger
        self.language = language
        self.libname = libname
        self.buildconfig = buildconfig
        self.install_context = install_context
        self.sourcefolder = sourcefolder
        self.target_name = target_name

        if self.language in _propsandlibs:
            [self.compilerprops, self.libraryprops] = _propsandlibs[self.language]
        else:
            [self.compilerprops, self.libraryprops] = get_properties_compilers_and_libraries(self.language, self.logger)
            _propsandlibs[self.language] = [self.compilerprops, self.libraryprops]

        self.completeBuildConfig()

    def completeBuildConfig(self):
        libid = self.libname    # TODO: CE libid might be different from yaml libname

        if 'description' in self.libraryprops[libid]:
            self.buildconfig.description = self.libraryprops[libid]['description']
        if 'name' in self.libraryprops[libid]:
            self.buildconfig.description = self.libraryprops[libid]['name']
        if 'url' in self.libraryprops[libid]:
            self.buildconfig.url = self.libraryprops[libid]['url']
        if 'staticliblink' in self.libraryprops[libid]:
            self.buildconfig.staticliblink = self.libraryprops[libid]['staticliblink'].split(':')
        if 'liblink' in self.libraryprops[libid]:
            self.buildconfig.sharedliblink = self.libraryprops[libid]['liblink'].split(':')

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
        match = re.search("--gcc-toolchain=(\S*)", options)
        if match:
            return match[1]
        else:
            match = re.search("--gxx-name=(\S*)", options)
            if match:
                return os.path.realpath(os.path.join(os.path.dirname(match[1]), ".."))
        return False

    def getStdVerFromOptions(self, options):
        match = re.search("-std=(\S*)", options)
        if match:
            return match[1]
        return False

    def getTargetFromOptions(self, options):
        match = re.search("-target (\S*)", options)
        if match:
            return match[1]
        return False

    def does_compiler_support(self, exe, compilerType, arch, options):
        fixedTarget = self.getTargetFromOptions(options)
        if fixedTarget:
            return fixedTarget == arch

        if compilerType == "":
            output = subprocess.check_output([exe, '--target-help']).decode('utf-8')
        elif compilerType == "clang":
            folder = os.path.dirname(exe)
            llcexe = os.path.join(folder, 'llc')
            if os.path.exists(llcexe):
                try:
                    output = subprocess.check_output([llcexe, '--version']).decode('utf-8')
                except subprocess.CalledProcessError as e:
                    output = e.output.decode('utf-8')
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

    def writebuildscript(self, buildfolder, sourcefolder, compiler, compileroptions, compilerexe, compilerType, toolchain, buildos, buildtype, arch, stdver, stdlib, flagscombination, group):
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
        else:
            libcxx = "libstdc++"

        extraflags = ' '.join(x for x in flagscombination)

        if compilerType == "":
            compilerTypeOrGcc = "gcc"
        else:
            compilerTypeOrGcc = compilerType

        cxx_flags = f'{compileroptions} {archflag} {stdverflag} {stdlibflag} {rpathflags} {extraflags}'

        if len(self.buildconfig.prebuildscript) > 0:
            for line in self.buildconfig.prebuildscript:
                f.write(f'{line}\n')

        if self.buildconfig.build_type == "cmake":
            extracmakeargs = ' '.join(self.buildconfig.extra_cmake_arg)
            cmakeline = f'cmake -DCMAKE_BUILD_TYPE={buildtype} "-DCMAKE_CXX_COMPILER_EXTERNAL_TOOLCHAIN={toolchain}" "-DCMAKE_CXX_FLAGS_DEBUG={cxx_flags}" {extracmakeargs} {sourcefolder}\n'
            self.logger.debug(cmakeline)
            f.write(cmakeline)
        else:
            if os.path.exists(os.path.join(buildfolder, 'Makefile')):
                f.write(f'make clean\n')
            f.write(f'rm *.so*\n')
            f.write(f'rm *.a\n')
            f.write(f'export CXX_FLAGS="{cxx_flags}"\n')
            if self.buildconfig.build_type == "make":
                if os.path.exists(os.path.join(buildfolder, 'configure')):
                    f.write(f'./configure\n')

        if len(self.buildconfig.staticliblink) != 0:
            for lib in self.buildconfig.staticliblink:
                f.write(f'make {lib}\n')

        if len(self.buildconfig.sharedliblink) != 0:
            for lib in self.buildconfig.sharedliblink:
                f.write(f'make {lib}\n')

        if len(self.buildconfig.staticliblink) != 0:
            f.write(f'libsfound=$(find . -iname \'lib*.a\')\n')
        elif len(self.buildconfig.sharedliblink) != 0:
            f.write(f'libsfound=$(find . -iname \'lib*.so*\')\n')

        f.write(f'if [ "$libsfound" = "" ]; then\n')
        f.write(f'  make all\n')
        f.write(f'fi\n')

        for lib in self.buildconfig.staticliblink:
            f.write(f'find . -iname \'lib{lib}.a\' -type f -exec mv {{}} . \;\n')

        for lib in self.buildconfig.sharedliblink:
            f.write(f'find . -iname \'lib{lib}*.so*\' -type f,l -exec mv {{}} . \;\n')

        f.close()
        subprocess.check_call(['/bin/chmod','+x', scriptfile])

        scriptfile = os.path.join(buildfolder, "conanexport.sh")

        f = open(scriptfile, 'w')
        f.write('#!/bin/sh\n\n')
        f.write(f'conan export-pkg . {self.libname}/{self.target_name} -f -s os={buildos} -s build_type={buildtype} -s compiler={compilerTypeOrGcc} -s compiler.version={compiler} -s compiler.libcxx={libcxx} -s arch={arch} -s stdver={stdver} -s "flagcollection={extraflags}"\n')
        f.write(f'conan upload {self.libname}/{self.target_name} --all -r=ceserver -c\n')
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
        f.write(f'    settings = "os", "compiler", "build_type", "arch", "stdver", "flagcollection"\n')
        f.write(f'    description = "{self.buildconfig.description}"\n')
        f.write(f'    url = "{self.buildconfig.url}"\n')
        f.write(f'    license = "None"\n')
        f.write(f'    author = "None"\n')
        f.write(f'    topics = None\n')
        f.write(f'    def package(self):\n')
        for lib in self.buildconfig.staticliblink:
            f.write(f'        self.copy("lib{lib}.a", dst="lib", keep_path=False)\n')
        for lib in self.buildconfig.sharedliblink:
            f.write(f'        self.copy("lib{lib}.so*", dst="lib", keep_path=False)\n')
        f.write(f'    def package_info(self):\n')
        f.write(f'        self.cpp_info.libs = [{libsum}]\n')
        f.close()

    def follow_so_readelf(self, buildfolder, filepath):
        if not os.path.exists(filepath):
            return False

        try:
            details = subprocess.check_output(['readelf', '-h', filepath]).decode('utf-8')
            try:
                details += subprocess.check_output(['ldd', filepath]).decode('utf-8')
            finally:
                self.logger.debug(details)
                return details
        except subprocess.CalledProcessError:
            f = open(filepath, 'r')
            lines = f.readlines()
            f.close()
            self.logger.debug(lines)
            match = re.match("INPUT \((\S*)\)", '\n'.join(lines))
            if match:
                return self.follow_so_readelf(buildfolder, os.path.join(buildfolder, match[1]))
            return False

    def executeconanscript(self, buildfolder, arch, stdlib):
        filesfound = 0

        for lib in self.buildconfig.staticliblink:
            if os.path.exists(os.path.join(buildfolder, f'lib{lib}.a')):
                filesfound+=1

        for lib in self.buildconfig.sharedliblink:
            filepath = os.path.join(buildfolder, f'lib{lib}.so')
            details = self.follow_so_readelf(buildfolder, filepath)
            if details:
                if (stdlib == "" and 'libstdc++.so' in details) or (stdlib != "" and f'{stdlib}.so' in details):
                    if arch == "":
                        filesfound+=1
                    elif arch == "x86" and 'ELF32' in details:
                        filesfound+=1
                    elif arch == "x86_64" and 'ELF64' in details:
                        filesfound+=1

        if filesfound != 0:
            if subprocess.call(['./conanexport.sh'], cwd=buildfolder) == 0:
                self.logger.info(f'Upload succeeded')
                return True
            else:
                return False
        else:
            self.logger.info(f'No binaries found to upload')
            return False

    def executebuildscript(self, buildfolder):
        if subprocess.call(['./build.sh'], cwd=buildfolder) == 0:
            self.logger.info(f'Build succeeded in {buildfolder}')
            return True
        else:
            return False

    def makebuildhash(self, compiler, options, exe, compilerType, toolchain, buildos, buildtype, arch, stdver, stdlib, flagscombination, group):
        hasher = hashlib.sha256()
        flagsstr = '|'.join(x for x in flagscombination)
        hasher.update(bytes(f'{compiler},{options},{toolchain},{buildos},{buildtype},{arch},{stdver},{stdlib},{flagsstr}', 'utf-8'))

        self.logger.info(f'Building {self.libname} for [{compiler},{options},{toolchain},{buildos},{buildtype},{arch},{stdver},{stdlib},{flagsstr}]')

        return compiler + '_' + hasher.hexdigest()

    def makebuildfor(self, compiler, options, exe, compilerType, toolchain, buildos, buildtype, arch, stdver, stdlib, flagscombination, group):
        combinedhash = self.makebuildhash(compiler, options, exe, compilerType, toolchain, buildos, buildtype, arch, stdver, stdlib, flagscombination, group)

        buildfolder = ""
        if self.buildconfig.build_type == "cmake":
            buildfolder = os.path.join(self.install_context.staging, combinedhash)
            os.makedirs(buildfolder, exist_ok=True)
        else:
            buildfolder = self.sourcefolder

        self.logger.debug(f'Buildfolder: {buildfolder}')

        self.writebuildscript(buildfolder, self.sourcefolder, compiler, options, exe, compilerType, toolchain, buildos, buildtype, arch, stdver, stdlib, flagscombination, group)
        self.writeconanfile(buildfolder)
        builtok = self.executebuildscript(buildfolder)
        if builtok:
            if not self.install_context.dry_run:
                builtok = self.executeconanscript(buildfolder, arch, stdlib)

        if builtok:
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

    def makebuild(self, buildfor):
        builds_failed = 0
        builds_succeeded = 0

        for compiler in self.compilerprops:
            if buildfor != "" and compiler != buildfor:
                continue

            if 'compilerType' in self.compilerprops[compiler]:
                compilerType = self.compilerprops[compiler]['compilerType']
            else:
                raise RuntimeError(f'Something is wrong with {compiler}')

            exe = self.compilerprops[compiler]['exe']
            options = self.compilerprops[compiler]['options']
            group = self.compilerprops[compiler]['group']

            toolchain = self.getToolchainPathFromOptions(options)
            fixedStdver = self.getStdVerFromOptions(options)

            if not toolchain:
                toolchain = os.path.realpath(os.path.join(os.path.dirname(exe), '..'))

            stdlibs = ['']

            if self.buildconfig.build_fixed_stdlib != "":
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
                                    if self.makebuildfor(compiler, options, exe, compilerType, toolchain, buildos, buildtype, arch, stdver, stdlib, flagscombination, group):
                                        builds_succeeded = builds_succeeded + 1
                                    else:
                                        builds_failed = builds_failed + 1

        return builds_failed == 0
