"""VAPID鍵ペア(Web Push用)を生成する。
実行: python generate_vapid_keys.py
出力された値を .env の VAPID_PUBLIC_KEY / VAPID_PRIVATE_KEY に設定してください。
"""
import base64

from cryptography.hazmat.primitives.asymmetric import ec

private_key = ec.generate_private_key(ec.SECP256R1())
public_key = private_key.public_key()

public_numbers = public_key.public_numbers()
x = public_numbers.x.to_bytes(32, "big")
y = public_numbers.y.to_bytes(32, "big")
uncompressed_point = b"\x04" + x + y
public_b64url = base64.urlsafe_b64encode(uncompressed_point).rstrip(b"=").decode()

private_value = private_key.private_numbers().private_value
private_bytes = private_value.to_bytes(32, "big")
private_b64url = base64.urlsafe_b64encode(private_bytes).rstrip(b"=").decode()

print(f"VAPID_PUBLIC_KEY={public_b64url}")
print(f"VAPID_PRIVATE_KEY={private_b64url}")
