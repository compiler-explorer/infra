import re
import subprocess
from collections import defaultdict
from pathlib import Path
from typing import Dict, Any, Iterable

SYMBOLLINE_RE = re.compile(r'^\s*(\d*):\s[0-9a-f]*\s*(\d*)\s(\w*)\s*(\w*)\s*(\w*)\s*([\w|\d]*)\s?([\w\.]*)?$',
                           re.MULTILINE)
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

        self.buildfolder = Path(buildfolder)
        self.filepath = Path(filepath)

        self.readelf_header_details = ''
        self.readelf_symbols_details = ''
        self.ldd_details = ''

        self._follow_and_readelf()
        self._read_symbols_from_binary()

    def _follow_and_readelf(self) -> None:
        self.logger.debug('Readelf on %s', self.filepath)
        if not self.filepath.exists():
            return

        try:
            self.readelf_header_details = subprocess.check_output(
                ['readelf', '-h', str(self.filepath)]).decode('utf-8', 'replace')
            self.readelf_symbols_details = subprocess.check_output(
                ['readelf', '-W', '-s', str(self.filepath)]).decode('utf-8', 'replace')
            if ".so" in self.filepath.name:
                self.ldd_details = subprocess.check_output(['ldd', str(self.filepath)]).decode('utf-8', 'replace')
        except subprocess.CalledProcessError:
            match = SO_STRANGE_SYMLINK.match(Path(self.filepath).read_text(encoding='utf-8'))
            if match:
                self.filepath = self.buildfolder / match[1]
                self._follow_and_readelf()

    def _read_symbols_from_binary(self) -> None:
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

    @staticmethod
    def symbol_maybe_cxx11abi(symbol: str) -> bool:
        return 'cxx11' in symbol

    def set_maybe_cxx11abi(self, symbolset: Iterable[str]) -> bool:
        return any(self.symbol_maybe_cxx11abi(s) for s in symbolset)

    def cxx_info_from_binary(self) -> Dict[str, Any]:
        info: Dict[str, Any] = defaultdict(lambda: [])
        info['has_personality'] = {'__gxx_personality_v0'}.issubset(self.required_symbols)
        info['has_exceptions'] = {'_Unwind_Resume'}.issubset(self.required_symbols)
        info['has_maybecxx11abi'] = self.set_maybe_cxx11abi(self.implemented_symbols)

        return info

    def arch_info_from_binary(self) -> Dict[str, Any]:
        info: Dict[str, Any] = defaultdict(lambda: [])
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
