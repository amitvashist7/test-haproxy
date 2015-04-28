import logging
import string
import subprocess
import sys
import time
import socket
from collections import OrderedDict

import tutum

from globals import *
import utils


logger = logging.getLogger(__name__)


def get_cfg_text(cfg):
    text = ""
    for section, contents in cfg.items():
        text += "%s\n" % section
        for content in contents:
            text += "  %s\n" % content
    return text.strip()


def create_default_cfg(maxconn, mode):
    cfg = OrderedDict({
        "global": ["log %s local0" % RSYSLOG_DESTINATION,
                   "log %s local1 notice" % RSYSLOG_DESTINATION,
                   "log-send-hostname",
                   "maxconn %s" % maxconn,
                   "tune.ssl.default-dh-param 2048",
                   "pidfile /var/run/haproxy.pid",
                   "user haproxy",
                   "group haproxy",
                   "daemon",
                   "stats socket /var/run/haproxy.stats level admin"],
        "listen stats": ["bind *:%s" % STATS_PORT,
                         "mode http",
                         "stats enable",
                         "timeout connect 10s",
                         "timeout client 1m",
                         "timeout server 1m",
                         "stats hide-version",
                         "stats realm Haproxy\ Statistics",
                         "stats uri /",
                         "stats auth %s" % STATS_AUTH],
        "defaults": ["log global",
                     "mode %s" % mode]})
    for option in OPTION:
        if option:
            cfg["defaults"].append("option %s" % option.strip())
    for timeout in TIMEOUT:
        if timeout:
            cfg["defaults"].append("timeout %s" % timeout.strip())
    if SSL_BIND_OPTIONS:
        cfg["global"].append("ssl-default-bind-options %s" % SSL_BIND_OPTIONS)
    if SSL_BIND_CIPHERS:
        cfg["global"].append("ssl-default-bind-ciphers %s" % SSL_BIND_CIPHERS)

    return cfg


def get_backend_routes_tutum(uuid):
    # Output: {'HELLO_WORLD_1': {'proto': 'tcp', 'addr': '172.17.0.103', 'port': '80'},
    # 'HELLO_WORLD_2': {'proto': 'tcp', 'addr': '172.17.0.95', 'port': '80'}}
    addr_port_dict = {}
    try:
        container = tutum.Container.fetch(uuid)
        for link in container.linked_to_container:
            for port, endpoint in link.get("endpoints", {}).iteritems():
                if port in ["%s/tcp" % x for x in BACKEND_PORTS]:
                    addr_port_dict[link["name"].upper().replace("-", "_")] = ENDPOINT_MATCH.match(endpoint).groupdict()
    except Exception as e:
        logger.error("Cannot get backend route from Tutum:", e)
    return addr_port_dict


def get_backend_routes(dict_var):
    # Output: {'HELLO_WORLD_1': {'addr': '172.17.0.103', 'port': '80'},
    # 'HELLO_WORLD_2': {'addr': '172.17.0.95', 'port': '80'}}
    addr_port_dict = {}
    for name, value in dict_var.iteritems():
        position = string.find(name, LINK_ENV_PATTERN)
        if position != -1:
            container_name = name[:position]
            add_port = addr_port_dict.get(container_name, {'addr': "", 'port': ""})
            try:
                add_port['addr'] = socket.gethostbyname(container_name.lower())
            except socket.gaierror:
                add_port['addr'] = socket.gethostbyname(container_name.lower().replace("_", "-"))
            if name.endswith(LINK_PORT_SUFFIX):
                add_port['port'] = value
            addr_port_dict[container_name] = add_port
    return addr_port_dict


def update_cfg(cfg, backend_routes, vhost):
    logger.debug("Updating cfg: \n old cfg: %s\n backend_routes: %s\n vhost: %s", cfg, backend_routes, vhost)
    # Set frontend
    frontend = []
    frontend.append("bind 0.0.0.0:%s" % FRONTEND_PORT)
    if SSL:
        frontend.append("reqadd X-Forwarded-Proto:\ https")
        frontend.append("redirect scheme https code 301 if !{ ssl_fc }"),
        frontend.append("bind 0.0.0.0:443 %s" % SSL)
    if vhost:
        added_vhost = {}
        for _, domain_names in vhost.iteritems():
            for domain_name in domain_names:
                if not added_vhost.has_key(domain_name):
                    domain_str = domain_name.upper().replace(".", "_")
                    frontend.append("acl host_%s %s(host) -i %s" % (domain_str, HDR, domain_name))
                    frontend.append("use_backend %s_cluster if host_%s" % (domain_str, domain_str))
                added_vhost[domain_name] = domain_str
    else:
        frontend.append("default_backend default_service")
    cfg["frontend default_frontend"] = frontend

    # Set backend
    if vhost:
        added_vhost = {}
        for service_name, domain_names in vhost.iteritems():
            for domain_name in domain_names:
                domain_str = domain_name.upper().replace(".", "_")
                service_name = service_name.upper()
                if added_vhost.has_key(domain_name):
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
                    added_vhost[domain_name] = domain_name.upper().replace(".", "_")

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

    logger.debug("New cfg: %s", cfg)


def save_config_file(cfg_text, config_file):
    try:
        directory = os.path.dirname(config_file)
        if not os.path.exists(directory):
            os.makedirs(directory)
        f = open(config_file, 'w')
    except Exception as e:
        logger.error(e)
    else:
        f.write(cfg_text)
        logger.info("Config file is updated")
        f.close()


def reload_haproxy():
    global HAPROXY_CURRENT_SUBPROCESS
    if HAPROXY_CURRENT_SUBPROCESS:
        # Reload haproxy
        logger.info("Reloading haproxy")
        process = subprocess.Popen(HAPROXY_CMD + ["-sf", str(HAPROXY_CURRENT_SUBPROCESS.pid)])
        HAPROXY_CURRENT_SUBPROCESS.wait()
        HAPROXY_CURRENT_SUBPROCESS = process
    else:
        # Launch haproxy
        logger.info("Launching haproxy")
        HAPROXY_CURRENT_SUBPROCESS = subprocess.Popen(HAPROXY_CMD)


def run_haproxy():
    cfg = create_default_cfg(MAXCONN, MODE)
    vhost = utils.parse_vhost(VIRTUAL_HOST, os.environ.iteritems())
    backend_routes = get_backend_routes(os.environ)
    update_cfg(cfg, backend_routes, vhost)
    cfg_text = get_cfg_text(cfg)
    logger.info("HAProxy configuration:\n%s" % cfg_text)
    save_config_file(cfg_text, CONFIG_FILE)

    logger.info("Launching haproxy")
    p = subprocess.Popen(HAPROXY_CMD)
    p.wait()


def run_haproxy_tutum():
    cfg = create_default_cfg(MAXCONN, MODE)
    vhost = utils.parse_vhost(VIRTUAL_HOST, os.environ.iteritems())
    backend_routes = get_backend_routes_tutum(HAPROXY_CONTAINER_UUID)
    update_cfg(cfg, backend_routes, vhost)
    cfg_text = get_cfg_text(cfg)
    logger.info("HAProxy configuration:\n%s" % cfg_text)
    save_config_file(cfg_text, CONFIG_FILE)
    reload_haproxy()


def tutum_event_handler(event):
    if event.get("state", "").lower() == "success":
        pass
    if event.get("state", "").lower() == "success" and \
                    event.get("action", "").lower() == "update" and \
                    len(set(LINKED_SERVICES_ENDPOINTS).intersection(set(event.get("parents", [])))) > 0:
        run_haproxy_tutum()


def main():
    logging.basicConfig(stream=sys.stdout)
    logging.getLogger(__name__).setLevel(logging.DEBUG if DEBUG else logging.INFO)

    # Tell the user the mode of autoupdate we are using, if any
    if TUTUM_SERVICE_API_URL and TUTUM_CONTAINER_API_URL:
        if TUTUM_AUTH:
            logger.info("HAproxy has access to Tutum API - will reload list of backends in real-time")
        else:
            logger.warning(
                "HAproxy doesn't have access to Tutum API and it's running in Tutum - you might want to give "
                "an API role to this service for automatic backend reconfiguration")
    else:
        logger.info("HAproxy is not running in Tutum")

    if TUTUM_SERVICE_API_URL and TUTUM_AUTH:
        global LINKED_SERVICES_ENDPOINTS, HAPROXY_CONTAINER_UUID
        LINKED_SERVICES_ENDPOINTS = utils.parse_tutum_service_endpoint(os.environ.iteritems())
        HAPROXY_CONTAINER_UUID = utils.parse_uuid_from_url(TUTUM_CONTAINER_API_URL)
        run_haproxy_tutum()
        events = tutum.TutumEvents()
        events.on_message(tutum_event_handler)
        events.run_forever()
    else:
        while True:
            run_haproxy()
            time.sleep(1)


if __name__ == "__main__":
    main()