import hashlib
import tarfile
import urllib.parse

from base64 import b64encode
from concurrent import futures
from datetime import datetime
from tempfile import mkdtemp
import os
import shutil
import logging
from pathlib import Path

from lib.amazon import botocore, s3_client, force_lazy_init

logger = logging.getLogger('ce-cdn')

def read_file_chunked(fobj, chunk_size=128*1024):
    b = bytearray(chunk_size)
    mv = memoryview(b)

    for n in iter(lambda : fobj.readinto(mv), 0):
        yield mv[:n]


def hash_fileobj(fobj, hash_type):
    h = hash_type()
    for chnk in read_file_chunked(fobj):
        h.update(chnk)
    return h


def hash_file_for_s3(f):
    with open(f['path'], 'rb') as fobj:
        sha256 = hash_fileobj(fobj, hashlib.sha256).digest()
        sha256 = b64encode(sha256).decode()
        return dict(hash=sha256, **f)


def get_directory_contents(basedir):
    for f in Path(basedir).rglob('*'):
        name = f.relative_to(basedir).as_posix()
        yield dict(name=name, path=f)


class DeploymentJob(object):
    tmpdir = None

    def __init__(self, tar_file_path, bucket_name, bucket_path='', version=None, max_workers=None):
        self.tar_file_path = tar_file_path
        self.bucket_name = bucket_name
        self.bucket_path = Path(bucket_path)
        self.version = version
        self.max_workers = max_workers or os.cpu_count() or 1
        self.deploydate = datetime.utcnow().isoformat(timespec='seconds')

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.__cleanup_tempdir()

    def __unpack_tar(self):
        # ensure temp dir exists
        if not self.tmpdir:
            self.tmpdir = mkdtemp()

        # unpack tar contents
        logger.debug(f'unpacking "{self.tar_file_path}" into "{self.tmpdir}"')
        with tarfile.open(self.tar_file_path) as tar:
            tar.extractall(self.tmpdir)

        return list(get_directory_contents(self.tmpdir))

    def __cleanup_tempdir(self):
        # bail if tmpdir is not set
        if not self.tmpdir:
            return

        try:
            # recursively remove directory tree
            shutil.rmtree(self.tmpdir)

            # only clear tmpdir if above succeeds
            # maybe a file is still open or something
            # and we can try again later in case of failure
            self.tmpdir = None
        except:
            logger.exception(f'failure to cleanup temp directory "{self.tmpdir}"')

    def __get_bucket_path(self, key):
        return (self.bucket_path / key).as_posix()

    def __s3_head_object(self, key, **kwargs):
        try:
            return s3_client.head_object(
                Bucket=self.bucket_name,
                Key=self.__get_bucket_path(key),
                **kwargs
            )
        except botocore.exceptions.ClientError as e:
            if e.response['Error']['Code'] == "404":
                return None
            raise

    def __s3_upload_fileobj(self, fileobj, key, **kwargs):
        return s3_client.upload_fileobj(
            fileobj,
            self.bucket_name,
            self.__get_bucket_path(key),
            **kwargs
        )

    def __s3_upload_file(self, filepath, key, **kwargs):
        return s3_client.upload_file(
            filepath,
            self.bucket_name,
            self.__get_bucket_path(key),
            **kwargs
        )

    def __s3_get_object_tagging(self, key):
        resp = s3_client.get_object_tagging(
            Bucket=self.bucket_name,
            Key=self.__get_bucket_path(key)
        )

        tags = dict()
        for t in resp['TagSet']:
            tags[t['Key']] = t['Value']
        return tags

    def __s3_put_object_tagging(self, key, tags, **kwargs):
        tagset = list([dict(Key=k, Value=v) for k,v in tags.items()])

        return s3_client.put_object_tagging(
            Bucket=self.bucket_name,
            Key=self.__get_bucket_path(key),
            Tagging=dict(TagSet=tagset),
            **kwargs
        )

    def _check_s3_hash(self, file):
        ret = dict(exists=False, mismatch=False, s3hash=None, **file)

        resp = self.__s3_head_object(ret['name'])
        if resp:
            ret['exists'] = True
            ret['s3hash'] = resp.get('Metadata', {}).get('sha256')
            ret['mismatch'] = ret['s3hash'] != ret['hash']

        return ret

    def _upload_file(self, file):
        # upload file to s3
        self.__s3_upload_file(
            str(file['path']),
            file['name'],
            ExtraArgs=dict(Metadata=dict(sha256=file['hash']))
        )

        tags = dict(FirstDeployDate=self.deploydate, LastDeployDate=self.deploydate)
        if self.version:
            tags['FirstVersionSeen'] = tags['LastVersionSeen'] = str(self.version)

        # attach s3 tags
        self.__s3_put_object_tagging(file['name'], tags)
        return file

    def _update_tags(self, file):
        # get existing tags
        tags = self.__s3_get_object_tagging(file['name'])

        # update tag values
        tags['LastDeployDate'] = self.deploydate
        if self.version:
            tags['LastVersionSeen'] = str(self.version)

        # store updated tags to s3
        self.__s3_put_object_tagging(file['name'], tags)
        return file

    def run(self):
        logger.debug(f'running with {self.max_workers} workers')

        # work around race condition with parallel lazy init of boto3
        force_lazy_init(s3_client)

        files = self.__unpack_tar()

        with futures.ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            # calculate hashes for all the files
            files = list(executor.map(hash_file_for_s3, files))

            files_to_update = []
            files_to_upload = []
            files_with_mismatch = []

            # check for existing files on s3 and compare hashes
            for f in executor.map(self._check_s3_hash, files):
                if f['exists']:
                    if f['mismatch']:
                        files_with_mismatch.append(f)
                    else:
                        files_to_update.append(f)
                else:
                    files_to_upload.append(f)

            if files_with_mismatch:
                logger.error(f'{len(files_with_mismatch)} files have mismatching hashes')
                for f in files_with_mismatch:
                    logger.error(f"{f['name']}: expected hash {f['hash']} != {f['s3hash']}")

                logger.error('aborting cdn deployment due to errors')
                return False

            logger.info(f"will update {len(files_to_update)} file tag{'s' if len(files_to_update) != 1 else ''}")
            logger.info(f"will upload {len(files_to_upload)} new file{'s' if len(files_to_upload) != 1 else ''}")

            for f in executor.map(self._upload_file, files_to_upload):
                logger.debug(f"uploaded {f['name']}")

            for f in executor.map(self._update_tags, files_to_update):
                logger.debug(f"updated tags on {f['name']}")

            return True
