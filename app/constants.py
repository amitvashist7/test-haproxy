import os

# Config ENV
RSYSLOG_DESTINATION = os.getenv("RSYSLOG_DESTINATION", "127.0.0.1")
BACKEND_PORT = os.getenv("PORT", os.getenv("BACKEND_PORT", "80"))
BACKEND_PORTS = [x.strip() for x in os.getenv("BACKEND_PORTS", BACKEND_PORT).split(",")]
FRONTEND_PORT = os.getenv("FRONTEND_PORT", "80")
MODE = os.getenv("MODE", "http")
HDR = os.getenv("HDR", "hdr")
BALANCE = os.getenv("BALANCE", "roundrobin")
MAXCONN = os.getenv("MAXCONN", "4096")
SSL = os.getenv("SSL", "")
SSL_BIND_OPTIONS = os.getenv("SSL_BIND_OPTIONS", None)
SSL_BIND_CIPHERS = os.getenv("SSL_BIND_CIPHERS", None)
SESSION_COOKIE = os.getenv("SESSION_COOKIE")
OPTION = os.getenv("OPTION", "redispatch, httplog, dontlognull, forwardfor").split(",")
TIMEOUT = os.getenv("TIMEOUT", "connect 5000, client 50000, server 50000").split(",")
VIRTUAL_HOST = os.getenv("VIRTUAL_HOST", None)
TUTUM_CONTAINER_API_URI = os.getenv("TUTUM_CONTAINER_API_URI", None)
TUTUM_SERVICE_API_URI = os.getenv("TUTUM_SERVICE_API_URI", None)
STATS_PORT = os.getenv("STATS_PORT", "1936")
STATS_AUTH = os.getenv("STATS_AUTH", "stats:stats")

TUTUM_AUTH = os.getenv("TUTUM_AUTH")
DEBUG = os.getenv("DEBUG", False)

# Const var
CONFIG_FILE = '/etc/haproxy/haproxy.cfg'
HAPROXY_CMD = ['/usr/sbin/haproxy', '-f', CONFIG_FILE, '-db', '-q']
LINK_ENV_PATTERN = "_PORT_%s_TCP" % BACKEND_PORT
LINK_ADDR_SUFFIX = LINK_ENV_PATTERN + "_ADDR"
LINK_PORT_SUFFIX = LINK_ENV_PATTERN + "_PORT"
VIRTUAL_HOST_SUFFIX = "_ENV_VIRTUAL_HOST"
API_ERROR_RETRY_TIME = 10