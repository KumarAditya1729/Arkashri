# Arkashri External Verification Specification (v1.0.0-RFC)

This document defines the strictly deterministic process required to independently verify an Arkashri Audit Seal.
Arkashri produces a cryptographically sealed WORM bundle (Immutable JSON). To verify it, an auditor must extract the payload, format it consistently, hash it, and verify an ECDSA signature.

## 1. Cryptographic Algorithms
*   **Hashing:** SHA-256
*   **Signature Scheme:** ECDSA using `secp256k1` (or standard `secp256r1`/P-256)
*   **Signature Encoding:** Base64 encoded DER format

## 2. Canonical JSON Serialization Rules (CRITICAL)
Before computing the payload hash, the JSON object must be serialized into a byte-stream uniformly.

1.  **Key Ordering**: All dictionary keys must be sorted alphabetically.
2.  **No Whitespace**: The separators must be strictly `','` and `':'` with zero spaces.
3.  **ASCII Enforcement**: Only ASCII characters; Unicode must be escaped.
4.  **Unicode Normalization**: All string fields must be normalized using Unicode Normalization Form C (`NFC`).
5.  **Numeric Types (Floats Banned)**:
    -   To absolutely guarantee cross-language mathematical consistency, **binary floating-point numbers are strictly prohibited**.
    -   All decimal representations MUST be ingested and serialized natively as **Strings** (e.g. `"amount": "1250.75"`).
    -   Integers are permitted.
6.  **Booleans and Nulls**:
    -   Booleans use native JSON `true` and `false`.
    -   Nulls use native JSON `null`.
7.  **List Sorts**:
    -   Lists must be sorted based on the deterministic string representation of their items.

## 3. Test Vectors

**Input Payload**
```json
{
  "tenant_id": "Ark-001",
  "temperature": 98.60,
  "is_active": true,
  "nested_list": [{"b": 1}, {"a": 2}],
  "null_field": null,
  "unicode": "Ç"
}
```

**Canonical UTF-8 Output**
```
{"is_active":true,"nested_list":[{"a":"2"},{"b":"1"}],"null_field":null,"temperature":"98.6","tenant_id":"Ark-001","unicode":"\u00c7"}
```

**Resulting SHA-256 Hash**
```
a2efc4b22c7a... (Deterministic hash mapping to string)
```

## 4. Rebuilding the Proof Chain
A full audit bundle contains the root hash of the `AuditEvent` Merkle Tree.
If the auditor possesses the exported transactional data:
1. They must compute the `SHA-256` hash of every individual audit log in the stream.
2. They must rebuild the Merkle tree (pairwise hashing).
3. The derived `Merkle Root` must exactly equal the `audit_events_merkle_root` stored inside the `"cryptographic_anchors"` block of the payload.
4. Finally, they verify the Merkle root inclusion in the **Arkashri Transparency Log**, tracking it back to the daily **Public Blockchain Anchor**.
