from cryptography.hazmat.primitives.asymmetric \
    import ec
from cryptography.hazmat.primitives \
    import hashes
from cryptography.hazmat.backends \
    import openssl
from cryptography.hazmat.primitives.kdf \
    import hkdf
from cryptography.hazmat.primitives.ciphers.aead \
    import AESGCM
from cryptography.hazmat.primitives.serialization \
    import Encoding, PublicFormat, load_der_public_key

import uuid

import secrets

class Node():
    def __init__(self, name, curEC=ec.SECP256K1(), curBE=openssl.backend):
        self.id = uuid.uuid4()
        self.EC = curEC
        self.BE = curBE
        print("Generate %s's private key" % self.id)
        self.private_key = ec.generate_private_key(
            curve=self.EC, backend=self.BE
        )
        self.shared_keys = {} # dictionary containing master secret for each peer
        # TODO: find a better way to exchange the nonces, instead of using counters
        self.salts = {} # dictionary containing salt for each paired peer
        self.name = name

    def __str__(self):
        shared_keys2str = ",\n\t".join( [str(key) + ':' + str(value)
                                for (key, value) in self.shared_keys.items()]
        )
        return f"Node(name={self.name}, id={self.id}, " + \
            f"shared_keys=[\n\t{shared_keys2str}\n\t]\n)"

    def salt2bytes(self, peer_id):
        return str(self.salts[peer_id]).encode()
    
    def compute_shared_master_secret(self, peer_id, peer_public_key):
        print("Exchanging keys...")
        self.shared_keys[peer_id] = self.private_key. \
            exchange(
                ec.ECDH(), self.deserialize_pk(peer_public_key)
            )
        self.salts[peer_id] = 0 

    '''
    This is the chaining function
    '''
    def derive_current_secret(self, peer_id):
        derived_key =  hkdf.HKDF(
            algorithm=hashes.SHA256(),
            length=32,
            salt=self.salt2bytes(peer_id),
            info=b'handshake_data',
            backend=self.BE
        ).derive(self.shared_keys[peer_id])

        print(f"Key derived by {self.name}: \n\t{str(derived_key)} ",
                f"\n\t key length: {len(derived_key)}")
        return derived_key

    def serialize_pk(self):
        return self.private_key.public_key().public_bytes(
            Encoding.X962,
            PublicFormat.CompressedPoint
        )

    def deserialize_pk(self, peer_pk):
        return ec.EllipticCurvePublicKey.\
            from_encoded_point(self.EC, peer_pk)
    
    def encrypt_msg(self, receiver_id, pt):
        self.salts[receiver_id] = self.salts[receiver_id] + 1
        # symmetric key is derived
        cur_secret = self.derive_current_secret(receiver_id)
        cipher = AESGCM( cur_secret )

        nonce = secrets.token_bytes(20)
        return cipher.encrypt(nonce, pt, None) + nonce

    def decrypt_msg(self, sender_id, msg):
        self.salts[sender_id] = self.salts[sender_id] + 1
        cur_secret = self.derive_current_secret(sender_id)
        cipher = AESGCM( cur_secret )
            
        ct, nonce = msg[:-20], msg[-20:]
        return cipher.decrypt(nonce, ct, None)

    
    
def send_secure_msg(sender, receiver, message):
    print(f"{sender.name} -> {receiver.name}: {message}")
    msg = receiver.decrypt_msg(
        sender.id,
        sender.encrypt_msg(receiver.id, message.encode())
    )
    print(f"{receiver.name} reads \"{msg.decode()}\"")

A = Node('A')
B = Node('B')


A.compute_shared_master_secret(
    B.id,
    B.serialize_pk()
)
B.compute_shared_master_secret(
    A.id,
    A.serialize_pk()
)

print(A)
print(B)

send_secure_msg(A, B, "Hello B")
send_secure_msg(B, A, "Hi A")
send_secure_msg(A, B, "How is it going?")
send_secure_msg(B, A, "Everything is fine, and you?")
