import os
import yaml
from pathlib import Path
from lib.rust_crates import TopRustCrates

from lib.config_safe_loader import ConfigSafeLoader

class LibraryYaml:
    def __init__(self, yaml_dir):
        self.yaml_dir = yaml_dir
        self.yaml_path = Path(os.path.join(self.yaml_dir, 'libraries.yaml'))
        self.load()

    def load(self):
        with self.yaml_path.open(encoding='utf-8', mode="r") as yaml_file:
            self.yaml_doc = yaml.load(yaml_file, Loader=ConfigSafeLoader)

    def save(self):
        with self.yaml_path.open(encoding='utf-8', mode="w") as yaml_file:
            yaml.dump(self.yaml_doc, yaml_file)

    def reformat(self):
        self.save()

    def add_rust_crate(self, libid, libversion):
        libraries_for_language = self.yaml_doc['libraries']['rust']
        if libid in libraries_for_language:
            if not libversion in libraries_for_language[libid]['targets']:
                libraries_for_language[libid]['targets'].append(libversion)
        else:
            libraries_for_language[libid] = dict(
                type = 'cratesio',
                build_type = 'cargo',
                targets = [libversion]
            )

    def add_top100_rust_crates(self):
        cratelisting = TopRustCrates()
        crates = cratelisting.list(10)
        for crate in crates:
            self.add_rust_crate(crate['libid'], crate['libversion'])
