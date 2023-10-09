from lib.amazon import dynamodb_client
from lib.amazon_properties import get_properties_compilers_and_libraries


class NightlyVersions:
    version_table_name: str = "nightly-version"
    exe_table_name: str = "nightly-exe"

    def __init__(self, logger):
        self.logger = logger
        [self.cpp, _] = get_properties_compilers_and_libraries("c++", logger)
        [self.c, _] = get_properties_compilers_and_libraries("c", logger)
        [self.fortran, _] = get_properties_compilers_and_libraries("fortran", logger)

    def as_c_compiler(self, exe: str):
        if exe.endswith("/g++"):
            return exe[:-3] + "gcc"
        if exe.endswith("/clang++"):
            return exe[:-2]
        return exe

    def as_fortran_compiler(self, exe: str):
        if exe.endswith("/g++"):
            return exe[:-3] + "gfortran"
        return exe

    def get_compiler_ids(self, exe: str):
        ids = set()

        for compiler_id in self.cpp:
            compiler = self.cpp[compiler_id]
            if exe == compiler["exe"]:
                ids.add(compiler_id)

        cexe = self.as_c_compiler(exe)
        for compiler_id in self.c:
            compiler = self.c[compiler_id]
            if cexe == compiler["exe"]:
                ids.add(compiler_id)

        fortranexe = self.as_fortran_compiler(exe)
        for compiler_id in self.fortran:
            compiler = self.fortran[compiler_id]
            if fortranexe == compiler["exe"]:
                ids.add(compiler_id)

        return ids

    def update_version(self, exe: str, modified: str, version: str, full_version: str):
        compiler_ids = self.get_compiler_ids(exe)
        dynamodb_client.put_item(
            TableName=self.version_table_name,
            Item={
                "exe": {"S": exe},
                "modified": {"N": modified},
                "version": {"S": version},
                "full_version": {"S": full_version},
            },
        )

        for compiler_id in compiler_ids:
            dynamodb_client.put_item(
                TableName=self.exe_table_name,
                Item={
                    "id": {"S": compiler_id},
                    "exe": {"S": exe},
                },
            )

        return

    def get_version(self, exe: str):
        result = dynamodb_client.get_item(
            TableName=self.version_table_name,
            Key={"exe": {"S": exe}},
            ConsistentRead=True,
        )
        item = result.get("Item")
        if item:
            return {
                "exe": item["exe"]["S"],
                "version": item["version"]["S"],
                "full_version": item["full_version"]["S"],
                "modified": item["modified"]["N"],
            }
        else:
            return None
