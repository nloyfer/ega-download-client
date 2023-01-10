import os
import uuid

import pytest

from tests.functional.test_download import run_command_and_assert_download_complete, cleanup
from tests.functional.util import md5

script_dir = os.path.dirname(__file__)


# TODO enable once bug is fixed
@pytest.mark.skip(reason="Failing because of a bug")
def test_htsget_vcf():
    file_id, file_format, ref = ['EGAF00005001623', 'VCF', '22']

    output_dir = _run_pyega3(file_id, file_format, ref)

    _assert_correct_file_is_downloaded(f'{output_dir}/{file_id}',
                                       f'ALL_chr22_20130502_2504Individuals.vcf_genomic_range_{ref}_None_None.gz.vcf',
                                       '4c8b4a934c29415723beac115c1edfaa')

    cleanup(output_dir)


# TODO enable once bug is fixed
@pytest.mark.skip(reason="Failing because of a bug")
def test_htsget_vcf_with_range():
    file_id, file_format, ref, start, end = ['EGAF00005001623', 'VCF', '22', 0, 100000]

    output_dir = _run_pyega3(file_id, file_format, ref, start, end)

    _assert_correct_file_is_downloaded(f'{output_dir}/{file_id}',
                                       f'ALL_chr22_20130502_2504Individuals.vcf_genomic_range_{ref}_{start}_{end}.gz.vcf',
                                       'b10fbc3ce033ba5a713cdc010d3307d7')
    cleanup(output_dir)


def test_htsget_cram():
    file_id, file_format, ref = ['EGAF00007243774', 'CRAM', 'chr10']

    output_dir = _run_pyega3(file_id, file_format, ref)

    _assert_correct_file_is_downloaded(f'{output_dir}/{file_id}',
                                       f'HG00096.GRCh38DH__1097r__10.10000-10100__21.5000000-5050000_genomic_range_{ref}_None_None.cram',
                                       'becca46f235cad30ef92743af8ab69fa')

    cleanup(output_dir)


def test_htsget_cram_with_range():
    file_id, file_format, ref, start, end = ['EGAF00007243774', 'CRAM', 'chr10', 10000, 10050]

    output_dir = _run_pyega3(file_id, file_format, ref, start, end)

    _assert_correct_file_is_downloaded(f'{output_dir}/{file_id}',
                                       f'HG00096.GRCh38DH__1097r__10.10000-10100__21.5000000-5050000_genomic_range_{ref}_{start}_{end}.cram',
                                       'becca46f235cad30ef92743af8ab69fa')

    cleanup(output_dir)


def test_htsget_cram_with_range2():
    file_id, file_format, ref, start, end = ['EGAF00007462304', 'CRAM', 'chr10', 10000, 10035]

    output_dir = _run_pyega3(file_id, file_format, ref, start, end)

    _assert_correct_file_is_downloaded(f'{output_dir}/{file_id}',
                                       f'EE-2564.NA18636.alt_bwamem_GRCh38DH.20150826.CHB.exome_genomic_range_{ref}_{start}_{end}.cram',
                                       '86b66eb1a56aaa0535a5aaecf8923552')

    cleanup(output_dir)


@pytest.mark.skip(reason="implement this")
def test_htsget_cram_big_file_with_range():
    pass


def test_htsget_bam():
    file_id, file_format, ref = ['EGAF00007243773', 'BAM', 'chr10']

    output_dir = _run_pyega3(file_id, file_format, ref)

    _assert_correct_file_is_downloaded(f'{output_dir}/{file_id}',
                                       f'HG00096.GRCh38DH__1097r__10.10000-10100__21.5000000-5050000_genomic_range_{ref}_None_None.bam',
                                       'a5483f1da3981851ac0a5e4dddd2062f')

    cleanup(output_dir)


def test_htsget_bam_with_range():
    file_accession, file_format, ref, start, end = ['EGAF00007243773', 'BAM', 'chr10', 10000, 10050]

    output_dir = _run_pyega3(file_accession, file_format, ref, start, end)

    _assert_correct_file_is_downloaded(f'{output_dir}/{file_accession}',
                                       f'HG00096.GRCh38DH__1097r__10.10000-10100__21.5000000-5050000_genomic_range_{ref}_{start}_{end}.bam',
                                       'a5483f1da3981851ac0a5e4dddd2062f')

    cleanup(output_dir)


def test_htsget_bcf():
    file_accession, file_format, ref = ['EGAF00005001625', 'BCF', '22']

    output_dir = _run_pyega3(file_accession, file_format, ref)

    _assert_correct_file_is_downloaded(f'{output_dir}/{file_accession}',
                                       f'ALL_chr22_20130502_2504Individuals_genomic_range_{ref}_None_None.bcf',
                                       'c65ca1a4abd55351598ccbc65ebfa9a6')

    cleanup(output_dir)


def test_htsget_bcf_with_range():
    file_accession, file_format, ref, start, end = ['EGAF00005001625', 'BCF', '22', 0, 100000]

    output_dir = _run_pyega3(file_accession, file_format, ref, start, end)

    _assert_correct_file_is_downloaded(f'{output_dir}/{file_accession}',
                                       f'ALL_chr22_20130502_2504Individuals_genomic_range_{ref}_{start}_{end}.bcf',
                                       'c65ca1a4abd55351598ccbc65ebfa9a6')

    cleanup(output_dir)


def _run_pyega3(file_accession: str, file_format: str, ref: str, start=None, end=None):
    start_arg = '' if start is None else f'--start {start}'
    end_arg = '' if end is None else f'--end {end} '
    range_args = f'{start_arg} {end_arg}' if start_arg and end_arg else ''
    outdir = _setup_output_dir()
    cmd = f'pyega3 -t -d fetch {file_accession} --reference-name {ref} {range_args}--format {file_format} --output-dir {outdir}'
    run_command_and_assert_download_complete(cmd)
    return outdir


def _setup_output_dir():
    dir_id = str(uuid.uuid1())
    output_dir = f'{script_dir}/.tmp/{dir_id}'
    os.makedirs(output_dir, exist_ok=True)
    return output_dir


def _assert_correct_file_is_downloaded(download_dir: str, filename: str, md5sum: str):
    downloaded_files = [f for f in os.listdir(download_dir) if os.path.isfile(f'{download_dir}/{f}')]
    assert len(downloaded_files) == 1
    htsget_file = downloaded_files[0]
    assert htsget_file == filename
    assert md5(f'{download_dir}/{htsget_file}') == md5sum
