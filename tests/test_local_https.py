import ssl
import tempfile
import unittest
from pathlib import Path

from aiohttp.test_utils import TestClient, TestServer
from local_https import find_openssl, prepare_certificates, setup_app
from server import make_app


class LocalHTTPSSetupTests(unittest.IsolatedAsyncioTestCase):
    async def test_http_homepage_has_public_download_and_https_setup_links(self):
        with tempfile.TemporaryDirectory() as directory:
            (Path(directory)/'root-ca.cer').write_bytes(b'public certificate')
            app = make_app(certificate_directory=directory, https_port=9443)
            async with TestClient(TestServer(app)) as client:
                page = await (await client.get('/')).text()
                self.assertIn('href="/root-ca.cer"', page)
                self.assertIn('href="/camera-setup"', page)
                setup = await (await client.get('/camera-setup')).text()
                self.assertIn('https://127.0.0.1:9443', setup)
                self.assertEqual(await (await client.get('/root-ca.cer')).read(), b'public certificate')
                self.assertEqual((await client.get('/root-ca.key')).status, 404)

    async def test_missing_certificate_explains_how_to_start_https(self):
        with tempfile.TemporaryDirectory() as directory:
            async with TestClient(TestServer(make_app(certificate_directory=directory))) as client:
                response = await client.get('/root-ca.cer')
                self.assertEqual(response.status, 404)
                self.assertIn('python local_https.py', await response.text())

    async def test_setup_serves_only_public_certificate(self):
        with tempfile.TemporaryDirectory() as directory:
            (Path(directory)/'root-ca.cer').write_bytes(b'public certificate')
            (Path(directory)/'root-ca.key').write_text('private key')
            async with TestClient(TestServer(setup_app(directory, '192.168.1.20', 8443))) as client:
                response = await client.get('/')
                page = await response.text()
                self.assertIn('https://192.168.1.20:8443', page)
                self.assertIn('Certificate Trust Settings', page)
                response = await client.get('/root-ca.cer')
                self.assertEqual(await response.read(), b'public certificate')
                self.assertEqual(response.content_type, 'application/x-x509-ca-cert')
                for path in ('/root-ca.key', '/server.key', '/.local-https/root-ca.key'):
                    self.assertEqual((await client.get(path)).status, 404)

    async def test_certificates_load_and_ca_stays_stable(self):
        try:
            find_openssl()
        except RuntimeError:
            self.skipTest('OpenSSL is not installed')
        with tempfile.TemporaryDirectory() as directory:
            context = prepare_certificates(directory, '192.168.1.20')
            self.assertIsInstance(context, ssl.SSLContext)
            root = Path(directory)/'root-ca.pem'
            original = root.read_bytes()
            prepare_certificates(directory, '192.168.1.21')
            self.assertEqual(root.read_bytes(), original)
            self.assertIn('IP:192.168.1.21', (Path(directory)/'server.ext').read_text())

    async def test_invalid_address_does_not_create_certificate_directory(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory)/'certificates'
            with self.assertRaises(ValueError):
                prepare_certificates(target, 'not-an-ip')
            self.assertFalse(target.exists())
