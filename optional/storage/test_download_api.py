import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
import download_api as api


class DownloadPolicyTests(unittest.TestCase):
    def test_paths_cannot_escape_primary_even_through_symlinks(self):
        with tempfile.TemporaryDirectory() as folder, tempfile.TemporaryDirectory() as outside:
            root = Path(folder)
            (root/'escape').symlink_to(outside, target_is_directory=True)
            with patch.object(api, 'ROOT', root):
                for path in ['../secret', '/etc/passwd', 'escape/file', '.private/file']:
                    with self.subTest(path=path), self.assertRaises(ValueError):
                        api.primary_path(path)
                self.assertEqual(api.primary_path('Downloads/files'), root/'Downloads/files')

    @patch.object(api, 'guard_space')
    @patch.object(api, 'rpc')
    def test_add_exposes_no_arbitrary_aria2_options(self, rpc, guard):
        rpc.return_value = '0123456789abcdef'
        with tempfile.TemporaryDirectory() as folder, patch.object(api, 'ROOT', Path(folder)):
            result = api.dispatch({'action':'add', 'url':'https://example.org/file',
                                   'options':{'dir':'/etc', 'rpc-secret':'leak'}})
            self.assertEqual(result['folder'], 'Downloads')
            self.assertEqual(rpc.call_args_list[0].args,
                             ('addUri', ['https://example.org/file'], {'dir':folder+'/Downloads'}))
            rpc.assert_called_with('saveSession')

    @patch.object(api, 'guard_space')
    @patch.object(api, 'rpc')
    def test_rejects_local_file_protocols_and_credentials(self, rpc, guard):
        with tempfile.TemporaryDirectory() as folder, patch.object(api, 'ROOT', Path(folder)):
            for link in ['file:///etc/shadow', 'ftp://example.org/x', 'https://a:b@example.org/x', 'https://x/\nsecret']:
                with self.subTest(link=link), self.assertRaises(ValueError):
                    api.dispatch({'action':'add','url':link})
            rpc.assert_not_called()

    def test_low_host_space_blocks_downloads_even_with_bucket_space(self):
        low = SimpleNamespace(f_bavail=1, f_frsize=4096)
        high = SimpleNamespace(f_bavail=100000000, f_frsize=4096)
        with patch.object(api.os, 'statvfs', side_effect=[low, high]), self.assertRaises(ValueError):
            api.guard_space()

    @patch.object(api, 'rpc')
    def test_pausing_never_deletes_downloaded_files(self, rpc):
        rpc.return_value = '0123456789abcdef'
        result = api.dispatch({'action':'remove', 'gid':'0123456789abcdef'})
        self.assertFalse(result['files_deleted'])
        self.assertEqual(rpc.call_args_list[0].args, ('remove','0123456789abcdef'))


if __name__ == '__main__':
    unittest.main()
