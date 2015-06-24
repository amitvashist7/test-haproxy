import os
import logging
import subprocess
import time
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
    cls__cfg = None
    cls_haproxy_process = None

    def __init__(self):
        self.ssl = None
        if Haproxy.cls_container_uri and Haproxy.cls_service_uri and Haproxy.cls_tutum_auth:
            logger.info("Loading HAProxy definition through REST API")
            container = self.fetch_tutum_obj(Haproxy.cls_container_uri)
            service = self.fetch_tutum_obj(Haproxy.cls_service_uri)
            Haproxy.cls_linked_services = [srv.get("to_service") for srv in service.linked_to_service]
            self.link_specs = Specs(container, service)
        else:
            logger.info("Loading HAProxy definition from environment variables")
            Haproxy.cls_linked_services = None
            Haproxy.link_specs = Specs()

    def update(self):
        cfg_dict = OrderedDict()
        self._config_ssl()
        cfg_dict.update(self._config_default())
        cfg_dict.update(self._config_frontend())
        cfg_dict.update(self._config_backend())

        cfg = self._prettify(cfg_dict)
        if Haproxy.cls_service_uri and Haproxy.cls_container_uri and Haproxy.cls_tutum_auth:
            if Haproxy.cls__cfg != cfg:
                if not Haproxy.cls__cfg:
                    logger.info("HAProxy configuration:\n%s" % cfg)
                else:
                    logger.info("HAProxy configuration is updated:\n%s" % cfg)
                Haproxy.cls__cfg = cfg
                if self._save_conf():
                    self._run()
            else:
                logger.info("HAProxy configuration remains unchanged")
        else:
            logger.info("HAProxy configuration:\n%s" % cfg)
            Haproxy.cls__cfg = cfg
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
        certs.extend(self.link_specs.get_default_ssl_cert())
        certs.extend(self.link_specs.get_ssl_cert())
        self._save_certs(certs)
        if certs:
            self.ssl = "ssl crt /certs/"

    def _save_certs(self, certs):
        try:
            if not os.path.exists(self.const_cert_dir):
                os.makedirs(self.const_cert_dir)
        except Exception as e:
            logger.error(e)
        for index, cert in enumerate(certs):
            cert_filename = "%scert%d.pem" % (self.const_cert_dir, index)
            logger.info(cert_filename)
            try:
                with open(cert_filename, 'w') as f:
                    f.write(cert.replace("\\n", '\n'))
            except Exception as e:
                logger.error(e)

    def _save_conf(self):
        try:
            with open(self.const_config_file, 'w') as f:
                f.write(Haproxy.cls__cfg)
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

    def _config_frontend(self):
        cfg = OrderedDict()
        if self.link_specs.get_vhosts():
            frontends_dict = {}
            rule_counter = 0
            for vhost in self.link_specs.get_vhosts():
                # caculate acl rules
                rule_counter += 1
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
                    port = vhost["port"]
                    if len(host_acl) > 2 and len(path_acl) > 2:
                        rule = [" ".join(host_acl), " ".join(path_acl),
                                "use_backend SERVICE_%s if host_rule_%d path_rule_%d" %
                                (vhost["service_alias"], rule_counter, rule_counter)]
                    elif len(host_acl) > 2:
                        rule = [" ".join(host_acl), "use_backend SERVICE_%s if host_rule_%d" %
                                (vhost["service_alias"], rule_counter)]
                    elif len(path_acl) > 2:
                        rule = [" ".join(path_acl), "use_backend SERVICE_%s if path_rule_%d" %
                                (vhost["service_alias"], rule_counter)]

                    if port in frontends_dict:
                        frontend = frontends_dict[port]
                        frontend.extend(rule)
                    else:
                        ssl = False
                        force_ssl = False
                        for v in self.link_specs.get_vhosts():
                            if v["port"] == port:
                                service = v["service_alias"]
                                if self.link_specs.specs[service]["force_ssl"]:
                                    force_ssl = True
                                scheme = v["scheme"].lower()
                                if scheme in ["https", "wss"]:
                                    ssl = True
                                    break
                        if ssl:
                            frontend = ["bind :%s %s" % (port, self.ssl)]
                            frontend.append("reqadd X-Forwarded-Proto:\ https")
                        else:
                            frontend = ["bind :%s" % port]
                            if force_ssl:
                                frontend.append("redirect scheme https code 301 if !{ ssl_fc }")

                        frontend.extend(rule)
                        frontends_dict[port] = frontend
            for port, frontend in frontends_dict.iteritems():
                cfg["frontend port_%s" % port] = frontend
        else:
            frontend = ["bind :80"]
            if self.ssl:
                frontend.append("bind :443 %s" % self.ssl)
                frontend.append("reqadd X-Forwarded-Proto:\ https")
                if self.link_specs.get_force_ssl():
                    frontend.append("redirect scheme https code 301 if !{ ssl_fc }")
            frontend.append("default_backend default_service")
            cfg["frontend default_frontend"] = frontend
        return cfg

    def _config_backend(self):
        cfg = OrderedDict()

        if not self.link_specs.get_vhosts():
            services = [None]
        else:
            services = self.link_specs.service_aliases

        for service in services:
            backend = []
            route_setting = []

            # To add an entry to backend section: append to backend
            # To add items to a route: append to route_setting
            balance = self._get_service_attr("balance", service)
            if balance:
                backend.append("balance %s" % balance)

            appsession = self._get_service_attr("appsession", service)
            if appsession:
                backend.append("appsession %s len 64 timeout 3h request-learn prefix" % appsession)
                route_setting.append("cookie check")

            for service_alias, routes in self.link_specs.get_routes().iteritems():
                if not service or service == service_alias:
                    for route in routes:
                        backend_route = "server %s %s:%s" % (route["container_name"], route["addr"], route["port"])
                        if route_setting:
                            backend_route = " ".join([backend_route, " ".join(route_setting)])
                        backend.append(backend_route)

            if not service:
                cfg["backend default_service"] = sorted(backend)
            else:
                cfg["backend SERVICE_%s" % service] = sorted(backend)
        return cfg

    def _get_service_attr(self, attr_name, service_alias=None):
        attr_value = None

        # check if the attribute is set in the linked services
        method_name = "get_%s" % attr_name
        if hasattr(self.link_specs, method_name):
            attr = getattr(self.link_specs, method_name)()
        else:
            return None

        # random pick up a value when service_alias is None, which means haproxy is running not with tutum
        if service_alias:
            attr_value = attr.get(service_alias)
        else:
            if attr:
                attr_value = next(attr.itervalues())

        # try to see if there is a setting in haproxy container globally
        if not attr_value:
            attr_value = getattr(Haproxy, "envvar_%s" % attr_name, None)

        return attr_value

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
