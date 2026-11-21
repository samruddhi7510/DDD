"""
Main Entrypoint Script to Launch the Driver Drowsiness Detection System.
Generates an automatic SSL certificate for HTTPS so Android mobile browsers
grant camera permissions (getUserMedia) across the local network without security blocks.
"""

import os
import sys
import socket
import argparse

# Ensure standard output handles UTF-8 on Windows
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    except Exception:
        pass

import uvicorn


def get_local_ip() -> str:
    """Finds the primary local LAN IP address of this machine."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(('8.8.8.8', 80))
        ip = s.getsockname()[0]
    except Exception:
        ip = '127.0.0.1'
    finally:
        s.close()
    return ip


def generate_self_signed_cert(ip_str: str, base_dir: str):
    """
    Creates a valid self-signed SSL certificate with Subject Alternative Names (SAN)
    for localhost and the local network IP. Enables mobile browser camera access.
    """
    cert_path = os.path.join(base_dir, "cert.pem")
    key_path = os.path.join(base_dir, "key.pem")
    
    if os.path.exists(cert_path) and os.path.exists(key_path):
        return cert_path, key_path

    try:
        from cryptography import x509
        from cryptography.x509.oid import NameOID
        from cryptography.hazmat.primitives import hashes
        from cryptography.hazmat.primitives.asymmetric import rsa
        from cryptography.hazmat.primitives import serialization
        import datetime
        import ipaddress

        print(">> Generating local SSL certificate for mobile camera permissions...")
        key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        subject = issuer = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, ip_str)])
        
        alt_names = [
            x509.DNSName("localhost"),
            x509.IPAddress(ipaddress.ip_address("127.0.0.1"))
        ]
        try:
            alt_names.append(x509.IPAddress(ipaddress.ip_address(ip_str)))
        except Exception:
            pass

        cert = x509.CertificateBuilder().subject_name(
            subject
        ).issuer_name(
            issuer
        ).public_key(
            key.public_key()
        ).serial_number(
            x509.random_serial_number()
        ).not_valid_before(
            datetime.datetime.now(datetime.timezone.utc)
        ).not_valid_after(
            datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(days=365)
        ).add_extension(
            x509.SubjectAlternativeName(alt_names),
            critical=False
        ).sign(key, hashes.SHA256())

        with open(key_path, "wb") as f:
            f.write(key.private_bytes(
                serialization.Encoding.PEM,
                serialization.PrivateFormat.TraditionalOpenSSL,
                serialization.NoEncryption()
            ))

        with open(cert_path, "wb") as f:
            f.write(cert.public_bytes(serialization.Encoding.PEM))

        print(">> SSL certificate created successfully!")
        return cert_path, key_path
    except Exception as e:
        print(f">> Note: SSL generation skipped ({e}). Falling back to HTTP.")
        return None, None


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run DrowseGuard AI Server")
    parser.add_argument("--http", action="store_true", help="Force plain HTTP instead of HTTPS")
    parser.add_argument("--port", type=int, default=8000, help="Port to listen on (default 8000)")
    args = parser.parse_args()

    base_dir = os.path.dirname(os.path.abspath(__file__))
    os.chdir(base_dir)
    sys.path.insert(0, base_dir)
    
    local_ip = get_local_ip()
    port = args.port
    
    cert_file = None
    key_file = None
    protocol = "http"
    
    if not args.http:
        cert_file, key_file = generate_self_signed_cert(local_ip, base_dir)
        if cert_file and key_file:
            protocol = "https"

    print("\n" + "=" * 65)
    print("      DROWSEGUARD AI -- ADAPTIVE DRIVER SAFETY SYSTEM v2.0")
    print("=" * 65)
    print(f">> Protocol:                     {protocol.upper()}")
    print(f">> Open on Laptop Browser:       {protocol}://localhost:{port}")
    print(f">> Open on Android Mobile Phone: {protocol}://{local_ip}:{port}")
    print("=" * 65)
    if protocol == "https":
        print("💡 Mobile Note: When opening in Android Chrome, Chrome will say")
        print("   'Your connection is not private'. Tap 'Advanced' -> 'Proceed',")
        print("   and your phone's front camera will open instantly!")
    else:
        print("💡 Mobile Note: If camera says denied, in Chrome on phone open:")
        print(f"   chrome://flags/#unsafely-treat-insecure-origin-as-secure")
        print(f"   and add: http://{local_ip}:{port}")
    print("=" * 65 + "\n")
    
    uvicorn_kwargs = {
        "app": "server:app",
        "host": "0.0.0.0",
        "port": port,
        "reload": False,
        "log_level": "info"
    }
    if cert_file and key_file:
        uvicorn_kwargs["ssl_certfile"] = cert_file
        uvicorn_kwargs["ssl_keyfile"] = key_file

    uvicorn.run(**uvicorn_kwargs)
