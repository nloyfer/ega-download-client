import concurrent.futures
import logging
import logging.handlers
import math
import os
import sys
import time
import urllib

import htsget
import psutil
from tqdm import tqdm

from pyega3.utils import md5, get_fname_md5, merge_bin_files_on_disk

DOWNLOAD_FILE_SLICE_CHUNK_SIZE = 32 * 1024


class DataFile:
    TEMPORARY_FILES_SHOULD_BE_DELETED = False

    def __init__(self, data_client, file_id,
                 display_file_name=None,
                 file_name=None,
                 size=None,
                 unencrypted_checksum=None):
        self.data_client = data_client
        self.id = file_id

        self.temporary_files = set()

        self._display_file_name = display_file_name
        self._file_name = file_name
        self._file_size = size
        self._unencrypted_checksum = unencrypted_checksum

    def load_metadata(self):
        res = self.data_client.get_json(f"/metadata/files/{self.id}")

        if res['displayFileName'] is None or res['unencryptedChecksum'] is None:
            raise RuntimeError(f"Metadata for file id '{self.id}' could not be retrieved")

        self._display_file_name = res['displayFileName']
        self._file_name = res['fileName']
        self._file_size = res['fileSize']
        self._unencrypted_checksum = res['unencryptedChecksum']

    @property
    def display_name(self):
        if self._display_file_name is None:
            self.load_metadata()
        return self._display_file_name

    @property
    def name(self):
        if self._file_name is None:
            self.load_metadata()
        return self._file_name

    @property
    def size(self):
        if self._file_size is None:
            self.load_metadata()
        return self._file_size

    @property
    def unencrypted_checksum(self):
        if self._unencrypted_checksum is None:
            self.load_metadata()
        return self._unencrypted_checksum

    @staticmethod
    def print_local_file_info(prefix_str, file, md5):
        logging.info(f"{prefix_str}'{os.path.abspath(file)}'({os.path.getsize(file)} bytes, md5={md5})")

    def download_file(self, output_file, num_connections=1, key=None):
        """Download an individual file"""

        if key is not None:
            raise ValueError('key parameter: encrypted downloads are not supported yet')

        file_size = self.size
        check_sum = self.unencrypted_checksum
        options = {}

        if key is None:
            options["destinationFormat"] = "plain"
            file_size -= 16  # 16 bytes IV not necesary in plain mode

        if os.path.exists(output_file) and md5(output_file, file_size) == check_sum:
            DataFile.print_local_file_info('Local file exists:', output_file, check_sum)
            return

        num_connections = max(num_connections, 1)
        num_connections = min(num_connections, 128)

        if file_size < 100 * 1024 * 1024:
            num_connections = 1

        logging.info(f"Download starting [using {num_connections} connection(s)]...")

        chunk_len = math.ceil(file_size / num_connections)

        with tqdm(total=int(file_size), unit='B', unit_scale=True) as pbar:
            params = [
                (output_file, chunk_start_pos, min(chunk_len, file_size - chunk_start_pos), options, pbar)
                for chunk_start_pos in range(0, file_size, chunk_len)]

            results = []
            with concurrent.futures.ThreadPoolExecutor(max_workers=num_connections) as executor:
                for part_file_name in executor.map(self.download_file_slice_, params):
                    results.append(part_file_name)

            pbar.close()

            downloaded_file_total_size = sum(os.path.getsize(f) for f in results)
            if downloaded_file_total_size == file_size:
                merge_bin_files_on_disk(output_file, results, downloaded_file_total_size)

        not_valid_server_md5 = len(str(check_sum or '')) != 32

        logging.info("Calculating md5 (this operation can take a long time depending on the file size)")

        received_file_md5 = md5(output_file, file_size)

        logging.info("Verifying file checksum")

        if received_file_md5 == check_sum or not_valid_server_md5:
            DataFile.print_local_file_info('Saved to : ', output_file, check_sum)
            if not_valid_server_md5:
                logging.info(
                    f"WARNING: Unable to obtain valid MD5 from the server(recived:{check_sum})."
                    f" Can't validate download. Contact EGA helpdesk")
            with open(get_fname_md5(output_file), 'wb') as f:  # save good md5 in aux file for future re-use
                f.write(received_file_md5.encode())
        else:
            os.remove(output_file)
            raise Exception(f"Download process expected md5 value '{check_sum}' but got '{received_file_md5}'")

    def download_file_slice_(self, args):
        return self.download_file_slice(*args)

    def download_file_slice(self, file_name, start_pos, length, options=None, pbar=None):
        if start_pos < 0:
            raise ValueError("start : must be positive")
        if length <= 0:
            raise ValueError("length : must be positive")

        path = f"/files/{self.id}"
        if options is not None:
            path += '?' + urllib.parse.urlencode(options)

        file_name += f'-from-{str(start_pos)}-len-{str(length)}.slice'
        self.temporary_files.add(file_name)

        existing_size = os.stat(file_name).st_size if os.path.exists(file_name) else 0
        if existing_size > length:
            os.remove(file_name)
        if pbar:
            pbar.update(existing_size)

        if existing_size == length:
            return file_name

        with self.data_client.get_stream(path,
                                         {'Range': f'bytes={start_pos + existing_size}-{start_pos + length - 1}'}) as r:
            with open(file_name, 'ba') as file_out:
                for chunk in r.iter_content(DOWNLOAD_FILE_SLICE_CHUNK_SIZE):
                    file_out.write(chunk)
                    if pbar:
                        pbar.update(len(chunk))

        total_received = os.path.getsize(file_name)
        if total_received != length:
            raise Exception(f"Slice error: received={total_received}, requested={length}, file='{file_name}'")

        return file_name

    @staticmethod
    def is_genomic_range(genomic_range_args):
        if not genomic_range_args:
            return False
        return genomic_range_args[0] is not None or genomic_range_args[1] is not None

    def generate_output_filename(self, folder, genomic_range_args):
        file_name = self.display_name
        ext_to_remove = ".cip"
        if file_name.endswith(ext_to_remove):
            file_name = file_name[:-len(ext_to_remove)]
        name, ext = os.path.splitext(os.path.basename(file_name))

        genomic_range = ''
        if DataFile.is_genomic_range(genomic_range_args):
            genomic_range = "_genomic_range_" + (genomic_range_args[0] or genomic_range_args[1])
            genomic_range += '_' + (str(genomic_range_args[2]) or '0')
            genomic_range += '_' + (str(genomic_range_args[3]) or '')
            format_ext = '.' + (genomic_range_args[4] or '').strip().lower()
            if format_ext != ext and len(format_ext) > 1:
                ext += format_ext

        ret_val = os.path.join(folder, self.id, name + genomic_range + ext)
        logging.debug(f"Output file:'{ret_val}'")
        return ret_val

    @staticmethod
    def print_local_file_info_genomic_range(prefix_str, file, gr_args):
        logging.info(
            f"{prefix_str}'{os.path.abspath(file)}'({os.path.getsize(file)} bytes, referenceName={gr_args[0]},"
            f" referenceMD5={gr_args[1]}, start={gr_args[2]}, end={gr_args[3]}, format={gr_args[4]})"
        )

    def download_file_retry(self, num_connections, output_file, genomic_range_args, max_retries, retry_wait, key=None):
        if self.name.endswith(".gpg"):
            logging.info(
                "GPG files are not supported, please use the Java client"
                " - https://ega-archive.org/download/using-ega-download-client")
            return

        logging.info(f"File Id: '{self.id}'({self.size} bytes).")

        if output_file is None:
            output_file = self.generate_output_filename(os.getcwd(), genomic_range_args)
        dir = os.path.dirname(output_file)
        if not os.path.exists(dir) and len(dir) > 0:
            os.makedirs(dir)

        hdd = psutil.disk_usage(os.getcwd())
        logging.info(f"Total space : {hdd.total / (2 ** 30):.2f} GiB")
        logging.info(f"Used space : {hdd.used / (2 ** 30):.2f} GiB")
        logging.info(f"Free space : {hdd.free / (2 ** 30):.2f} GiB")

        if DataFile.is_genomic_range(genomic_range_args):
            with open(output_file, 'wb') as output:
                htsget.get(
                    f"{self.data_client.htsget_url}/files/{self.id}",
                    output,
                    reference_name=genomic_range_args[0], reference_md5=genomic_range_args[1],
                    start=genomic_range_args[2], end=genomic_range_args[3],
                    data_format=genomic_range_args[4],
                    max_retries=sys.maxsize if max_retries < 0 else max_retries,
                    retry_wait=retry_wait,
                    bearer_token=self.data_client.auth_client.token)
            DataFile.print_local_file_info_genomic_range('Saved to : ', output_file, genomic_range_args)
            return

        done = False
        num_retries = 0
        while not done:
            try:
                self.download_file(output_file, num_connections, key)
                done = True
            except Exception as e:
                logging.exception(e)
                if num_retries == max_retries:
                    if DataFile.TEMPORARY_FILES_SHOULD_BE_DELETED:
                        self.delete_temporary_files()

                    raise e
                time.sleep(retry_wait)
                num_retries += 1
                logging.info(f"retry attempt {num_retries}")

    def delete_temporary_files(self):
        try:
            for temporary_file in self.temporary_files:
                logging.debug(f'Deleting the {temporary_file} temporary file...')
                os.remove(temporary_file)
        except FileNotFoundError as ex:
            logging.error(f'Could not delete the temporary file: {ex}')
