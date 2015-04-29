import socket
import string
import re

from constants import LINK_ENV_PATTERN, LINK_ADDR_SUFFIX, LINK_PORT_SUFFIX, BACKEND_PORTS, \
    VIRTUAL_HOST_SUFFIX, TUTUM_ENDPOINT_PREFIX


ENDPOINT_MATCH = re.compile(r"(?P<proto>tcp|udp):\/\/(?P<addr>[^:]*):(?P<port>.*)")


def parse_vhost_from_envvar(envvars):
    # Input:  "web1=a.com, b.com, web=c.com"
    # Output: {'web1':['a.com', 'b.com'], 'web2':['c.com']
    vhost = {}
    container_name = None
    for term in envvars.split(','):
        tmp = term.strip().split("=", 2)
        tmp_len = len(tmp)
        if tmp_len == 2:
            container_name = tmp[0].strip()
            domain = tmp[1].strip()
            domain_list = vhost.get(container_name, [])
            domain_list.append(domain)
            if container_name:
                vhost[container_name] = domain_list
        if tmp_len == 1 and container_name:
            domain = tmp[0].strip()
            domain_list = vhost.get(container_name, [])
            domain_list.append(domain)
            vhost[container_name] = domain_list
    return vhost


def parse_vhost(virtualhost, envvars):
    # Input:  virtualhost - None or "web1=a.com, b.com, web=c.com"
    # envvars     - {'WEB_1_ENV_VIRTUAL_HOST':'a.com', 'b.com', 'WEB_2_ENV_VIRTUAL_HOST':'c.com'}
    # Output: {'web1':['a.com', 'b.com'], 'web2':['c.com']
    vhost = {}
    if virtualhost:
        vhost.update(parse_vhost_from_envvar(virtualhost))
    if not vhost:
        # try to parse vhost specified in the linked containers
        for name, value in envvars.iteritems():
            position = string.find(name, VIRTUAL_HOST_SUFFIX)
            if position != -1 and value != "**None**":
                vhost.update(parse_vhost_from_envvar("%s=%s" % (name[:position], value)))
    return vhost


def parse_uuid_from_url(url):
    # Input:  https://dashboard.tutum.co/api/v1/container/f04588e5-9388-4718-b932-cd98815cc0d5/
    # Output: f04588e5-9388-4718-b932-cd98815cc0d5
    if url:
        terms = url.strip().strip("/").split("/")
        if len(terms) > 0:
            return terms[-1]
    return None


def parse_endpoint_from_url(url):
    # Input:  https://dashboard.tutum.co/api/v1/container/f04588e5-9388-4718-b932-cd98815cc0d5/
    # Output: /api/v1/container/f04588e5-9388-4718-b932-cd98815cc0d5/
    endpoint = ""
    position = string.find(url, TUTUM_ENDPOINT_PREFIX)
    if position != -1:
        endpoint = url[position:]
    return endpoint


def parse_backend_routes(dict_var):
    # Input:  {'HELLO_2_PORT_80_TCP_ADDR': '10.7.0.5}
    # 'HELLO_1_PORT_80_TCP_ADDR': '10.7.0.3}
    # 'HELLO_2_PORT_80_TCP_PORT': '80'
    # 'HELLO_2_PORT_80_TCP_PORT': '80'}
    # Output: {'HELLO_1': {'addr': '172.17.0.103', 'port': '80'},
    #          'HELLO_2': {'addr': '172.17.0.95', 'port': '80'}}
    addr_port_dict = {}
    for name, value in dict_var.iteritems():
        position = string.find(name, LINK_ENV_PATTERN)
        if position != -1:
            container_name = name[:position]
            addr_port = addr_port_dict.get(container_name, {'addr': "", 'port': ""})
            try:
                addr_port['addr'] = socket.gethostbyname(container_name.lower())
            except socket.gaierror:
                try:
                    addr_port['addr'] = socket.gethostbyname(container_name.lower().replace("_", "-"))
                except socket.gaierror:
                    if name.endswith(LINK_ADDR_SUFFIX):
                        addr_port['addr'] = value
            if name.endswith(LINK_PORT_SUFFIX):
                addr_port['port'] = value
            addr_port_dict[container_name] = addr_port
    return addr_port_dict


def parse_backend_routes_tutum(container_links):
    # Input:  [{"endpoints": {"80/tcp": "tcp://10.7.0.3:80"},
    # "name": "hello-1",
    #           "from_container": "/api/v1/container/702d18d4-7934-4715-aea3-c0637f1a4129/",
    #           "to_container": "/api/v1/container/60b850b7-593e-461b-9b61-5fe1f5a681aa/"
    #          },
    #          {"endpoints": {"80/tcp": "tcp://10.7.0.5:80"},
    #           "name": "hello-2",
    #           "from_container": "/api/v1/container/702d18d4-7934-4715-aea3-c0637f1a4129/",
    #           "to_container": "/api/v1/container/65b18c61-b551-4c7f-a92b-06ef95494d5a/"
    #          }]
    # Output: {'HELLO_1': {'proto': 'tcp', 'addr': '10.7.0.3', 'port': '80'},
    #          'HELLO_2': {'proto': 'tcp', 'addr': '10.7.0.5', 'port': '80'}}

    if not hasattr(parse_backend_routes_tutum, "endpoint_match"):
        parse_backend_routes_tutum.endpoint_match = re.compile(r"(?P<proto>tcp|udp):\/\/(?P<addr>[^:]*):(?P<port>.*)")

    routes = {}
    for link in container_links:
        for port, endpoint in link.get("endpoints", {}).iteritems():
            if port in ["%s/tcp" % x for x in BACKEND_PORTS]:
                container_name = link.get("name").upper().replace("-", "_")
                if container_name:
                    routes[container_name] = parse_backend_routes_tutum.endpoint_match.match(endpoint).groupdict()
    return routes