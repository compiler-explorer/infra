import re
import os
import subprocess
from collections import defaultdict

SYMBOLLINE_RE = re.compile(r'^\s*(\d*):\s[0-9a-f]*\s*(\d*)\s(\w*)\s*(\w*)\s*(\w*)\s*([\w|\d]*)\s?([\w\.]*)?$', re.MULTILINE)
SO_STRANGE_SYMLINK = re.compile(r'INPUT \((\S*)\)')

ELF_CLASS_RE = re.compile(r'^\s*Class:\s*(.*)$', re.MULTILINE)
ELF_OSABI_RE = re.compile(r'^\s*OS\/ABI:\s*(.*)$', re.MULTILINE)
ELF_MACHINE_RE = re.compile(r'^\s*Machine:\s*(.*)$', re.MULTILINE)

sym_grp_num = 0
sym_grp_val = 1
sym_grp_type = 2
sym_grp_bind = 3
sym_grp_vis = 4
sym_grp_ndx = 5
sym_grp_name = 6

class BinaryInfo:
    def __init__(self, logger, buildfolder, filepath):
        self.logger = logger

        self.buildfolder = buildfolder
        self.filepath = filepath

        self.readelf_header_details = ''
        self.readelf_symbols_details = ''
        self.ldd_details = ''

        self.follow_and_readelf()
        self.read_symbols_from_binary()

    def follow_and_readelf(self):
        self.logger.debug('Readelf on ' + self.filepath)
        if not os.path.exists(self.filepath):
            return False

        try:
            self.readelf_header_details = subprocess.check_output(['readelf', '-h', self.filepath]).decode('utf-8', 'replace')
            self.readelf_symbols_details = subprocess.check_output(['readelf', '-W', '-s', self.filepath]).decode('utf-8', 'replace')
            if ".so" in self.filepath:
                self.ldd_details = subprocess.check_output(['ldd', self.filepath]).decode('utf-8', 'replace')
        except subprocess.CalledProcessError:
            f = open(self.filepath, 'r')
            lines = f.readlines()
            f.close()

            match = SO_STRANGE_SYMLINK.match('\n'.join(lines))
            if match:
                self.filepath = os.path.join(self.buildfolder, match[1])
                return self.follow_and_readelf()
            return False

    def read_symbols_from_binary(self):
        self.required_symbols = set()
        self.implemented_symbols = set()

        symbollinematches = SYMBOLLINE_RE.findall(self.readelf_symbols_details)
        if symbollinematches:
            for line in symbollinematches:
                if len(line) == 7 and line[sym_grp_name]:
                    if line[sym_grp_ndx] == 'UND':
                        self.required_symbols.add(line[sym_grp_name])
                    else:
                        self.implemented_symbols.add(line[sym_grp_name])
            return True
        else:
            return False

    def symbol_maybe_cxx11abi(self, symbol):
        return 'cxx11' in symbol

    def set_maybe_cxx11abi(self, symbolset):
        for symbol in symbolset:
            if self.symbol_maybe_cxx11abi(symbol):
                return True
        return False

    def cxx_info_from_binary(self):
        info = defaultdict(lambda: [])
        info['has_personality'] = set(['__gxx_personality_v0']).issubset(self.required_symbols)
        info['has_exceptions'] = set(['_Unwind_Resume']).issubset(self.required_symbols)
        info['has_maybecxx11abi'] = self.set_maybe_cxx11abi(self.implemented_symbols)

        return info

    def arch_info_from_binary(self):
        info = defaultdict(lambda: [])
        info['elf_class'] = ''
        info['elf_osabi'] = ''
        info['elf_machine'] = ''

        matches = ELF_CLASS_RE.findall(self.readelf_header_details)
        for match in matches:
            info['elf_class'] = match
            break

        matches = ELF_OSABI_RE.findall(self.readelf_header_details)
        for match in matches:
            info['elf_osabi'] = match
            break

        matches = ELF_MACHINE_RE.findall(self.readelf_header_details)
        for match in matches:
            info['elf_machine'] = match
            break

        return info
