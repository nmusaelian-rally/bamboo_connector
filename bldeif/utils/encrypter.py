import base64

from cryptography.fernet import Fernet
from cryptography.hazmat.backends   import default_backend
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC


################################################################################

class DecryptionError(Exception): pass

class Encrypter:

    def __init__(self, key):
        """
           key param must be a String

        """
        # cryptography package wants to massage and transform your given key
        # to something it considers more secure and in a standard form/size.
        # Convert the given to a bytes and supply it to the kdf.derive function
        # then translate that back into a String that is URL safe.
        # This convoluted journey provides the real key that is then used
        # for saving/retrieving.

        kdf = PBKDF2HMAC(algorithm=hashes.SHA256(), length=32, salt=b'neeber', iterations=100000, backend=default_backend())
        derived_key = kdf.derive(bytes(key, encoding='utf-8'))
        self.__key = base64.urlsafe_b64encode(derived_key)
        self.__crypto_worker = Fernet(self.__key)


    def encrypt(self, cleartext):
        """
            cleartext must be a String
        """
        crypto_worker = Fernet(self.__key)
        encrypted = self.__crypto_worker.encrypt(bytes(cleartext, encoding='utf-8'))
        return encrypted.decode()

    def decrypt(self, value):
        """
            value must be a String
        """
        encrypted_bytes = bytes(value, encoding='utf-8')
        try:
            payload = self.__crypto_worker.decrypt(encrypted_bytes)
        except:
            raise DecryptionError
        revealed = payload.decode(encoding='utf-8')
        return revealed


###########################################################################################

