from enum import Enum
from typing import Optional, Tuple

from attr import dataclass


@dataclass(frozen=True)
class Hash:
    hash: str

    def __str__(self) -> str:
        return f"{str(self.hash[:6])}..{str(self.hash[-6:])}"


class VersionSource(Enum):
    value: Tuple[int, str]
    TRAVIS = (0, "tr")
    GITHUB = (1, "gh")

    def __lt__(self, other):
        return self.value < other.value

    def __str__(self):
        return f"{self.value[1]}"


@dataclass(frozen=True, repr=False)
class Version:
    source: VersionSource
    number: int

    @staticmethod
    def from_string(version_str: str, assumed_source: VersionSource = VersionSource.GITHUB):
        if "-" not in version_str:
            return Version(assumed_source, int(version_str))
        source, num = version_str.split("-")
        for possible_source in list(VersionSource):
            if possible_source.value[1] == source:
                return Version(possible_source, int(num))
        raise RuntimeError(f"Unknown source {source}")

    def __str__(self):
        return f"{self.source}-{self.number}"

    def __repr__(self):
        return str(self)


@dataclass
class Release:
    version: Version
    branch: str
    key: str
    info_key: str
    size: int
    hash: Hash
    static_key: Optional[str] = None
