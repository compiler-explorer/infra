import os
import yaml

from pathlib import Path
from typing import List

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
        if not 'rust' in self.yaml_doc['libraries']:
            self.yaml_doc['libraries']['rust'] = dict()

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

    def get_ce_properties_for_rust_libraries(self):
        all_ids: List[str] = []
        properties_txt = ''

        libraries_for_language = self.yaml_doc['libraries']['rust']
        for libid in libraries_for_language:
            all_ids.append(libid)

            all_libver_ids: List[str] = []

            for libver in libraries_for_language[libid]['targets']:
                all_libver_ids.append(libver.replace('.', ''))

            libverprops = f'libs.{libid}.name={libid}\n'
            libverprops += f'libs.{libid}.url=https://crates.io/crates/{libid}\n'
            libverprops += f'libs.{libid}.versions='
            libverprops += ':'.join(all_libver_ids) + '\n'

            for libver in libraries_for_language[libid]['targets']:
                libverid = libver.replace('.', '')
                libverprops += f'libs.{libid}.versions.{libverid}.version={libver}\n'
                underscore_lib = libid.replace('-', '_')
                libverprops += f'libs.{libid}.versions.{libverid}.path=lib{underscore_lib}.rlib\n'

            properties_txt += libverprops + '\n'

        header_properties_txt = 'libs=' + ':'.join(all_ids) + '\n\n'

        return header_properties_txt + properties_txt

    def add_top_rust_crates(self):
        cratelisting = TopRustCrates()
        crates = cratelisting.list(100)
        for crate in crates:
            self.add_rust_crate(crate['libid'], crate['libversion'])
