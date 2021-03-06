from datetime import timedelta
import time
import uuid

from Crypto.PublicKey.RSA import importKey
from django.utils import timezone
from hashlib import md5
from jwkest.jwk import RSAKey as jwk_RSAKey
from jwkest.jws import JWS

from oidc_provider.lib.utils.common import get_issuer
from oidc_provider.models import *
from oidc_provider import settings
import hashlib
import base64

def create_id_token(user, aud, nonce):
    """
    Receives a user object and aud (audience).
    Then creates the id_token dictionary.
    See: http://openid.net/specs/openid-connect-core-1_0.html#IDToken

    Return a dic.
    """
    sub = settings.get('OIDC_IDTOKEN_SUB_GENERATOR', import_str=True)(user=user)

    expires_in = settings.get('OIDC_IDTOKEN_EXPIRE')

    # Convert datetimes into timestamps.
    now = timezone.now()
    iat_time = int(time.mktime(now.timetuple()))
    exp_time = int(time.mktime((now + timedelta(seconds=expires_in)).timetuple()))
    user_auth_time = user.last_login or user.date_joined
    auth_time = int(time.mktime(user_auth_time.timetuple()))

    dic = {
        'iss': get_issuer(),
        'sub': sub,
        'aud': str(aud),
        'exp': exp_time,
        'iat': iat_time,
        'auth_time': auth_time,
    }

    if nonce:
        dic['nonce'] = str(nonce)

    processing_hook = settings.get('OIDC_IDTOKEN_PROCESSING_HOOK')

    if isinstance(processing_hook, (list, tuple)):
        for hook in processing_hook:
            dic = settings.import_from_str(hook)(dic, user=user)
    else:
        dic = settings.import_from_str(processing_hook)(dic, user=user)

    return dic


def encode_id_token(payload):
    """
    Represent the ID Token as a JSON Web Token (JWT).

    Return a hash.
    """
    keys = []

    for rsakey in RSAKey.objects.all():
        keys.append(jwk_RSAKey(key=importKey(rsakey.key), kid=rsakey.kid))

    if not keys:
        raise Exception('You must add at least one RSA Key.')
    
    _jws = JWS(payload, alg='RS256')

    return _jws.sign_compact(keys)


def create_token(user, client, id_token_dic, scope):
    """
    Create and populate a Token object.

    Return a Token object.
    """
    token = Token()
    token.user = user
    token.client = client
    raw_uuid = uuid.uuid4()
    token.access_token = raw_uuid.hex

    # next 3 lines is the code to create our at_hash
    ascii_representation_access_token = raw_uuid.hex
    hashed_token = hashlib.sha256(ascii_representation_access_token)
    id_token_dic['at_hash'] = base64.urlsafe_b64encode(hashed_token.digest()[:16])

    token.id_token = id_token_dic
    token.at_hash = id_token_dic['at_hash']
    token.refresh_token = uuid.uuid4().hex
    token.expires_at = timezone.now() + timedelta(
        seconds=settings.get('OIDC_TOKEN_EXPIRE'))
    token.scope = scope

    return token


def create_code(user, client, scope, nonce, is_authentication):
    """
    Create and populate a Code object.

    Return a Code object.
    """
    code = Code()
    code.user = user
    code.client = client
    code.code = uuid.uuid4().hex
    code.expires_at = timezone.now() + timedelta(
        seconds=settings.get('OIDC_CODE_EXPIRE'))
    code.scope = scope
    code.nonce = nonce
    code.is_authentication = is_authentication

    return code
