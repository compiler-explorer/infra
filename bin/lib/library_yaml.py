import os
import yaml
from pathlib import Path

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
