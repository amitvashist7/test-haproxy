tutum-docker-clusterproxy
=========================

HAproxy image that balances between linked containers and, if launched in Tutum, 
reconfigures itself when a linked cluster member joins or leaves


Usage
-----

Make sure your application container exposes port 80. Then, launch it:

	docker run -d --name web1 tutum/hello-world
	docker run -d --name web2 tutum/hello-world

Then, run tutum/haproxy-http linking it to the target containers:

	docker run -d -p 80:80 --link web1:web1 --link web2:web2 tutum/haproxy


Configuration
-------------

You can overwrite the following HAproxy configuration options:

* `PORT` (default: `80`): Port HAproxy will bind to, and the port that will forward requests to.
* `MODE` (default: `http`): Mode of load balancing for HAproxy. Possible values include: `http`, `tcp`, `health`.
* `BALANCE` (default: `roundrobin`): Load balancing algorithm to use. Possible values include: `roundrobin`, `static-rr`, `source`, `leastconn`.
* `MAXCONN` (default: `4096`): Sets the maximum per-process number of concurrent connections.
* `OPTION` (default: `redispatch`): Comma-separated list of HAproxy `option` entries to the `default` section.
* `TIMEOUT` (default: `connect 5000,client 50000,server 50000`): Comma-separated list of HAproxy `timeout` entries to the `default` section.
* `SSL_CERT` (default: `**None**`): An optional certificate to use on the binded port. It should have both the private and public keys content. If using it for HTTPS, remember to also set `PORT=443` as the port is not changed by this setting.
* `VIRTUAL_HOST` (default: `**None**`): Optional. Let HAProxy route by domain name. Format `LINK_ALIAS=DOMAIN`, comma separated.

Check [the HAproxy configuration manual](http://haproxy.1wt.eu/download/1.4/doc/configuration.txt) for more information on the above.


Usage within Tutum
------------------

Launch the service you want to load-balance using Tutum.

Then, launch the load balancer. To do this, select `Jumpstarts` > `Proxies` and select `tutum/haproxy`. During the 3rd step of the wizard, link to the service created earlier, and add "Full Access" API role (this will allow HAproxy to be updated dynamically by querying Tutum's API). 

That's it - the proxy container will start querying Tutum's API for an updated list of containers in the service and reconfigure itself automatically.

How to use this container
-------------------------
1. My service container(hello) exposes port 8080, I want the HAProxy listens to port 80

    Run this container with `--link hello:hello -e PORT=8080 -p 80:80`

2. My service container(hello) exposes port 80, I want the HAProxy listens to port 8080

    Run this container with `--link hello:hello -p 8080:80`

3. How to use SSL?

    Run this container with `-e SSL_CERT="YOUR_CERT_TEXT"`

    The certificate is a combination of public certificate and private key. Remember to put `\n` between each line of the certificate. To make it simple, suppose your certificate is stored in `~/cert.pem`, you can run this container with `-e SSL_CERT="$(awk 1 ORS='\\n' ~/cert.pem)"`

4. My service container(hello) exposes port 8080, I want to access it with SSL using HAProxy

    Run this container with `-e SSL_CERT="YOUR_CERT_TEXT" -e PORT=8080 -p 443:443`

    If you also publish port 80, the user accessing port 80 will be redirect to 443 using https

5. I want to set up virtual host routing by domain

    Run this container with `--link hello1:hello1 --link hello2:hello2 -e VIRTUAL_HOST="hello1=www.hello1.com, hello2=www.hello2.com" -p 80:80`

    Notice that the format of VIRTUAL_HOST is `LINK_ALIAS=DOMAIN`, where LINK_ALIAS must match the link alias.

    In the example above, when you access http://www.hello1.com, it will show the service running in container hello1, and http://www.hello2.com will go to container hello2
