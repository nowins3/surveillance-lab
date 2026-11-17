#!/usr/bin/env python3
"""Run the lab over local HTTPS, with an iPhone certificate setup page."""
import argparse
import asyncio
import ipaddress
import shutil
import socket
import ssl
import subprocess
from pathlib import Path

from aiohttp import web
from server import ROOT, make_app
from https_setup import setup_app


def find_openssl():
    executable = shutil.which('openssl')
    if executable:
        return executable
    for location in (Path('C:/Program Files/Git/usr/bin/openssl.exe'),
                     Path('C:/Program Files (x86)/Git/usr/bin/openssl.exe')):
        if location.is_file():
            return str(location)
    raise RuntimeError('OpenSSL is required. Install Git for Windows (which includes OpenSSL), '
                       'or add openssl to PATH.')


def lan_ip():
    # Selecting a route with UDP connect does not send any application data.
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as probe:
        probe.connect(('192.0.2.1', 9))
        return probe.getsockname()[0]


def prepare_certificates(directory, address):
    address = str(ipaddress.IPv4Address(address))
    directory = Path(directory).resolve()
    directory.mkdir(parents=True, exist_ok=True)
    openssl = find_openssl()

    def run(*args):
        result = subprocess.run([openssl, *args], cwd=directory, capture_output=True, text=True)
        if result.returncode:
            raise RuntimeError('OpenSSL failed: ' + result.stderr.strip())

    ca_key, ca_cert = directory/'root-ca.key', directory/'root-ca.pem'
    if ca_key.exists() != ca_cert.exists():
        raise RuntimeError('The local CA is incomplete. Restore its missing key or certificate '
                           'before continuing; existing trusted certificates were not replaced.')
    if not ca_key.exists():
        run('req', '-x509', '-newkey', 'rsa:2048', '-nodes', '-sha256', '-days', '3650',
            '-keyout', ca_key.name, '-out', ca_cert.name, '-subj', '/CN=Surveillance Lab Local CA',
            '-addext', 'basicConstraints=critical,CA:TRUE,pathlen:0',
            '-addext', 'keyUsage=critical,keyCertSign,cRLSign',
            '-addext', 'subjectKeyIdentifier=hash')
    # Keep the CA stable so the iPhone needs to trust it only once. Renew the
    # short-lived server certificate on launch, including the current Wi-Fi IP.
    extension_file = directory/'server.ext'
    extension_file.write_text(
        'basicConstraints=critical,CA:FALSE\n'
        'keyUsage=critical,digitalSignature,keyEncipherment\n'
        'extendedKeyUsage=serverAuth\n'
        f'subjectAltName=DNS:localhost,IP:127.0.0.1,IP:{address}\n', encoding='ascii')
    run('req', '-new', '-newkey', 'rsa:2048', '-nodes', '-sha256',
        '-keyout', 'server.key', '-out', 'server.csr', '-subj', '/CN=Surveillance Lab')
    run('x509', '-req', '-in', 'server.csr', '-CA', ca_cert.name, '-CAkey', ca_key.name,
        '-CAcreateserial', '-out', 'server.pem', '-days', '90', '-sha256',
        '-extfile', extension_file.name)
    run('x509', '-in', ca_cert.name, '-outform', 'DER', '-out', 'root-ca.cer')
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.load_cert_chain(directory/'server.pem', directory/'server.key')
    return context


async def serve(args, context):
    app = make_app(args.vision, certificate_directory=args.directory,
                   https_port=args.port, https_address=args.ip)
    runner = web.AppRunner(app)
    try:
        await runner.setup()
        await web.TCPSite(runner, '0.0.0.0', args.setup_port).start()
        await web.TCPSite(runner, '0.0.0.0', args.port, ssl_context=context).start()
        print(f'\nHTTP website: http://{args.ip}:{args.setup_port}', flush=True)
        print('Use the Camera / HTTPS setup link to download the certificate.', flush=True)
        print(f'After installing and trusting the certificate: https://{args.ip}:{args.port}', flush=True)
        print('Keep this terminal open. Press Ctrl+C to stop both servers.', flush=True)
        await asyncio.Event().wait()
    finally:
        await runner.cleanup()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--ip', help='Computer Wi-Fi IPv4 address (automatically detected by default)')
    parser.add_argument('--port', type=int, default=8443, help='HTTPS port (default: 8443)')
    parser.add_argument('--setup-port', type=int, default=8000, help='HTTP website port (default: 8000)')
    parser.add_argument('--directory', type=Path, default=ROOT/'.local-https', help='Private certificate directory')
    parser.add_argument('--vision', action='store_true')
    args = parser.parse_args()
    try:
        args.ip = str(ipaddress.IPv4Address(args.ip or lan_ip()))
        context = prepare_certificates(args.directory, args.ip)
        asyncio.run(serve(args, context))
    except KeyboardInterrupt:
        pass
    except (OSError, RuntimeError, ValueError) as exc:
        parser.exit(1, f'{exc}\n')
