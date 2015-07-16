FROM ubuntu:trusty
MAINTAINER Feng Honglin <hfeng@tutum.co>

# Install pip and haproxy
RUN echo 'deb http://ppa.launchpad.net/vbernat/haproxy-1.5/ubuntu trusty main' >> /etc/apt/sources.list && \
    echo 'deb-src http://ppa.launchpad.net/vbernat/haproxy-1.5/ubuntu trusty main' >> /etc/apt/sources.list && \
    apt-key adv --keyserver keyserver.ubuntu.com --recv-keys 505D97A41C61B9CD && \
    apt-get update && \
    apt-get install -y --no-install-recommends haproxy python-pip && \
    apt-get clean && \
    pip install python-tutum==0.16.0 && \
    rm -rf /var/lib/apt/lists/*

# the rsyslog destination to where haproxy logs are sent
ENV RSYSLOG_DESTINATION 127.0.0.1

# MODE of operation (http, tcp)
ENV MODE http

# algorithm for load balancing (roundrobin, source, leastconn, ...)
ENV BALANCE roundrobin

# maximum number of connections
ENV MAXCONN 4096

# list of options separated by commas
ENV OPTION redispatch, httplog, dontlognull, forwardfor

# list of timeout entries separated by commas
ENV TIMEOUT connect 5000, client 50000, server 50000

# Stats port
ENV STATS_PORT 1936

# Stats authentication
ENV STATS_AUTH stats:stats

# SSL certificate to use (optional)
ENV SSL_CERT **None**

# SSL bind options to use (optional)
ENV SSL_BIND_OPTIONS no-sslv3

ENV SSL_BIND_CIPHERS ECDHE-RSA-AES128-GCM-SHA256:ECDHE-ECDSA-AES128-SHA256:ECDHE-RSA-AES128-SHA256:ECDHE-ECDSA-AES128-SHA:ECDHE-RSA-AES128-SHA:DHE-RSA-AES128-SHA:ECDHE-ECDSA-AES256-GCM-SHA384:ECDHE-RSA-AES256-GCM-SHA384:ECDHE-ECDSA-AES256-SHA384:ECDHE-RSA-AES256-SHA384:ECDHE-RSA-AES256-SHA:ECDHE-ECDSA-AES256-SHA:AES128-GCM-SHA256:AES128-SHA256:AES128-SHA:AES256-GCM-SHA384:AES256-SHA256:AES256-SHA:DHE-DSS-AES128-SHA:DES-CBC3-SHA

# Add scripts
ADD haproxy /haproxy
ADD run.sh /

EXPOSE 80 443 1936
CMD ["/run.sh"]
