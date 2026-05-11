# pyre-ignore-all-errors
from __future__ import annotations

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec


def test_aws_kms_provider_signs_and_verifies_without_exporting_private_key():
    from arkashri.services.canonical import canonical_json_bytes
    from arkashri.services.kms import AWSKMSProvider

    private_key = ec.generate_private_key(ec.SECP256R1())
    public_der = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.DER,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )

    class FakeKMSClient:
        seen_key_ids: list[str] = []

        def sign(self, *, KeyId, Message, MessageType, SigningAlgorithm):
            self.seen_key_ids.append(KeyId)
            assert MessageType == "RAW"
            assert SigningAlgorithm == "ECDSA_SHA_256"
            return {"Signature": private_key.sign(Message, ec.ECDSA(hashes.SHA256()))}

        def get_public_key(self, *, KeyId):
            self.seen_key_ids.append(KeyId)
            return {"PublicKey": public_der}

    fake_client = FakeKMSClient()
    provider = AWSKMSProvider(
        region="ap-south-1",
        asymmetric_key_id="alias/arkashri-{tenant_id}-seal",
    )
    provider._client = fake_client

    payload = {"report": "final", "amount": 100}
    signature = provider.sign_payload("tenant-a", payload)

    assert provider.verify_payload("tenant-a", payload, signature) is True
    assert provider.verify_payload("tenant-a", {"report": "changed"}, signature) is False
    assert fake_client.seen_key_ids == [
        "alias/arkashri-tenant-a-seal",
        "alias/arkashri-tenant-a-seal",
        "alias/arkashri-tenant-a-seal",
    ]
    assert signature != canonical_json_bytes(payload)
