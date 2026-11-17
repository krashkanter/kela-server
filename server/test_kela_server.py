import http.client
import json
import struct
import threading
import unittest
from unittest.mock import patch
import kela_server as kela


class SpecTests(unittest.TestCase):
    def test_storage_mount_isolation(self):
        for source in ['/', '/srv', '/srv/bucket', '/srv/kela-secondary', '/proc/1/root',
                       '/var/run/docker.sock', '../srv/bucket', 'kela-primary', 'kela-secondary']:
            with self.subTest(source=source), self.assertRaises(ValueError):
                kela.container_spec({'name': 'unapproved', 'image': 'alpine', 'binds': [source+':/data']})
        _, spec = kela.container_spec({'name': 'phone-hermes', 'image': 'alpine', 'binds': ['kela-primary:/data']})
        self.assertEqual(spec['HostConfig']['Binds'], ['kela-primary:/data'])

    def test_owner_can_grant_another_container_primary(self):
        from tempfile import TemporaryDirectory
        from pathlib import Path
        with TemporaryDirectory() as tmp:
            config = Path(tmp)/'grants.json'
            config.write_text('{"kela-primary": ["phone-hermes", "approved"]}')
            with patch.object(kela, 'STORAGE_GRANTS', config):
                kela.container_spec({'name': 'approved', 'image': 'alpine', 'binds': ['kela-primary:/data:ro']})
                with self.assertRaises(ValueError):
                    kela.container_spec({'name': 'other', 'image': 'alpine', 'binds': ['kela-primary:/data']})

    def test_ports_and_environment_are_structured(self):
        name, spec = kela.container_spec({"name": "test", "image": "nginx:alpine", "ports": ["127.0.0.1:8081:80", "5353:53/udp"], "environment": ["VALUE=a=b"], "binds": ["bucket:/data:ro"]})
        self.assertEqual(name, "test")
        self.assertEqual(spec["HostConfig"]["PortBindings"]["80/tcp"], [{"HostIp": "127.0.0.1", "HostPort": "8081"}])
        self.assertEqual(spec["Env"], ["VALUE=a=b"])
        self.assertEqual(spec["HostConfig"]["NetworkMode"], "phone-edge")

    def test_rejects_invalid_ports_and_shell_names(self):
        for value in ["0:80", "70000:80", "8081:0", "80", "$(id):80"]:
            with self.subTest(port=value), self.assertRaises(ValueError):
                kela.container_spec({"name": "test", "image": "alpine", "ports": [value]})
        with self.assertRaises(ValueError):
            kela.container_spec({"name": "test;id", "image": "alpine"})

    def test_docker_log_frames(self):
        frame = lambda stream, data: bytes([stream, 0, 0, 0]) + struct.pack(">I", len(data)) + data
        self.assertEqual(kela.demultiplex(frame(1, b"out\n") + frame(2, b"err\n")), "out\nerr\n")
        self.assertEqual(kela.demultiplex(b"TTY output\n"), "TTY output\n")


class AuthenticationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = kela.ThreadingHTTPServer(("127.0.0.1", 0), kela.Handler)
        cls.server.token = "test-token-" * 8
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown(); cls.server.server_close(); cls.thread.join()

    def request(self, method, path, body=None, headers=None):
        client = http.client.HTTPConnection("127.0.0.1", self.server.server_port)
        client.request(method, path, body=body, headers=headers or {})
        response = client.getresponse()
        result = response.status, json.loads(response.read())
        client.close()
        return result

    @patch.object(kela, "docker")
    def test_unauthenticated_mutation_never_reaches_docker(self, docker):
        status, _ = self.request("DELETE", "/v1/containers/abc?force=true")
        self.assertEqual(status, 401); docker.assert_not_called()

    @patch.object(kela, "docker")
    def test_browser_origin_rejected_even_with_token(self, docker):
        status, _ = self.request("GET", "/v1/containers", headers={"Authorization": "Bearer " + self.server.token, "Origin": "https://example.invalid"})
        self.assertEqual(status, 401); docker.assert_not_called()

    @patch.object(kela, "docker", return_value=[])
    def test_authenticated_listing(self, docker):
        status, value = self.request("GET", "/v1/containers", headers={"Authorization": "Bearer " + self.server.token})
        self.assertEqual((status, value), (200, [])); docker.assert_called_once_with("GET", "/containers/json?all=true")

    @patch.object(kela, "docker")
    def test_body_limit(self, docker):
        status, _ = self.request("POST", "/v1/containers", headers={"Authorization": "Bearer " + self.server.token, "Content-Length": str(kela.MAX_BODY + 1)})
        self.assertEqual(status, 413); docker.assert_not_called()

    @patch.object(kela, "docker")
    def test_socket_proxy_path_cannot_be_requested(self, docker):
        status, _ = self.request("POST", "/v1/exec/abc/start", headers={"Authorization": "Bearer " + self.server.token})
        self.assertEqual(status, 404); docker.assert_not_called()

    @patch.object(kela, "docker")
    def test_malformed_payload(self, docker):
        status, _ = self.request("POST", "/v1/containers", body='[1,2]', headers={"Authorization": "Bearer " + self.server.token, "Content-Type": "application/json"})
        self.assertEqual(status, 400); docker.assert_not_called()


if __name__ == "__main__":
    unittest.main()
