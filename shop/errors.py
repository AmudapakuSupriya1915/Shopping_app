class ShopError(Exception):
    status_code = 400


class ValidationError(ShopError):
    pass


class NotFoundError(ShopError):
    status_code = 404


class ConflictError(ShopError):
    status_code = 409


class AuthenticationError(ShopError):
    status_code = 401


class ForbiddenError(ShopError):
    status_code = 403