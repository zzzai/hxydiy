import importlib.util
from pathlib import Path
import tarfile
import unittest

spec = importlib.util.spec_from_file_location('gateway', Path(__file__).resolve().parents[1] / 'deploy/diy/github-ssh-gateway.py')
gateway = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gateway)


class GatewayTests(unittest.TestCase):
    def test_only_release_protocol_commands_are_allowed(self):
        release = 'github-123456789abc-123'
        self.assertEqual(gateway.command_args('true'), ('check', None))
        self.assertEqual(gateway.command_args('hxy-deploy prepare ' + release), ('prepare', release))
        self.assertEqual(gateway.command_args('scp -t /root/hxy-diy-20260811/incoming/' + release + '/'), ('upload', release))
        self.assertEqual(gateway.command_args('scp -d -t /root/hxy-diy-20260811/incoming/' + release + '/'), ('upload', release))
        for command in ['bash', 'cat /etc/passwd', 'true; id', 'hxy-deploy release ../../etc',
                        'scp -t /root/.ssh/', 'scp -t /root/hxy-diy-20260811/incoming/../x', 'internal-sftp']:
            with self.assertRaises(ValueError):
                gateway.command_args(command)

    def test_archive_rejects_traversal_links_devices_and_other_roots(self):
        for name, kind, expected in [('./', tarfile.DIRTYPE, True), ('./diy-web/dist/index.html', tarfile.REGTYPE, True),
                                     ('../../etc/passwd', tarfile.REGTYPE, False), ('/etc/passwd', tarfile.REGTYPE, False),
                                     ('deploy/link', tarfile.SYMTYPE, False), ('deploy/device', tarfile.CHRTYPE, False),
                                     ('other/file', tarfile.REGTYPE, False)]:
            member = tarfile.TarInfo(name)
            member.type = kind
            self.assertEqual(gateway.safe_member(member), expected, name)
