import errno
import json
import os
import unittest
from pathlib import Path
from unittest.mock import patch

import pandas as pd
from click.testing import CliRunner
from PIL import Image

from support import temporary_directory
from imagemorphflow.cli.cli import cli
from imagemorphflow.config import load_mappings
from imagemorphflow.portable import conda_command, image_directory, latest_config, plate_image_directory
from imagemorphflow.processing.load_data import generate_load_data
from imagemorphflow.processing.config_builder import ConfigBuilder
from test_config import manifest


class PortableTests(unittest.TestCase):
    def test_reference_mode_never_creates_a_link_or_copies_images(self):
        with temporary_directory() as directory:
            source, destination = Path(directory) / 'raw images', Path(directory) / 'project' / 'images'
            source.mkdir()
            with patch.object(Path, 'symlink_to', side_effect=AssertionError('must not create a symlink')):
                self.assertEqual(image_directory(source, destination, 'reference'), source.resolve())
            self.assertFalse(destination.exists())

    def test_auto_falls_back_on_missing_symlink_privilege(self):
        with temporary_directory() as directory:
            source, destination = Path(directory) / 'source', Path(directory) / 'destination'
            source.mkdir()
            with patch.object(Path, 'symlink_to', side_effect=OSError(errno.EPERM, 'not permitted')):
                self.assertEqual(image_directory(source, destination), source.resolve())
                with self.assertRaises(OSError):
                    image_directory(source, destination, 'symlink')
            self.assertFalse(destination.exists())

    def test_auto_does_not_hide_disk_errors_or_overwrite_real_folders(self):
        with temporary_directory() as directory:
            source, destination = Path(directory) / 'source', Path(directory) / 'destination'
            source.mkdir()
            with patch.object(Path, 'symlink_to', side_effect=OSError(errno.ENOSPC, 'disk full')):
                with self.assertRaises(OSError):
                    image_directory(source, destination)
            destination.mkdir()
            marker = destination / 'keep.txt'
            marker.write_text('existing data')
            self.assertEqual(image_directory(source, destination), source.resolve())
            self.assertEqual(marker.read_text(), 'existing data')

    def test_latest_config_falls_back_to_small_atomic_copy(self):
        with temporary_directory() as directory:
            root = Path(directory)
            source, latest = root / 'dated.yaml', root / 'latest.yaml'
            source.write_text('project_name: test\n', encoding='utf-8')
            latest.write_text('old config')
            with patch.object(Path, 'symlink_to', side_effect=OSError(errno.EPERM, 'no symlink privilege')):
                latest_config(source, latest)
            self.assertEqual(latest.read_bytes(), source.read_bytes())
            self.assertFalse(latest.is_symlink())
            self.assertEqual(list(root.glob('*.tmp')), [])

    def test_reference_images_end_to_end_with_spaces_and_unicode(self):
        with temporary_directory() as directory:
            root = Path(directory) / 'experimento células'
            acquired = root / 'raw images' / 'plate old' / 'date' / 'images'
            acquired.mkdir(parents=True)
            for channel in ('w1', 'w2'):
                Image.new('L', (4, 4), color=10).save(acquired / f'A01_s12_{channel}.tif')
            data = manifest(root / 'project space')
            data['overrides'].update(image_path=str(root / 'raw images'), image_link_mode='reference', channels={'w1':'DNA', 'w2':'ER'})
            builder = ConfigBuilder()
            config = builder.build_config(data, 'analysis')
            workspace = Path(config['base_path'])
            (workspace / 'symlinks').mkdir(parents=True)
            (workspace / 'symlinks' / 'demo.json').write_text(json.dumps({'plate old':'p01'}))
            config_path = root / 'config.json'
            config_path.write_text(json.dumps(config), encoding='utf-8')
            with patch.object(Path, 'symlink_to', side_effect=AssertionError('no symlinks required')):
                generate_load_data(config_path)
            frame = pd.read_csv(workspace / 'loaddata' / 'p01' / 'load_data.csv')
            self.assertEqual(len(frame), 1)
            self.assertEqual(Path(frame.loc[0, 'PathName_DNA']), acquired.resolve())
            self.assertEqual(plate_image_directory(config, 'p01'), acquired.resolve())
            self.assertFalse((Path(config['project_root']) / 'images' / 'images' / 'p01').exists())

    def test_case_collisions_and_windows_reserved_names(self):
        with temporary_directory() as directory:
            path = Path(directory) / 'plates.json'
            for mappings in ({'a':'Plate', 'b':'plate'}, {'a':'CON'}, {'a':'plate.'}, {'a':'plate:1'}):
                path.write_text(json.dumps(mappings))
                with self.assertRaises(ValueError):
                    load_mappings(path)

    def test_explicit_conda_executable_and_arguments_with_spaces(self):
        with patch.dict(os.environ, {'CONDA_EXE':'/custom path/conda.exe'}):
            command = conda_command('cell profiler', ['python', '-c', 'print("hello")'])
        self.assertEqual(command[:5], ['/custom path/conda.exe','run','--no-capture-output','-n','cell profiler'])
        self.assertEqual(command[-1], 'print("hello")')
        self.assertEqual(conda_command('sam', ['tool'], '/explicit/conda')[0], '/explicit/conda')
        with self.assertRaisesRegex(ValueError, 'conda.exe'):
            conda_command('sam', ['tool'], '/missing/conda.bat')

    def test_doctor_without_conda_does_not_claim_scientific_validation(self):
        with patch.dict(os.environ, {'CONDA_EXE':''}), patch('shutil.which', return_value=None):
            result = CliRunner().invoke(cli, ['doctor','--json'])
        self.assertEqual(result.exit_code, 0, result.output)
        report = json.loads(result.output)
        self.assertIsNone(report['conda_executable'])
        self.assertFalse(report['scientific_tools_validated'])
        self.assertEqual(report['image_link_mode'], 'auto')
