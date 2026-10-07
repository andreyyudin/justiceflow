from sqlalchemy.engine import URL, make_url

ASYNC_PG_DRIVER = "postgresql+asyncpg"
LIBPQ_SSL_MODE_PARAMETER = "sslmode"
ASYNCPG_SSL_PARAMETER = "ssl"
UNSUPPORTED_ASYNCPG_PARAMETERS = frozenset({"channel_binding"})


def normalize_asyncpg_url(database_url: str) -> str:
    url = make_url(database_url)

    if url.drivername != ASYNC_PG_DRIVER:
        return database_url

    query = dict(url.query)

    if LIBPQ_SSL_MODE_PARAMETER not in query and not UNSUPPORTED_ASYNCPG_PARAMETERS.intersection(
        query
    ):
        return database_url

    ssl_mode = query.pop(LIBPQ_SSL_MODE_PARAMETER, None)

    for parameter in UNSUPPORTED_ASYNCPG_PARAMETERS:
        query.pop(parameter, None)

    if ssl_mode is not None:
        existing_ssl = query.get(ASYNCPG_SSL_PARAMETER)
        if existing_ssl is not None and existing_ssl != ssl_mode:
            raise ValueError("Database URL contains conflicting ssl and sslmode parameters.")
        query[ASYNCPG_SSL_PARAMETER] = ssl_mode

    normalized_url: URL = url.set(query=query)
    return normalized_url.render_as_string(hide_password=False)
