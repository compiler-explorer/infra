from lib.amazon_properties import get_properties_compilers_and_libraries

class CompilerVersions:
    def __init__(self, logger):
        self.logger = logger
        [self.compilerprops, _] = get_properties_compilers_and_libraries("c++", self.logger)

    def getIdsForExePath(self, path):
        ids = []
        for compiler in self.compilerprops:
            if compiler.exe.includes(path):
                ids += [compiler.id]
        return ids

    def list(self, installables):
        installed = dict()
        for installable in installables:
            installed[installable.path] = self.getIdsForExePath(installable.path)
        return installed
