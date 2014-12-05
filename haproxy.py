#!/usr/bin/env python
import logging
import os
import time
import string
import subprocess
import sys
from collections import OrderedDict

import requests


logger = logging.getLogger(__name__)

# Config ENV
PORT = os.getenv("PORT", "80")
MODE = os.getenv("MODE", "http")
BALANCE = os.getenv("BALANCE", "roundrobin")
MAXCONN = os.getenv("MAXCONN", "4096")
SSL = os.getenv("SSL", "")
OPTION = os.getenv("OPTION", "redispatch, httplog, dontlognull, forwardfor").split(",")
TIMEOUT = os.getenv("TIMEOUT", "connect 5000, client 50000, server 50000").split(",")
VIRTUAL_HOST = os.getenv("VIRTUAL_HOST", None)

TUTUM_AUTH = os.getenv("TUTUM_AUTH")
DEBUG = os.getenv("DEBUG", False)


# Const var
CONFIG_FILE = '/etc/haproxy/haproxy.cfg'
HAPROXY_CMD = ['/usr/sbin/haproxy', '-f', CONFIG_FILE, '-db']
POLLING_PERIOD = 30
LINK_ENV_PATRTERN = "_PORT_%s_TCP" % PORT
LINK_ADDR_SUFFIX = LINK_ENV_PATRTERN + "_ADDR"
LINK_PORT_SUFFIX = LINK_ENV_PATRTERN + "_PORT"
TUTUM_URL_SUFFIX = "_TUTUM_API_URL"


# Global Var
HAPROXY_CURRENT_SUBPROCESS = None


def get_cfg_text(cfg):
    text = ""
    for section, contents in cfg.items():
        text += "%s\n" % section
        for content in contents:
            text += "  %s\n" % content
    return text.strip()


def create_default_cfg(maxconn, mode):
    cfg = OrderedDict({
        "global": ["log 127.0.0.1   local0",
                   "log 127.0.0.1   local1 notice",
                   "maxconn %s" % maxconn,
                   "pidfile /var/run/haproxy.pid",
                   "user haproxy",
                   "group haproxy",
                   "daemon"],
        "defaults": ["log     global",
                     "mode %s" % mode]})
    for option in OPTION:
        if option:
            cfg["defaults"].append("option %s" % option.strip())
    for timeout in TIMEOUT:
        if timeout:
            cfg["defaults"].append("timeout %s" % timeout.strip())

    return cfg


def get_tutum_api_urls(dict_var):
    # return sth like: {'HELLO_WORLD': 'https://dashboard.tutum.co/api/v1/service/b4976881-9b87-4cc8-a41e-78ea56ca21c2/'}
    service_urls_dict = {}
    for name, value in dict_var.iteritems():
        position = string.find(name, TUTUM_URL_SUFFIX)
        if position != -1 and name.endswith(TUTUM_URL_SUFFIX):
            cluster_name = name[:position]
            service_urls_dict[cluster_name] = value

    return service_urls_dict


def get_backend_routes(dict_var):
    # Return sth like: {'HELLO_WORLD_1': {'addr': '172.17.0.103', 'port': '80'},
    # 'HELLO_WORLD_2': {'addr': '172.17.0.95', 'port': '80'}}
    addr_port_dict = {}
    for name, value in dict_var.iteritems():
        position = string.find(name, LINK_ENV_PATRTERN)
        if position != -1:
            container_name = name[:position]
            add_port = addr_port_dict.get(container_name, {'addr': "", 'port': ""})
            if name.endswith(LINK_ADDR_SUFFIX):
                add_port['addr'] = value
            elif name.endswith(LINK_PORT_SUFFIX):
                add_port['port'] = value
            addr_port_dict[container_name] = add_port

    return addr_port_dict


def update_cfg(cfg, backend_routes, vhost):
    if not vhost:
        frontend = []
        frontend.append("bind 0.0.0.0:80")
        frontend.append("default_backend default_service")
        if SSL:
            frontend.append("redirect scheme https code 301 if !{ ssl_fc }"),
            frontend.append("bind 0.0.0.0:443 %s" % SSL)

        backend = []
        backend.append("balance %s" % BALANCE)
        for container_name, addr_port in backend_routes.iteritems():
            backend.append("server %s %s:%s" % (container_name, addr_port["addr"], addr_port["port"]))
        cfg["frontend default_frontend"] = frontend
        cfg["backend default_service"] = backend


def update_config_file(cfg_text, config_file):
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
        # reload haproxy
        logger.info("Reloading haproxy")
        process = subprocess.Popen(HAPROXY_CMD + ["-sf", str(HAPROXY_CURRENT_SUBPROCESS.pid)])
        HAPROXY_CURRENT_SUBPROCESS.wait()
        HAPROXY_CURRENT_SUBPROCESS = process
    else:
        # Launch haproxy
        logger.info("Lauching haproxy")
        HAPROXY_CURRENT_SUBPROCESS = subprocess.Popen(HAPROXY_CMD)


if __name__ == "__main__":
    if DEBUG:
        logging.basicConfig(stream=sys.stdout, level=logging.DEBUG)
    else:
        logging.basicConfig(stream=sys.stdout, level=logging.INFO)

    session = requests.Session()
    headers = {"Authorization": TUTUM_AUTH}
    cfg = create_default_cfg(MAXCONN, MODE)
    tutum_api_urls = get_tutum_api_urls(os.environ)

    vhost = {}
    if VIRTUAL_HOST:
        for host in VIRTUAL_HOST:
            tmp = host.split("=", 2)
            if len(tmp) == 2:
                vhost[tmp[0].strip()] = tmp[1].strip()

    # Start HAProxy
    backend_routes = get_backend_routes(os.environ)
    update_cfg(cfg, backend_routes, vhost)
    cfg_text = get_cfg_text(cfg)
    logger.info("HAProxy cfg:\n\n%s\n" % cfg_text)
    update_config_file(cfg_text, CONFIG_FILE)
    reload_haproxy()

    while True:
        try:
            # Runs in tutum with full access, able to update backend dynamically on service scaling
            if tutum_api_urls != {} and TUTUM_AUTH:
                for service_name, url in tutum_api_urls.iteritems():
                    # Get service info
                    r = session.get(url, headers=headers)
                    if r.status_code != 200:
                        raise Exception(
                            "Request url %s gives us a %d error code. Response: %s" % (r.status_code, r.text))
                    else:
                        r.raise_for_status()

                    service_details = r.json()
                    logger.debug("Balancer: Container Cluster info. %s", service_details)

                    backend_routes = get_backend_routes(service_details.get("link_variables", {}))
                    update_cfg(cfg, backend_routes, vhost)
                    old_text = cfg_text
                    cfg_text = get_cfg_text(cfg)
                    logger.info("HAProxy cfg:\n%s" % cfg_text)

                    if old_text != cfg_text:
                        logger.info("HAProxy configuration has been changed")
                        update_config_file(cfg_text, CONFIG_FILE)
                        reload_haproxy()

        except Exception as e:
            logger.exception("Error: %s" % e)
        time.sleep(POLLING_PERIOD)