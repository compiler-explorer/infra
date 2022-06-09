import urllib.request
import json

class RustCrate:
    def __init__(self, libid, libversion):
        self.libid = libid
        self.version = libversion
        self.cratesio = 'https://crates.io'
        self.crateinfo = self.LoadCrateInfo()

    def LoadCrateInfo(self):
        url = f'{self.cratesio}/api/v1/crates/{self.libid}/{self.version}'
        response = urllib.request.urlopen(url)
        data = json.loads(response.read())
        return data

    def GetDownloadUrl(self):
        download_path = self.crateinfo['version']['dl_path']
        download_url = f'{self.cratesio}{download_path}'

        return download_url

class TopRustCrates:
    def __init__(self):
        self.cratesio = 'https://crates.io'

    def list(self, limit = 100):
        url = f'{self.cratesio}/api/v1/crates?page=1&per_page={limit}&sort=downloads'
        response = urllib.request.urlopen(url)
        data = json.loads(response.read())

        crates = []

        for crate in data['crates']:
            crates.append(dict(
                libid = crate['id'],
                libversion = crate['max_stable_version']))

        return crates
