import hashlib
"""Certificate generation for TLS MITM interception.

Generates a local CA and per-host leaf certificates using the cryptography library.
No openssl binary required.
"""

import datetime
import ipaddress
import logging
from pathlib import Path
from typing import Iterable, Tuple

logger = logging.getLogger(__name__)

INTERCEPTED_HOSTS = (
    'assetdelivery.roblox.com',
    'fts.rbxcdn.com',
    'contentdelivery.roblox.com',
    'gamejoin.roblox.com',
)

CA_VALIDITY_DAYS = 3650
LEAF_VALIDITY_DAYS = 825


def _crypto():
    from cryptography import x509
    from cryptography.x509.oid import NameOID
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
    return x509, NameOID, hashes, serialization, rsa


def generate_ca(ca_dir: Path) -> Tuple[Path, Path]:
    """Generate a CA key + self-signed cert. Returns (cert_path, key_path)."""
    ca_dir.mkdir(parents=True, exist_ok=True)
    cert_path = ca_dir / 'ca.crt'
    key_path = ca_dir / 'ca.key'

    if cert_path.exists() and key_path.exists():
        return cert_path, key_path

    x509, NameOID, hashes, serialization, rsa = _crypto()
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name([
        x509.NameAttribute(NameOID.COMMON_NAME, 'RobloxCacheScraper Proxy CA'),
        x509.NameAttribute(NameOID.ORGANIZATION_NAME, 'RobloxCacheScraper'),
    ])
    now = datetime.datetime.now(datetime.timezone.utc)
    cert = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - datetime.timedelta(minutes=5))
        .not_valid_after(now + datetime.timedelta(days=CA_VALIDITY_DAYS))
        .add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True)
        .add_extension(x509.SubjectKeyIdentifier.from_public_key(key.public_key()), critical=False)
        .add_extension(
            x509.KeyUsage(
                digital_signature=True, key_cert_sign=True, crl_sign=True,
                content_commitment=False, key_encipherment=False,
                data_encipherment=False, key_agreement=False,
                encipher_only=False, decipher_only=False,
            ), critical=True,
        )
        .sign(key, hashes.SHA256())
    )
    cert_path.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    key_path.write_bytes(
        key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.TraditionalOpenSSL,
            serialization.NoEncryption(),
        )
    )
    logger.info('Generated CA cert at %s', cert_path)
    return cert_path, key_path


def generate_multi_host_cert(
    hosts: Iterable[str],
    ca_cert_path: Path,
    ca_key_path: Path,
    ca_dir: Path,
) -> Tuple[Path, Path]:
    """Generate a leaf certificate covering all given hosts."""
    ca_dir.mkdir(parents=True, exist_ok=True)
    hosts = sorted({str(h).strip().lower() for h in hosts if str(h).strip()})
    # CN is limited to 64 chars by RFC 5280, so use a short fixed name.
    # SAN (Subject Alternative Name) carries the actual host list.
    cn = 'RobloxCacheScraper Proxy'
    # Use a hash of the joined hosts for a unique but short filename
    host_hash = hashlib.sha256('_'.join(hosts).encode()).hexdigest()[:16]
    cert_path = ca_dir / f'leaf_{host_hash}.crt'
    key_path = ca_dir / f'leaf_{host_hash}.key'

    x509, NameOID, hashes, serialization, rsa = _crypto()
    from cryptography.hazmat.primitives.serialization import load_pem_private_key

    ca_cert = x509.load_pem_x509_certificate(ca_cert_path.read_bytes())

    if cert_path.exists() and key_path.exists():
        return cert_path, key_path

    ca_key = load_pem_private_key(ca_key_path.read_bytes(), password=None)
    leaf_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    now = datetime.datetime.now(datetime.timezone.utc)

    san_entries = []
    for host in hosts:
        try:
            san_entries.append(x509.IPAddress(ipaddress.ip_address(host)))
        except ValueError:
            san_entries.append(x509.DNSName(host))

    leaf_cert = (
        x509.CertificateBuilder()
        .subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, cn)]))
        .issuer_name(ca_cert.subject)
        .public_key(leaf_key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - datetime.timedelta(minutes=5))
        .not_valid_after(now + datetime.timedelta(days=LEAF_VALIDITY_DAYS))
        .add_extension(x509.SubjectAlternativeName(san_entries), critical=False)
        .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
        .add_extension(x509.SubjectKeyIdentifier.from_public_key(leaf_key.public_key()), critical=False)
        .add_extension(x509.AuthorityKeyIdentifier.from_issuer_public_key(ca_key.public_key()), critical=False)
        .add_extension(
            x509.KeyUsage(
                digital_signature=True, key_cert_sign=False, crl_sign=False,
                content_commitment=False, key_encipherment=True,
                data_encipherment=False, key_agreement=False,
                encipher_only=False, decipher_only=False,
            ), critical=True,
        )
        .add_extension(
            x509.ExtendedKeyUsage([x509.ExtendedKeyUsageOID.SERVER_AUTH]),
            critical=False,
        )
        .sign(ca_key, hashes.SHA256())
    )
    cert_path.write_bytes(leaf_cert.public_bytes(serialization.Encoding.PEM))
    key_path.write_bytes(
        leaf_key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.TraditionalOpenSSL,
            serialization.NoEncryption(),
        )
    )
    logger.debug('Generated leaf cert for %s hosts', len(hosts))
    return cert_path, key_path
