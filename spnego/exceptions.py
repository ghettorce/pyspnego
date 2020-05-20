# Copyright: (c) 2020, Jordan Borean (@jborean93) <jborean93@gmail.com>
# MIT License (see LICENSE or https://opensource.org/licenses/MIT)

from spnego._compat import (
    add_metaclass,

    Optional,
    Union,

    IntEnum,
)

from spnego._text import (
    text_type,
    to_native,
)

try:
    from gssapi.exceptions import GSSError
except ImportError:
    GSSError = ()

try:
    WinError = WindowsError
except NameError:
    WinError = ()


class ErrorCode(IntEnum):
    """Common error codes for SPNEGO operations.

    Mostly a copy of the `GSS major error codes`_ with the names made more pythonic. Not all codes have a corresponding
    SpnegoError class as they are reserved for the codes that apply to both GSSAPI and SSPI.

    .. _GSS major error codes:
        https://docs.oracle.com/cd/E19683-01/816-1331/reference-4/index.html
    """
    bad_mech = 1  # BadMechanismError
    bad_name = 2  # BadNameError
    bad_nametype = 3
    bad_bindings = 4  # BadBindings
    bad_status = 5
    bad_mic = 6  # BadMICError
    no_cred = 7
    no_context = 8
    invalid_token = 9  # InvalidTokenError
    invalid_credential = 10
    credentials_expired = 11
    context_expired = 12  # ContextExpiredError
    failure = 13  # This is a generic error with the error coming from the minor code, uses SpnegoError directly.
    bad_qop = 14  # UnsupportedQop
    unauthorized = 15
    unavailable = 16  # OperationNotAvailableError
    duplicate_element = 17
    name_not_mn = 18


# Implementation is inspired by the python-gssapi project https://github.com/pythongssapi/python-gssapi.
# https://github.com/pythongssapi/python-gssapi/blob/826c02de1c1885896924bf342c60087f369c6b1a/gssapi/raw/misc.pyx#L180
class _SpnegoErrorRegistry(type):
    __registry = {}
    __gssapi_map = {}
    __sspi_map = {}

    def __init__(cls, name, bases, attributes):
        # Load up the registry with the instantiated class so we can look it up when creating a SpnegoError.
        error_code = getattr(cls, 'ERROR_CODE', None)

        if error_code is not None and error_code not in cls.__registry:
            cls.__registry[error_code] = cls

        # Map the system error codes to the common spnego error code.
        for system_attr, mapping in [('_GSSAPI_CODE', cls.__gssapi_map), ('_SSPI_CODE', cls.__sspi_map)]:
            codes = getattr(cls, system_attr, None)

            if codes is None:
                continue

            if not isinstance(codes, (list, tuple)):
                codes = [codes]

            for c in codes:
                mapping[c] = error_code

    def __call__(cls, error_code=None, base_error=None, *args, **kwargs):
        error_code = error_code if error_code is not None else getattr(cls, 'ERROR_CODE', None)

        if error_code is None:
            if not base_error:
                raise ValueError("%s requires either an error_code or base_error" % cls.__name__)

            # GSSError
            if hasattr(base_error, 'maj_code'):
                error_code = cls.__gssapi_map.get(base_error.maj_code, None)

            # WindowsError
            elif hasattr(base_error, 'winerror'):
                error_code = cls.__sspi_map.get(base_error.winerror, None)

            else:
                raise ValueError("base_error of type '%s' is not supported, must be a gssapi.exceptions.GSSError or "
                                 "WindowsError" % type(base_error).__name__)

        new_cls = cls.__registry.get(error_code, cls)
        return super(_SpnegoErrorRegistry, new_cls).__call__(error_code, base_error, *args, **kwargs)


@add_metaclass(_SpnegoErrorRegistry)
class SpnegoError(Exception):
    """Common error for SPNEGO exception.

    Creates an common error record for SPNEGO errors raised by pyspnego. This error record can wrap system level error
    records raised by GSSAPI or SSPI and wrap them into a common error record across the various platforms.

    Args:
        error_code: The ErrorCode for the error, this must be set if base_error is not set.
        base_error: The system level error from SSPI or GSSAPI, this must be set if error_code is not set.
        context_msg: Optional message to provide more context around the error.

    Attributes:
        base_error (Optional[Union[GSSError, WinError]]): The system level error if one was provided.
    """

    # Classes the subclass this type need to provide the following class attribute:
    #
    # ERROR_CODE = common ErrorCode value for the exception
    # _BASE_MESSAGE = common string that explains the error code in the absence of the system error message.
    #
    # The following attributes are used to map specific system error codes to the common ErrorCode error.
    # _GSSAPI_CODE = The GSSAPI major_code from GSSError to map to the common error code
    # _SSPI_CODE = The winerror value from an WindowsError to map to the common error code

    def __init__(self, error_code=None, base_error=None, context_msg=None):
        self.base_error = base_error  # type: Optional[Union[GSSError, WinError]]
        self._error_code = error_code  # type: Optional[ErrorCode]
        self._context_message = context_msg  # type: Optional[text_type]

        super(SpnegoError, self).__init__(self.message)

    @property
    def message(self):
        error_code = self._error_code if self._error_code is not None else 0xFFFFFFFF

        if self.base_error:
            base_message = str(self.base_error)

        else:
            base_message = getattr(self, '_BASE_MESSAGE', 'Unknown error code')

        msg = "SpnegoError (%d): %s" % (error_code, base_message)
        if self._context_message:
            msg += ", Context: %s" % self._context_message

        return msg


class BadMechanismError(SpnegoError):
    ERROR_CODE = ErrorCode.bad_mech

    _BASE_MESSAGE = "An unsupported mechanism was requested"
    _GSSAPI_CODE = 65536  # GSS_S_BAD_MECH
    _SSPI_TOKEN = -2146893051  # SEC_E_SECPKG_NOT_FOUND


class BadNameError(SpnegoError):
    ERROR_CODE = ErrorCode.bad_name

    _BASE_MESSAGE = "An invalid name was supplied"
    _GSSAPI_CODE = 1310722  # GSS_S_BAD_NAME
    _SSPI_TOKEN = -2146893053  # SEC_E_TARGET_UNKNOWN


class BadBindings(SpnegoError):
    ERROR_CODE = ErrorCode.bad_bindings

    _BASE_MESSAGE = "Invalid channel bindings"
    _GSSAPI_CODE = 262144  # GSS_BAD_BINDINGS
    _SSPI_TOKEN = -2146892986  # SEC_E_BAD_BINDINGS


class BadMICError(SpnegoError):
    ERROR_CODE = ErrorCode.bad_mic

    _BASE_MESSAGE = "A token had an invalid Message Integrity Check (MIC)"
    _GSSAPI_CODE = 3932166  # GSS_BAD_MIC
    _SSPI_TOKEN = -2146893041  # SEC_E_MESSAGE_ALTERED


class NoCredentialError(SpnegoError):
    ERROR_CODE = ErrorCode.no_cred

    _BASE_MESSAGE = "No credentials were supplied, or the credentials were unavailable or inaccessible"
    _GSSAPI_CODE = 458752  # GSS_NO_CRED
    _SSPI_TOKEN = -2146893042  # SEC_E_NO_CREDENTIALS


class InvalidTokenError(SpnegoError):
    ERROR_CODE = ErrorCode.invalid_token

    _BASE_MESSAGE = "A token was invalid"
    _GSSAPI_CODE = 589824  # GSS_S_DEFECTIVE_TOKEN
    _SSPI_TOKEN = -2146893048  # SEC_E_INVALID_TOKEN


class ContextExpiredError(SpnegoError):
    ERROR_CODE = ErrorCode.context_expired

    _BASE_MESSAGE = "Security context has expired"
    _GSSAPI_CODE = 786432  # GSS_S_CONTEXT_EXPIRED
    _SSPI_TOKEN = -2146893033  # SEC_E_CONTEXT_EXPIRED


class UnsupportedQop(SpnegoError):
    ERROR_CODE = ErrorCode.bad_qop

    _BASE_MESSAGE = "The quality-of-protection requested could not be provided"
    _GSSAPI_CODE = 917504  # GSS_S_BAD_QOP
    _SSPI_TOKEN = -2146893046  # SEC_E_QOP_NOT_SUPPORTED


class OperationNotAvailableError(SpnegoError):
    ERROR_CODE = ErrorCode.unavailable

    _BASE_MESSAGE = "Operation not supported or available"
    _GSSAPI_CODE = 1048576  # GSS_S_UNAVAILABLE
    _SSPI_CODE = -2146893054  # SEC_E_UNSUPPORTED_FUNCTION
