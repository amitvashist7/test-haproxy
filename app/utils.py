import string

from globals import VIRTUAL_HOST_SUFFIX


def parse_vhost_from_envvar(envvars):
    # Input: "web1=a.com, b.com, web=c.com"
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
            vhost[container_name] = domain_list
        if tmp_len == 1:
            domain = tmp[0].strip()
            domain_list = vhost.get(container_name, [])
            domain_list.append(domain)
            vhost[container_name] = domain_list
    return vhost


def parse_vhost(virtualhost, envvars):
    # Input: virtualhost - "web1=a.com, b.com, web=c.com" or None
    # envvars - "
    # {'web1':['a.com', 'b.com'], 'web2':['c.com']
    vhost = {}
    if virtualhost:
        vhost.update(parse_vhost_from_envvar(virtualhost))
    else:
        # vhost specified in the linked containers
        for name, value in envvars:
            position = string.find(name, VIRTUAL_HOST_SUFFIX)
            if position != -1 and value != "**None**":
                vhost.update(parse_vhost_from_envvar("%s=%s" % (name[:position], value)))
    return vhost


def parse_uuid_from_url(url):
    # Input: https://dashboard.tutum.co/api/v1/container/f04588e5-9388-4718-b932-cd98815cc0d5/
    # Output: f04588e5-9388-4718-b932-cd98815cc0d5
    if url:
        terms = url.strip().strip("/").split("/")
        if len(terms) > 0:
            return terms[-1]
    return None


def parse_tutum_service_endpoint(envvars):
    # Input: {'HELLO_A_ENV_TUTUM_SERVICE_API_URL': 'https://dashboard.tutum.co/api/v1/service/b3380257-c5ff-4219-ad33-e844b427477d/',
    # 'HELLO_A_1_ENV_TUTUM_SERVICE_API_URL': 'https://dashboard.tutum.co/api/v1/service/b3380257-c5ff-4219-ad33-e844b427477d/',
    # 'HELLO_B_ENV_TUTUM_SERVICE_API_URL': 'https://dashboard.tutum.co/api/v1/service/f04588e5-9388-4718-b932-cd98815cc0d5/',
    # 'HELLO_B_1_ENV_TUTUM_SERVICE_API_URL': 'https://dashboard.tutum.co/api/v1/service/f04588e5-9388-4718-b932-cd98815cc0d5/'}
    # Output: ["/api/v1/service/b3380257-c5ff-4219-ad33-e844b427477d/",
    #         "/api/v1/service/f04588e5-9388-4718-b932-cd98815cc0d5/"]
    service_endpoints = []
    for key, value in envvars:
        if key.endswith("_ENV_TUTUM_SERVICE_API_URL"):
            position = string.find(value, "/api/v1/service")
            if position != -1:
                endpoint = value[position:]
                if endpoint not in service_endpoints:
                    service_endpoints.append(endpoint)
    return service_endpoints