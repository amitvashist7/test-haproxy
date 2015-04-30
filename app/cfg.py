import logging
from collections import OrderedDict

from constants import *


logger = logging.getLogger("tutum_haproxy")


def cfg_default(rsyslog_dst, maxconn, stats_port, stats_auth, mode, options, timeout,
                ssl_bind_opts, ssl_bind_ciphers):
    cfg = OrderedDict({
        "global": ["log %s local0" % rsyslog_dst,
                   "log %s local1 notice" % rsyslog_dst,
                   "log-send-hostname",
                   "maxconn %s" % maxconn,
                   "tune.ssl.default-dh-param 2048",
                   "pidfile /var/run/haproxy.pid",
                   "user haproxy",
                   "group haproxy",
                   "daemon",
                   "stats socket /var/run/haproxy.stats level admin"],
        "listen stats": ["bind *:%s" % stats_port,
                         "mode http",
                         "stats enable",
                         "timeout connect 10s",
                         "timeout client 1m",
                         "timeout server 1m",
                         "stats hide-version",
                         "stats realm Haproxy\ Statistics",
                         "stats uri /",
                         "stats auth %s" % stats_auth],
        "defaults": ["log global",
                     "mode %s" % mode]})
    for opt in options:
        if opt:
            cfg["defaults"].append("option %s" % opt.strip())
    for t in timeout:
        if t:
            cfg["defaults"].append("timeout %s" % t.strip())
    if ssl_bind_opts:
        cfg["global"].append("ssl-default-bind-options %s" % ssl_bind_opts)
    if ssl_bind_ciphers:
        cfg["global"].append("ssl-default-bind-ciphers %s" % ssl_bind_ciphers)

    return cfg


def cfg_frontend(vhost):
    cfg = OrderedDict()
    frontend = []
    frontend.append("bind 0.0.0.0:%s" % FRONTEND_PORT)
    if SSL:
        frontend.append("reqadd X-Forwarded-Proto:\ https")
        frontend.append("redirect scheme https code 301 if !{ ssl_fc }"),
        frontend.append("bind 0.0.0.0:443 %s" % SSL)
    if vhost:
        added_vhost = set()
        for _, domain_names in vhost.iteritems():
            for domain_name in domain_names:
                if domain_name not in added_vhost:
                    domain_str = domain_name.upper().replace(".", "_")
                    frontend.append("acl host_%s %s(host) -i %s" % (domain_str, HDR, domain_name))
                    frontend.append("use_backend %s_cluster if host_%s" % (domain_str, domain_str))
                added_vhost.add(domain_name)
    else:
        frontend.append("default_backend default_service")
    cfg["frontend default_frontend"] = frontend
    return cfg


def cfg_backend(backend_routes, vhost):
    cfg = OrderedDict()
    if vhost:
        added_vhost = set()
        for service_name, domain_names in vhost.iteritems():
            for domain_name in domain_names:
                domain_str = domain_name.upper().replace(".", "_")
                service_name = service_name.upper()
                if domain_name in added_vhost:
                    backend = cfg.get("backend %s_cluster" % domain_str, [])
                    for container_name, addr_port in backend_routes.iteritems():
                        if container_name.startswith(service_name):
                            server_string = "server %s %s:%s" % (container_name, addr_port["addr"], addr_port["port"])
                            if SESSION_COOKIE:
                                server_string += " cookie check"

                            # Do not add duplicate backend routes
                            duplicated = False
                            for server_str in backend:
                                if "%s:%s" % (addr_port["addr"], addr_port["port"]) in server_str:
                                    duplicated = True
                                    break
                            if not duplicated:
                                backend.append(server_string)
                    cfg["backend %s_cluster" % domain_str] = sorted(backend)
                else:
                    backend = []
                    if SESSION_COOKIE:
                        backend.append("appsession %s len 64 timeout 3h request-learn prefix" % (SESSION_COOKIE, ))

                    backend.append("balance %s" % BALANCE)
                    for container_name, addr_port in backend_routes.iteritems():
                        if container_name.startswith(service_name):
                            server_string = "server %s %s:%s" % (container_name, addr_port["addr"], addr_port["port"])
                            if SESSION_COOKIE:
                                server_string += " cookie check"

                            # Do not add duplicate backend routes
                            duplicated = False
                            for server_str in backend:
                                if "%s:%s" % (addr_port["addr"], addr_port["port"]) in server_str:
                                    duplicated = True
                                    break
                            if not duplicated:
                                backend.append(server_string)
                if backend:
                    cfg["backend %s_cluster" % domain_name.upper().replace(".", "_")] = sorted(backend)
                    added_vhost.add(domain_name)

    else:
        backend = []
        if SESSION_COOKIE:
            backend.append("appsession %s len 64 timeout 3h request-learn prefix" % (SESSION_COOKIE, ))

        backend.append("balance %s" % BALANCE)
        for container_name, addr_port in backend_routes.iteritems():
            server_string = "server %s %s:%s" % (container_name, addr_port["addr"], addr_port["port"])
            if SESSION_COOKIE:
                server_string += " cookie check"

            # Do not add duplicate backend routes
            duplicated = False
            for server_str in backend:
                if "%s:%s" % (addr_port["addr"], addr_port["port"]) in server_str:
                    duplicated = True
                    break
            if not duplicated:
                backend.append(server_string)

        cfg["backend default_service"] = sorted(backend)
    return cfg


def cfg_calc(backend_routes, vhost):
    logger.debug("Updating cfg: \n backend_routes: %s\n vhost: %s", backend_routes, vhost)
    cfg = OrderedDict()
    default = cfg_default(RSYSLOG_DESTINATION, MAXCONN, STATS_PORT, STATS_AUTH, MODE, OPTION, TIMEOUT,
                          SSL_BIND_OPTIONS, SSL_BIND_CIPHERS)
    frontend = cfg_frontend(vhost)
    backend = cfg_backend(backend_routes, vhost)
    cfg.update(default)
    cfg.update(frontend)
    cfg.update(backend)
    logger.debug("New cfg: %s", cfg)
    return cfg


def cfg_to_text(cfg):
    text = ""
    for section, contents in cfg.items():
        text += "%s\n" % section
        for content in contents:
            text += "  %s\n" % content
    return text.strip()


def cfg_save(text, path):
    try:
        directory = os.path.dirname(path)
        if not os.path.exists(directory):
            os.makedirs(directory)
        f = open(path, 'w')
    except Exception as e:
        logger.error(e)
    else:
        f.write(text)
        logger.info("Config file is updated")
        f.close()