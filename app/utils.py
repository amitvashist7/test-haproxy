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
            if container_name:
                vhost[container_name] = domain_list
        if tmp_len == 1 and container_name:
            domain = tmp[0].strip()
            domain_list = vhost.get(container_name, [])
            domain_list.append(domain)
            vhost[container_name] = domain_list
    return vhost