import os
import logging
import subprocess
import time
import copy
from collections import OrderedDict

import tutum

from parser import Specs

logger = logging.getLogger("haproxy")


class Haproxy(object):
    # envvar
    envvar_default_ssl_cert = os.getenv("DEFAULT_SSL_CERT") or os.getenv("SSL_CERT")
    envvar_maxconn = os.getenv("MAXCONN", "4096")
    envvar_mode = os.getenv("MODE", "http")
    envvar_option = os.getenv("OPTION", "redispatch, httplog, dontlognull, forwardfor").split(",")
    envvar_rsyslog_destnation = os.getenv("RSYSLOG_DESTINATION", "127.0.0.1")
    envvar_ssl_bind_ciphers = os.getenv("SSL_BIND_CIPHERS")
    envvar_ssl_bind_options = os.getenv("SSL_BIND_OPTIONS")
    envvar_stats_auth = os.getenv("STATS_AUTH", "stats:stats")
    envvar_stats_port = os.getenv("STATS_PORT", "1936")
    envvar_timeout = os.getenv("TIMEOUT", "connect 5000, client 50000, server 50000").split(",")

    # envvar overwritable
    envvar_balance = os.getenv("BALANCE", "roundrobin")
    envvar_appsession = os.getenv("APPSESSION")

    # const var
    const_cert_dir = "/certs/"
    const_config_file = "/haproxy.cfg"
    const_command = ['/usr/sbin/haproxy', '-f', const_config_file, '-db', '-q']
    const_api_retry = 10  # seconds

    # class var
    cls_container_uri = os.getenv("TUTUM_CONTAINER_API_URI")
    cls_service_uri = os.getenv("TUTUM_SERVICE_API_URI")
    cls_tutum_auth = os.getenv("TUTUM_AUTH")
    cls_linked_services = None
    cls_cfg = None
    cls_haproxy_process = None
    cls_certs = []

    def __init__(self):
        self.ssl = None
        self.ssl_updated = False
        self.routes_added = []
        self.require_default_route = False
        if Haproxy.cls_container_uri and Haproxy.cls_service_uri and Haproxy.cls_tutum_auth:
            logger.info("Loading HAProxy definition through REST API")
            container = self.fetch_tutum_obj(Haproxy.cls_container_uri)
            service = self.fetch_tutum_obj(Haproxy.cls_service_uri)
            Haproxy.cls_linked_services = [srv.get("to_service") for srv in service.linked_to_service]
            self.specs = Specs(container, service)
        else:
            logger.info("Loading HAProxy definition from environment variables")
            Haproxy.cls_linked_services = None
            Haproxy.specs = Specs()

    def update(self):
        cfg_dict = OrderedDict()
        self._config_ssl()
        cfg_dict.update(self._config_default())
        for cfg in self._config_tcp():
            cfg_dict.update(cfg)
        cfg_dict.update(self._config_frontend())
        cfg_dict.update(self._config_backend())

        cfg = self._prettify(cfg_dict)
        if Haproxy.cls_service_uri and Haproxy.cls_container_uri and Haproxy.cls_tutum_auth:
            if Haproxy.cls_cfg != cfg:
                if not Haproxy.cls_cfg:
                    logger.info("HAProxy configuration:\n%s" % cfg)
                else:
                    logger.info("HAProxy configuration is updated:\n%s" % cfg)
                Haproxy.cls_cfg = cfg
                if self._save_conf():
                    self._run()
            elif self.ssl_updated:
                self._run()
            else:
                logger.info("HAProxy configuration remains unchanged")
        else:
            logger.info("HAProxy configuration:\n%s" % cfg)
            Haproxy.cls_cfg = cfg
            self._save_conf()
            logger.info("Launching HAProxy")
            p = subprocess.Popen(self.const_command)
            p.wait()

    def _run(self):
        if Haproxy.cls_haproxy_process:
            # Reload haproxy
            logger.info("Reloading HAProxy")
            process = subprocess.Popen(self.const_command + ["-sf", str(Haproxy.cls_haproxy_process.pid)])
            Haproxy.cls_haproxy_process.wait()
            Haproxy.cls_haproxy_process = process
            logger.info("HAProxy has been reloaded\n******************************")
        else:
            # Launch haproxy
            logger.info("Launching HAProxy\n******************************")
            Haproxy.cls_haproxy_process = subprocess.Popen(self.const_command)

    @staticmethod
    def _prettify(cfg):
        text = ""
        for section, contents in cfg.items():
            text += "%s\n" % section
            for content in contents:
                text += "  %s\n" % content
        return text.strip()

    def _config_ssl(self):
        certs = []
        if self.envvar_default_ssl_cert:
            certs.append(self.envvar_default_ssl_cert)
        certs.extend(self.specs.get_default_ssl_cert())
        certs.extend(self.specs.get_ssl_cert())
        if certs:
            if set(certs) != set(Haproxy.cls_certs):
                Haproxy.cls_certs = copy.copy(certs)
                self.ssl_updated = True
                self._save_certs(certs)
            self.ssl = "ssl crt /certs/"

    def _save_certs(self, certs):
        try:
            if not os.path.exists(self.const_cert_dir):
                os.makedirs(self.const_cert_dir)
        except Exception as e:
            logger.error(e)
        for index, cert in enumerate(certs):
            cert_filename = "%scert%d.pem" % (self.const_cert_dir, index)
            try:
                with open(cert_filename, 'w') as f:
                    f.write(cert.replace("\\n", '\n'))
            except Exception as e:
                logger.error(e)
        logger.info("SSL certificates are updated")

    def _save_conf(self):
        try:
            with open(self.const_config_file, 'w') as f:
                f.write(Haproxy.cls_cfg)
            return True
        except Exception as e:
            logger.error(e)
            return False

    @classmethod
    def _config_default(cls):
        cfg = OrderedDict({
            "global": ["log %s local0" % cls.envvar_rsyslog_destnation,
                       "log %s local1 notice" % cls.envvar_rsyslog_destnation,
                       "log-send-hostname",
                       "maxconn %s" % cls.envvar_maxconn,
                       "tune.ssl.default-dh-param 2048",
                       "pidfile /var/run/haproxy.pid",
                       "user haproxy",
                       "group haproxy",
                       "daemon",
                       "stats socket /var/run/haproxy.stats level admin"],
            "listen stats": ["bind :%s" % cls.envvar_stats_port,
                             "mode http",
                             "stats enable",
                             "timeout connect 10s",
                             "timeout client 1m",
                             "timeout server 1m",
                             "stats hide-version",
                             "stats realm Haproxy\ Statistics",
                             "stats uri /",
                             "stats auth %s" % cls.envvar_stats_auth],
            "defaults": ["balance %s" % cls.envvar_balance,
                         "log global",
                         "mode %s" % cls.envvar_mode]})
        for opt in cls.envvar_option:
            if opt:
                cfg["defaults"].append("option %s" % opt.strip())
        for t in cls.envvar_timeout:
            if t:
                cfg["defaults"].append("timeout %s" % t.strip())
        if cls.envvar_ssl_bind_options:
            cfg["global"].append("ssl-default-bind-options %s" % cls.envvar_ssl_bind_options)
        if cls.envvar_ssl_bind_ciphers:
            cfg["global"].append("ssl-default-bind-ciphers %s" % cls.envvar_ssl_bind_ciphers)
        return cfg

    def _config_tcp(self):
        cfgs = []
        if not self._get_service_attr("tcp_ports"):
            return cfgs

        ports = []
        for service_alias in self.specs.service_aliases:
            _ports = self._get_service_attr("tcp_ports", service_alias)
            if _ports:
                ports.extend(_ports)

        for port in set(ports):
            cfg = OrderedDict()
            listen = ["bind :%s" % port, "mode tcp"]
            for _service_alias, routes in self.specs.get_routes().iteritems():
                _ports = self._get_service_attr("tcp_ports", _service_alias)
                if _ports and port in self._get_service_attr("tcp_ports", _service_alias):
                    for route in routes:
                        if route["port"] in self._get_service_attr("tcp_ports", _service_alias) and \
                                        route["port"] == port:
                            tcp_route = "server %s %s:%s" % (route["container_name"], route["addr"], route["port"])
                            listen.append(tcp_route)
                            self.routes_added.append(route)

            cfg["listen port_%s" % port] = listen
            cfgs.append(cfg)

        return cfgs

    def _config_frontend(self):
        cfg = OrderedDict()
        if self.specs.get_vhosts():
            frontends_dict = {}
            rule_counter = 0
            for vhost in self.specs.get_vhosts():
                rule_counter += 1
                port = vhost["port"]

                # initialize bind clause for each port
                if port not in frontends_dict:
                    ssl = False
                    for v in self.specs.get_vhosts():
                        if v["port"] == port:
                            scheme = v["scheme"].lower()
                            if scheme in ["https", "wss"] and self.ssl:
                                ssl = True
                                break
                    if ssl:
                        frontends_dict[port] = ["bind :%s %s" % (port, self.ssl), "reqadd X-Forwarded-Proto:\ https"]
                    else:
                        frontends_dict[port] = ["bind :%s" % port]

                # calculate virtual host rule
                host_acl = ["acl", "host_rule_%d" % rule_counter]
                host = vhost["host"].strip("/")
                if host == "*":
                    pass
                elif "*" in host:
                    host_acl.append("hdr_reg(host) -i %s" % host.replace(".", "\.").replace("*", ".*"))
                elif host.startswith("*"):
                    host_acl.append("hdr_end(host) -i %s" % host[1:])
                elif host.endswith("*"):
                    host_acl.append("hdr_beg(host) -i %s" % host[:-1])
                elif host:
                    host_acl.append("hdr_dom(host) -i %s" % host)

                # calculate virtual path rules
                path_acl = ["acl", "path_rule_%d" % rule_counter]
                path = vhost["path"].strip()
                if "*" in path[1:-1]:
                    path_acl.append("path_reg -i %s" % path.replace(".", "\.").replace("*", ".*"))
                elif path.startswith("*"):
                    path_acl.append("path_end -i %s" % path[1:])
                elif path.endswith("*"):
                    path_acl.append("path_beg -i %s" % path[:-1])
                elif path:
                    path_acl.append("path -i %s" % path)

                if len(host_acl) > 2 or len(path_acl):
                    service_alias = vhost["service_alias"]
                    if len(host_acl) > 2 and len(path_acl) > 2:
                        acl_condition = "host_rule_%d path_rule_%d" % (rule_counter, rule_counter)
                        acl_rule = [" ".join(host_acl), " ".join(path_acl),
                                "use_backend SERVICE_%s if %s" % (service_alias, acl_condition)]
                    elif len(host_acl) > 2:
                        acl_condition = "host_rule_%d" % rule_counter
                        acl_rule = [" ".join(host_acl),
                                "use_backend SERVICE_%s if %s" % (service_alias, acl_condition)]
                    elif len(path_acl) > 2:
                        acl_condition = "path_rule_%d" % rule_counter
                        acl_rule = [" ".join(path_acl),
                                "use_backend SERVICE_%s if %s" % (service_alias, acl_condition)]

                    frontends_dict[port].extend(acl_rule)

            for port, frontend in frontends_dict.iteritems():
                cfg["frontend port_%s" % port] = frontend

        else:
            all_routes = []
            for routes in self.specs.get_routes().itervalues():
                all_routes.extend(routes)
            if len(self.routes_added) < len(all_routes):
                self.require_default_route = True

            if self.require_default_route:
                frontend = ["bind :80"]
                if self.ssl and self:
                    frontend.append("bind :443 %s" % self.ssl)
                    frontend.append("reqadd X-Forwarded-Proto:\ https")
                    if self.specs.get_force_ssl():
                        frontend.append("redirect scheme https code 301 if !{ ssl_fc }")
                frontend.append("default_backend default_service")
                cfg["frontend default_frontend"] = frontend

        return cfg

    def _config_backend(self):
        cfg = OrderedDict()

        if not self.specs.get_vhosts():
            services_aliases = [None]
        else:
            services_aliases = self.specs.service_aliases

        for service_alias in services_aliases:
            backend = []
            is_sticky = False

            # To add an entry to backend section: append to backend
            # To add items to a route: append to route_setting
            balance = self._get_service_attr("balance", service_alias)
            if balance:
                backend.append("balance %s" % balance)

            appsession = self._get_service_attr("appsession", service_alias)
            if appsession:
                backend.append("appsession %s" % appsession)
                is_sticky = True

            cookie = self._get_service_attr("cookie", service_alias)
            if cookie:
                backend.append("cookie %s" % cookie)
                is_sticky = True

            force_ssl = self._get_service_attr("force_ssl", service_alias)
            if force_ssl:
                backend.append("redirect scheme https code 301 if !{ ssl_fc }")

            for _service_alias, routes in self.specs.get_routes().iteritems():
                if not service_alias or _service_alias == service_alias:
                    for route in routes:
                        # avoid adding those tcp routes adding http backends
                        if route in self.routes_added:
                            continue

                        backend_route = "server %s %s:%s" % (route["container_name"], route["addr"], route["port"])
                        if is_sticky:
                            backend_route = " ".join([backend_route, "cookie %s" % route["container_name"]])
                        backend.append(backend_route)

            if not service_alias:
                if self.require_default_route:
                    cfg["backend default_service"] = sorted(backend)
            else:
                if self._get_service_attr("virtual_host", _service_alias):
                    cfg["backend SERVICE_%s" % service_alias] = sorted(backend)
                else:
                    cfg["backend default_service"] = sorted(backend)
        return cfg

    def _get_service_attr(self, attr_name, service_alias=None):
        # service is None, when there is no virtual host is set
        if service_alias:
            try:
                return self.specs.get_details()[service_alias][attr_name]
            except:
                return None

        else:
            # Randomly pick a None value from the linked service
            for _service_alias in self.specs.get_details().iterkeys():
                if self.specs.get_details()[_service_alias][attr_name]:
                    return self.specs.get_details()[_service_alias][attr_name]
            return None

    @classmethod
    def fetch_tutum_obj(cls, uri):
        if not uri:
            return None

        while True:
            try:
                obj = tutum.Utils.fetch_by_resource_uri(uri)
                break
            except Exception as e:
                logger.error(e)
                time.sleep(cls.const_api_retry)
        return obj
