WEB_CONTAINERS = web-a web-b web-c web-d web-e web-f web-g web-h web-i web-j web-k web-l web-m web-n web-o web-p web-q web-r web-s web-t web-u web-v web-w
LB_CONTAINERS = lb0 lb1 lb2 lb3 lb4 lb5 lb6 lb7 lb8 lb9
NODE_FQDN = http://302a494c-tifayuki.node.tutum.io
services = $(shell tutum service ps -q)
random := $(shell awk 'BEGIN{srand();printf("%d", 65536*rand())}')

test:unittest functest linktest;

test-docker-available:
	@set -e
	@echo "==> Testing docker environment"
	docker version || (echo "==> Failed: cannot run docker" && false)
	@echo

clean:test-docker-available
	@set -e
	@echo "==> Cleaning tmp files and containers"
	docker rm -f $(WEB_CONTAINERS) $(LB_CONTAINERS) > /dev/null 2>&1 || true
	rm -f *.pem output
	@echo

create-cert:clean
	@set -e
	@echo "==> Generating certificate for tests"
	openssl req -x509 -newkey rsa:2048 -keyout key0.pem -out ca0.pem -days 1080 -nodes -subj '/CN=localhost/O=My Company Name LTD./C=US'
	cp key0.pem cert0.pem
	cat ca0.pem >> cert0.pem
	openssl req -x509 -newkey rsa:2048 -keyout key1.pem -out ca1.pem -days 1080 -nodes -subj '/CN=web-o.org/O=My Company Name LTD./C=US'
	cp key1.pem cert1.pem
	cat ca1.pem >> cert1.pem
	openssl req -x509 -newkey rsa:2048 -keyout key2.pem -out ca2.pem -days 1080 -nodes -subj '/CN=web-p.org/O=My Company Name LTD./C=US'
	cp key2.pem cert2.pem
	cat ca2.pem >> cert2.pem
	@echo

build:create-cert
	@set -e
	@echo "==> Building haproxy image"
	docker build -t tifayuki/haproxy-test .
	@echo

cert0 = $(shell awk 1 ORS='\\n' cert0.pem)
cert1 = $(shell awk 1 ORS='\\n' cert1.pem)
cert2 = $(shell awk 1 ORS='\\n' cert2.pem)
functest:build
	@set -e
	@echo "====== Running functionality integration tests ======"

	@echo "==> Testing if haproxy is running properly"
	docker run -d --name web-a -e HOSTNAME="web-a" tutum/hello-world
	docker run -d --name web-b -e HOSTNAME="web-b" tutum/hello-world
	docker run -d --name lb0 --link web-a:web-a --link web-b:web-b -p 8000:80 tifayuki/haproxy-test
	wget --spider --retry-connrefused --no-check-certificate -T 5 http://localhost:8000 > /dev/null
	curl --retry 10 --retry-delay 5 -L -I http://localhost:8000 | grep "200 OK" > /dev/null
	@echo

	@echo "==> Testing SSL settings"
	docker run -d --name lb1 --link web-a:web-a -e DEFAULT_SSL_CERT="$(cert0)" -p 442:443 tifayuki/haproxy-test
	sleep 5
	curl --retry 10 --retry-delay 5 -sSfL --cacert ca0.pem -L https://localhost:442 | grep 'My hostname is web-a' > /dev/null
	@echo

	@echo "==> Testing virtual host"
	docker run -d --name web-c -e HOSTNAME=web-c -e VIRTUAL_HOST=web-c.org tutum/hello-world
	docker run -d --name web-d -e HOSTNAME=web-d -e VIRTUAL_HOST="web-d.org, test.org" tutum/hello-world
	docker run -d --name lb2 --link web-c:web-c --link web-d:web-d -p 8002:80 tifayuki/haproxy-test
	wget --spider --retry-connrefused --no-check-certificate -q -T 5 127.0.0.1:8002 || true > /dev/null
	curl --retry 10 --retry-delay 5 -sSfL -H 'Host:web-c.org' 127.0.0.1:8002 | grep -iF 'My hostname is web-c' > /dev/null
	curl --retry 10 --retry-delay 5 -sSfL -H 'Host:test.org' 127.0.0.1:8002 | grep -iF 'My hostname is web-d' > /dev/null
	curl --retry 10 --retry-delay 5 -sSfL -H 'Host:web-d.org' 127.0.0.1:8002 | grep -iF 'My hostname is web-d' > /dev/null
	@echo

	@echo "==> Testing virtual host starting with wildcard"
	docker run -d --name web-e -e HOSTNAME=web-e -e VIRTUAL_HOST="*.web-e.org" tutum/hello-world
	docker run -d --name lb3 --link web-e:web-e -p 8003:80 tifayuki/haproxy-test
	wget --spider --retry-connrefused --no-check-certificate -q -T 5 127.0.0.1:8003 || true > /dev/null
	curl --retry 10 --retry-delay 5 -sSfL -H 'Host:www.web-e.org' 127.0.0.1:8003 | grep -iF 'My hostname is web-e' > /dev/null
	curl --retry 10 --retry-delay 5 -sSfL -H 'Host:abc.web-e.org' 127.0.0.1:8003 | grep -iF 'My hostname is web-e' > /dev/null
	curl -sSL -H 'Host:abc.web.org' 127.0.0.1:8003 | grep -iF '503 Service Unavailable' > /dev/null
	@echo

	@echo "==> Testing virtual host containing with wildcard"
	docker run -d --name web-f -e HOSTNAME=web-f -e VIRTUAL_HOST="www.web*.org" tutum/hello-world
	docker run -d --name lb4 --link web-f:web-f -p 8004:80 tifayuki/haproxy-test
	wget --spider --retry-connrefused --no-check-certificate -q -T 5 127.0.0.1:8004 || true > /dev/null
	curl --retry 10 --retry-delay 5 -sSfL -H 'Host:www.web.org' 127.0.0.1:8004 | grep -iF 'My hostname is web-f' > /dev/null
	curl --retry 10 --retry-delay 5 -sSfL -H 'Host:www.webtest.org' 127.0.0.1:8004 | grep -iF 'My hostname is web-f' > /dev/null
	curl -sSL -H 'Host:abc.wbbtest.org' 127.0.0.1:8004 | grep -iF '503 Service Unavailable' > /dev/null
	@echo

	@echo "==> Testing virtual path"
	docker run -d --name web-g -e HOSTNAME=web-g -e VIRTUAL_HOST="*/pg/, */pg, */pg/*, */*/pg/*" tutum/hello-world
	docker run -d --name web-h -e HOSTNAME=web-h -e VIRTUAL_HOST="*/ph" tutum/hello-world
	docker run -d --name web-i -e HOSTNAME=web-i -e VIRTUAL_HOST="*/pi/" tutum/hello-world
	docker run -d --name web-j -e HOSTNAME=web-j -e VIRTUAL_HOST="*/pj/*" tutum/hello-world
	docker run -d --name web-k -e HOSTNAME=web-k -e VIRTUAL_HOST="*/*/pk/*" tutum/hello-world
	docker run -d --name web-l -e HOSTNAME=web-l -e VIRTUAL_HOST="*/p*l/" tutum/hello-world
	docker run -d --name web-m -e HOSTNAME=web-m -e VIRTUAL_HOST="*/*.js" tutum/hello-world
	docker run -d --name lb5 --link web-g:web-g --link web-h:web-h --link web-i:web-i --link web-j:web-j --link web-k:web-k --link web-l:web-l --link web-m:web-m -p 8005:80 tifayuki/haproxy-test
	wget --spider --retry-connrefused --no-check-certificate -q -T 5 127.0.0.1:8005 || true > /dev/null
	curl --retry 10 --retry-delay 5 -sSfL 127.0.0.1:8005/pg | grep -iF 'My hostname is web-g' > /dev/null
	curl --retry 10 --retry-delay 5 -sSfL 127.0.0.1:8005/pg/ | grep -iF 'My hostname is web-g' > /dev/null
	curl --retry 10 --retry-delay 5 -sSfL 127.0.0.1:8005/pg/abc | grep -iF 'My hostname is web-g' > /dev/null
	curl --retry 10 --retry-delay 5 -sSfL 127.0.0.1:8005/abc/pg/ | grep -iF 'My hostname is web-g' > /dev/null
	curl --retry 10 --retry-delay 5 -sSfL 127.0.0.1:8005/abc/pg/123 | grep -iF 'My hostname is web-g' > /dev/null
	curl --retry 10 --retry-delay 5 -sSfL "127.0.0.1:8005/pg?u=user&p=pass" | grep -iF 'My hostname is web-g' > /dev/null

	curl --retry 10 --retry-delay 5 -sSfL 127.0.0.1:8005/ph | grep -iF 'My hostname is web-h' > /dev/null
	curl -sSL 127.0.0.1:8005/ph/ | grep -iF '503 Service Unavailable' > /dev/null
	curl -sSL 127.0.0.1:8005/ph/abc | grep -iF '503 Service Unavailable' > /dev/null
	curl -sSL 127.0.0.1:8005/abc/ph/ | grep -iF '503 Service Unavailable' > /dev/null
	curl -sSL 127.0.0.1:8005/abc/ph/123 | grep -iF '503 Service Unavailable' > /dev/null
	curl --retry 10 --retry-delay 5 -sSfL "127.0.0.1:8005/ph?u=user&p=pass" | grep -iF 'My hostname is web-h' > /dev/null

	curl -sSL 127.0.0.1:8005/pi | grep -iF '503 Service Unavailable' > /dev/null
	curl --retry 10 --retry-delay 5 -sSfL 127.0.0.1:8005/pi/ | grep -iF 'My hostname is web-i' > /dev/null
	curl -sSL 127.0.0.1:8005/pi/abc | grep -iF '503 Service Unavailable' > /dev/null
	curl -sSL 127.0.0.1:8005/abc/pi/ | grep -iF '503 Service Unavailable' > /dev/null
	curl -sSL 127.0.0.1:8005/abc/pi/123 | grep -iF '503 Service Unavailable' > /dev/null
	curl --retry 10 --retry-delay 5 -sSfL "127.0.0.1:8005/pi/?u=user&p=pass" | grep -iF 'My hostname is web-i' > /dev/null

	curl -sSL 127.0.0.1:8005/pj | grep -iF '503 Service Unavailable' > /dev/null
	curl --retry 10 --retry-delay 5 -sSfL 127.0.0.1:8005/pj/ | grep -iF 'My hostname is web-j' > /dev/null
	curl --retry 10 --retry-delay 5 -sSfL 127.0.0.1:8005/pj/abc | grep -iF 'My hostname is web-j' > /dev/null
	curl -sSL 127.0.0.1:8005/abc/pj/ | grep -iF '503 Service Unavailable' > /dev/null
	curl -sSL 127.0.0.1:8005/abc/pj/123 | grep -iF '503 Service Unavailable' > /dev/null
	curl --retry 10 --retry-delay 5 -sSfL "127.0.0.1:8005/pj/?u=user&p=pass" | grep -iF 'My hostname is web-j' > /dev/null
	curl --retry 10 --retry-delay 5 -sSfL "127.0.0.1:8005/pj/abc?u=user&p=pass" | grep -iF 'My hostname is web-j' > /dev/null

	curl -sSL 127.0.0.1:8005/pk | grep -iF '503 Service Unavailable' > /dev/null
	curl -sSL 127.0.0.1:8005/pk/ | grep -iF '503 Service Unavailable' > /dev/null
	curl -sSL 127.0.0.1:8005/pk/abc | grep -iF '503 Service Unavailable' > /dev/null
	curl --retry 10 --retry-delay 5 -sSfL 127.0.0.1:8005/abc/pk/ | grep -iF 'My hostname is web-k' > /dev/null
	curl --retry 10 --retry-delay 5 -sSfL 127.0.0.1:8005/abc/pk/123 | grep -iF 'My hostname is web-k' > /dev/null
	curl --retry 10 --retry-delay 5 -sSfL "127.0.0.1:8005/abc/pk/?u=user&p=pass" | grep -iF 'My hostname is web-k' > /dev/null
	curl --retry 10 --retry-delay 5 -sSfL "127.0.0.1:8005/abc/pk/123?u=user&p=pass" | grep -iF 'My hostname is web-k' > /dev/null

	curl -sSL 127.0.0.1:8005/pl | grep -iF '503 Service Unavailable' > /dev/null
	curl --retry 10 --retry-delay 5 -sSfL 127.0.0.1:8005/pl/ | grep -iF 'My hostname is web-l' > /dev/null
	curl -sSL 127.0.0.1:8005/p3l | grep -iF '503 Service Unavailable' > /dev/null
	curl --retry 10 --retry-delay 5 -sSfL 127.0.0.1:8005/p3l/ | grep -iF 'My hostname is web-l' > /dev/null
	curl --retry 10 --retry-delay 5 -sSfL "127.0.0.1:8005/pl/?u=user&p=pass" | grep -iF 'My hostname is web-l' > /dev/null
	curl --retry 10 --retry-delay 5 -sSfL "127.0.0.1:8005/p3l/?u=user&p=pass" | grep -iF 'My hostname is web-l' > /dev/null

	curl --retry 10 --retry-delay 5 -sSfL 127.0.0.1:8005/abc.js | grep -iF 'My hostname is web-m' > /dev/null
	curl --retry 10 --retry-delay 5 -sSfL 127.0.0.1:8005/path/123.js | grep -iF 'My hostname is web-m' > /dev/null
	curl --retry 10 --retry-delay 5 -sSfL "127.0.0.1:8005/abc.js?u=user&p=pass" | grep -iF 'My hostname is web-m' > /dev/null
	curl --retry 10 --retry-delay 5 -sSfL "127.0.0.1:8005/path/123.js?u=user&p=pass" | grep -iF 'My hostname is web-m' > /dev/null
	curl -sSL 127.0.0.1:8005/abc.jpg | grep -iF '503 Service Unavailable' > /dev/null
	curl -sSL 127.0.0.1:8005/path/abc.jpg | grep -iF '503 Service Unavailable' > /dev/null
	@echo

	@echo "==> Testing virtual host combined with virtual path"
	docker run -d --name web-n -e HOSTNAME=web-n -e VIRTUAL_HOST="http://www.web-n.org/p3/" tutum/hello-world
	docker run -d --name lb6 --link web-n:web-n -p 8006:80 tifayuki/haproxy-test
	wget --spider --retry-connrefused --no-check-certificate -q -T 5 127.0.0.1:8006 || true > /dev/null
	curl --retry 10 --retry-delay 5 -H "Host:www.web-n.org" -sSfL 127.0.0.1:8006/p3/ | grep -iF 'My hostname is web-n' > /dev/null
	curl -sSL 127.0.0.1:8006/p3/ | grep -iF '503 Service Unavailable' > /dev/null
	curl -sSL -H "Host:www.web-n.org" 127.0.0.1:8006 | grep -iF '503 Service Unavailable' > /dev/null
	curl -sSL -H "Host:www.web-n.org" 127.0.0.1:8006/p3 | grep -iF '503 Service Unavailable' > /dev/null
	curl -sSL -H "Host:www.web.org" 127.0.0.1:8006/p3 | grep -iF '503 Service Unavailable' > /dev/null
	@echo

	@echo "==> Testing multi ssl certificates"
	docker run -d --name web-o -e HOSTNAME="web-o" -e VIRTUAL_HOST="https://web-o.org" -e SSL_CERT="$(cert1)" tutum/hello-world
	docker run -d --name web-p -e HOSTNAME="web-p" -e VIRTUAL_HOST="https://web-p.org" -e SSL_CERT="$(cert2)" tutum/hello-world
	docker run -d --name lb7  --link web-o:web-o --link web-p:web-p -p 8007:443 tifayuki/haproxy-test
	sleep 5
	curl --retry 10 --retry-delay 5 -sSfL --cacert ca1.pem -L --resolve web-o.org:8007:127.0.0.1 https://web-o.org:8007 | grep -iF 'My hostname is web-o' > /dev/null
	curl --cacert ca2.pem -L --resolve web-o.org:8007:127.0.0.1 https://web-o.org:8007 2>&1 | grep -iF "SSL certificate problem: self signed certificate" > /dev/null
	curl --retry 10 --retry-delay 5 -sSfL --cacert ca2.pem -L --resolve web-p.org:8007:127.0.0.1 https://web-p.org:8007| grep -iF 'My hostname is web-p' > /dev/null
	curl --cacert ca1.pem -L --resolve web-p.org:8007:127.0.0.1 https://web-p.org:8007 2>&1 | grep -iF "SSL certificate problem: self signed certificate" > /dev/null
	@echo

	@echo "==> Testing multi frontends"
	docker run -d --name web-q -e HOSTNAME="web-q" -e VIRTUAL_HOST="https://web-o.org:444, webq2.org:8008" -e SSL_CERT="$(cert1)" tutum/hello-world
	docker run -d --name web-r -e HOSTNAME="web-r" -e VIRTUAL_HOST="https://web-p.org, http://webr2.org" -e SSL_CERT="$(cert2)" tutum/hello-world
	docker run -d --name web-s -e HOSTNAME="web-s" -e VIRTUAL_HOST="webs.org, http://webs1.org:8009, webs2.org/path/, */*.do/, *:8011/*.php/" tutum/hello-world
	docker run -d --name lb8  --link web-q:web-q --link web-r:web-r --link web-s:web-s -p 443:443 -p 444:444 -p 8008:8008 -p 8009:8009 -p 80:80 -p 8011:8011 tifayuki/haproxy-test
	sleep 5
	curl --retry 10 --retry-delay 5 -sSfL --cacert ca1.pem -L --resolve web-o.org:444:127.0.0.1 https://web-o.org:444 | grep -iF 'My hostname is web-q' > /dev/null
	curl --retry 10 --retry-delay 5 -sSfL -H "HOST:webq2.org" 127.0.0.1:8008 | grep -iF 'My hostname is web-q' > /dev/null
	curl --retry 10 --retry-delay 5 -sSfL --cacert ca2.pem -L --resolve web-p.org:443:127.0.0.1 https://web-p.org | grep -iF 'My hostname is web-r' > /dev/null
	curl --retry 10 --retry-delay 5 -sSfL -H "HOST:webr2.org" 127.0.0.1 | grep -iF 'My hostname is web-r' > /dev/null
	curl --retry 10 --retry-delay 5 -sSfL -H "HOST:webs.org" 127.0.0.1 | grep -iF 'My hostname is web-s' > /dev/null
	curl --retry 10 --retry-delay 5 -sSfL -H "HOST:webs1.org" 127.0.0.1:8009 | grep -iF 'My hostname is web-s' > /dev/null
	curl --retry 10 --retry-delay 5 -sSfL -H "HOST:webs2.org" 127.0.0.1/path/ | grep -iF 'My hostname is web-s' > /dev/null
	curl --retry 10 --retry-delay 5 -sSfL 127.0.0.1/abc.do/ | grep -iF 'My hostname is web-s' > /dev/null
	curl --retry 10 --retry-delay 5 -sSfL 127.0.0.1:8011/abc.php/ | grep -iF 'My hostname is web-s' > /dev/null
	@echo

	echo "==> Testing force_ssl with virtual host"
	docker rm -f lb8 || true
	docker run -d --name web-t -e HOSTNAME="web-t" -e VIRTUAL_HOST="https://web-o.org, web-o.org" -e SSL_CERT="$(cert1)" tutum/hello-world
	docker run -d --name web-u -e HOSTNAME="web-u" -e VIRTUAL_HOST="https://web-p.org, web-p.org" -e SSL_CERT="$(cert2)" -e FORCE_SSL=true tutum/hello-world
	docker run -d --name lb8  --link web-t:web-t --link web-u:web-u -p 443:443 -p 80:80 haproxy
	sleep 5
	curl --cacert ca1.pem -sS https://web-o.org --resolve web-o.org:443:127.0.0.1 | grep -iF 'My hostname is web-t' > /dev/null
	curl --cacert ca2.pem -sS https://web-p.org --resolve web-p.org:443:127.0.0.1 | grep -iF 'My hostname is web-u' > /dev/null
	curl --cacert ca1.pem -sSL http://web-o.org --resolve web-o.org:443:127.0.0.1 --resolve web-o.org:80:127.0.0.1 | grep -iF 'My hostname is web-t' > /dev/null
	curl --cacert ca2.pem -sSL http://web-p.org --resolve web-p.org:443:127.0.0.1 --resolve web-p.org:80:127.0.0.1 | grep -iF 'My hostname is web-u' > /dev/null
	curl --cacert ca1.pem -sSIL http://web-o.org --resolve web-o.org:443:127.0.0.1 --resolve web-o.org:80:127.0.0.1 | grep -iF "http/1.1" | grep -v "301"
	curl --cacert ca2.pem -sSIL http://web-p.org --resolve web-p.org:443:127.0.0.1 --resolve web-p.org:80:127.0.0.1 | grep -iF '301 Moved Permanently' > /dev/null
	@echo

	echo "==> Testing force_ssl without virtual host"
	docker rm -f lb8 || true
	docker run -d --name web-v -e HOSTNAME="web-wv" -e SSL_CERT="$(cert0)" tutum/hello-world
	docker run -d --name web-w -e HOSTNAME="web-wv" -e FORCE_SSL=true tutum/hello-world
	docker run -d --name lb9  --link web-v:web-v --link web-w:web-w -p 443:443 -p 80:80 haproxy
	sleep 5
	curl --cacert ca0.pem -sS https://localhost | grep -iF 'My hostname is web-wv' > /dev/null
	curl --cacert ca0.pem -sSL http://localhost | grep -iF 'My hostname is web-wv' > /dev/null
	curl --cacert ca0.pem -sSIL http://localhost | grep -iF '301 Moved Permanently' > /dev/null
	@echo

	@echo "==> functionality integration tests passed!"
	@echo
push-image: build
	@echo "=> Pushing the image to tifayuki/haproxy"
	@echo "=> Logging in to docker"
	@docker login -u $(DOCKER_USER) -p $(DOCKER_PASS) -e a@a.com
	docker push tifayuki/haproxy-test
	@echo

clean-tutum-service:
	@echo "==> Terminating containers in Tutum"
	tutum service terminate $(services) || true
	@echo

linktest:push-image clean-tutum-service
	@set -e
	@echo "====== Running dynamic link integration tests with Tutum ======"

	@echo "==> Testing if haproxy is running properly with Tutum"
	tutum service run --sync --name $(random)web-a -e HOSTNAME="web-a" tutum/hello-world
	tutum service run --sync --name $(random)web-b -e HOSTNAME="web-b" tutum/hello-world
	tutum service run --role global --sync --name $(random)lb1 --link $(random)web-a:web-a --link $(random)web-b:web-b -p 8000:80 tifayuki/haproxy-test
	wget --spider --retry-connrefused --no-check-certificate -q -T 5 $(NODE_FQDN):8000 || true
	curl --retry 10 --retry-delay 5 -sSfL 127.0.0.1:8000/ | grep -iF 'My hostname is web-a' > /dev/null
	curl --retry 10 --retry-delay 5 -sSfL -I $(NODE_FQDN):8000 | grep "200 OK"
	@echo

	@echo "==> Testing container run"
	tutum service run -t 2 --sync --name $(random)web-c -e VIRTUAL_HOST=web-c.org tutum/hello-world
	tutum service run -t 2 --sync --name $(random)web-d -e VIRTUAL_HOST=web-d.org tutum/hello-world
	tutum service run --role global --name $(random)lb2 --link $(random)web-c:$(random)web-c --link $(random)web-d:$(random)web-d -p 8001:80 -e DEBUG=true tifayuki/haproxy-test
	wget --spider --retry-connrefused --no-check-certificate -q -T 5 $(NODE_FQDN):8001 || true
	rm -f output
	curl --retry 10 --retry-delay 5 -sSfL -H 'Host:web-c.org' $(NODE_FQDN):8001 >> output
	curl --retry 10 --retry-delay 5 -sSfL -H 'Host:web-c.org' $(NODE_FQDN):8001 >> output
	curl --retry 10 --retry-delay 5 -sSfL -H 'Host:web-d.org' $(NODE_FQDN):8001 >> output
	curl --retry 10 --retry-delay 5 -sSfL -H 'Host:web-d.org' $(NODE_FQDN):8001 >> output
	grep 'My hostname is $(random)web-c-1' output | wc -l | grep 1
	grep 'My hostname is $(random)web-d-1' output | wc -l | grep 1
	grep 'My hostname is $(random)web-c-2' output | wc -l | grep 1
	grep 'My hostname is $(random)web-d-2' output | wc -l | grep 1
	@echo

	@echo "==> Testing container stop"
	tutum container stop --sync $(random)web-c-1
	tutum container stop --sync $(random)web-d-1
	rm -f output
	sleep 5
	curl --retry 10 --retry-delay 5 -sSfL -H 'Host:web-c.org' $(NODE_FQDN):8001 >> output
	curl --retry 10 --retry-delay 5 -sSfL -H 'Host:web-c.org' $(NODE_FQDN):8001 >> output
	curl --retry 10 --retry-delay 5 -sSfL -H 'Host:web-d.org' $(NODE_FQDN):8001 >> output
	curl --retry 10 --retry-delay 5 -sSfL -H 'Host:web-d.org' $(NODE_FQDN):8001 >> output
	grep 'My hostname is $(random)web-c-2' output | wc -l | grep 2
	grep 'My hostname is $(random)web-d-2' output | wc -l | grep 2
	@echo

	@echo "==> Testing container start"
	tutum container start --sync $(random)web-c-1
	tutum container start --sync $(random)web-d-1
	rm -f output
	sleep 5
	curl --retry 10 --retry-delay 5 -sSfL -H 'Host:web-c.org' $(NODE_FQDN):8001 >> output
	curl --retry 10 --retry-delay 5 -sSfL -H 'Host:web-c.org' $(NODE_FQDN):8001 >> output
	curl --retry 10 --retry-delay 5 -sSfL -H 'Host:web-d.org' $(NODE_FQDN):8001 >> output
	curl --retry 10 --retry-delay 5 -sSfL -H 'Host:web-d.org' $(NODE_FQDN):8001 >> output
	grep 'My hostname is $(random)web-c-1' output | wc -l | grep 1
	grep 'My hostname is $(random)web-d-1' output | wc -l | grep 1
	grep 'My hostname is $(random)web-c-2' output | wc -l | grep 1
	grep 'My hostname is $(random)web-d-2' output | wc -l | grep 1
	@echo

	@echo "==> Testing container terminate"
	tutum container terminate --sync $(random)web-c-2
	tutum container terminate --sync $(random)web-d-2
	rm -f output
	sleep 5
	curl --retry 10 --retry-delay 5 -sSfL -H 'Host:web-c.org' $(NODE_FQDN):8001 >> output
	curl --retry 10 --retry-delay 5 -sSfL -H 'Host:web-c.org' $(NODE_FQDN):8001 >> output
	curl --retry 10 --retry-delay 5 -sSfL -H 'Host:web-d.org' $(NODE_FQDN):8001 >> output
	curl --retry 10 --retry-delay 5 -sSfL -H 'Host:web-d.org' $(NODE_FQDN):8001 >> output
	grep 'My hostname is $(random)web-c-1' output | wc -l | grep 2
	grep 'My hostname is $(random)web-d-1' output | wc -l | grep 2
	@echo

	@echo "==> Testing container redeploy"
	tutum container redeploy --sync $(random)web-c-1
	tutum container redeploy --sync $(random)web-d-1
	rm -f output
	sleep 5
	curl --retry 10 --retry-delay 5 -sSfL -H 'Host:web-c.org' $(NODE_FQDN):8001 >> output
	curl --retry 10 --retry-delay 5 -sSfL -H 'Host:web-c.org' $(NODE_FQDN):8001 >> output
	curl --retry 10 --retry-delay 5 -sSfL -H 'Host:web-d.org' $(NODE_FQDN):8001 >> output
	curl --retry 10 --retry-delay 5 -sSfL -H 'Host:web-d.org' $(NODE_FQDN):8001 >> output
	grep 'My hostname is $(random)web-c-1' output | wc -l | grep 2
	grep 'My hostname is $(random)web-d-1' output | wc -l | grep 2
	@echo

	@echo "==> Testing with service scale up"
	tutum service scale --sync $(random)web-c 2
	tutum service scale --sync $(random)web-d 2
	rm -f output
	sleep 5
	curl --retry 10 --retry-delay 5 -sSfL -H 'Host:web-c.org' $(NODE_FQDN):8001 >> output
	curl --retry 10 --retry-delay 5 -sSfL -H 'Host:web-c.org' $(NODE_FQDN):8001 >> output
	curl --retry 10 --retry-delay 5 -sSfL -H 'Host:web-d.org' $(NODE_FQDN):8001 >> output
	curl --retry 10 --retry-delay 5 -sSfL -H 'Host:web-d.org' $(NODE_FQDN):8001 >> output
	grep 'My hostname is $(random)web-c-1' output | wc -l | grep 1
	grep 'My hostname is $(random)web-d-1' output | wc -l | grep 1
	grep 'My hostname is $(random)web-c-2' output | wc -l | grep 1
	grep 'My hostname is $(random)web-d-2' output | wc -l | grep 1
	@echo

	@echo "==> Testing with service scale down"
	tutum service scale --sync $(random)web-c 1
	tutum service scale --sync $(random)web-d 1
	rm -f output
	sleep 5
	curl --retry 10 --retry-delay 5 -sSfL -H 'Host:web-c.org' $(NODE_FQDN):8001 >> output
	curl --retry 10 --retry-delay 5 -sSfL -H 'Host:web-c.org' $(NODE_FQDN):8001 >> output
	curl --retry 10 --retry-delay 5 -sSfL -H 'Host:web-d.org' $(NODE_FQDN):8001 >> output
	curl --retry 10 --retry-delay 5 -sSfL -H 'Host:web-d.org' $(NODE_FQDN):8001 >> output
	grep 'My hostname is $(random)web-c-1' output | wc -l | grep 2
	grep 'My hostname is $(random)web-d-1' output | wc -l | grep 2
	@echo

	@echo "==> Testing with service stop"
	tutum service stop --sync $(random)web-d
	rm -f output
	sleep 5
	curl --retry 10 --retry-delay 5 -sSfL -H 'Host:web-c.org' $(NODE_FQDN):8001 >> output
	curl --retry 10 --retry-delay 5 -sSfL -H 'Host:web-c.org' $(NODE_FQDN):8001 >> output
	curl -sL -H 'Host:web-d.org' $(NODE_FQDN):8001 >> output
	curl -sL -H 'Host:web-d.org' $(NODE_FQDN):8001 >> output
	grep 'My hostname is $(random)web-c-1' output | wc -l | grep 2
	grep '503 Service Unavailable' output | wc -l | grep 2
	@echo

	@echo "==> Testing with service start"
	tutum service start --sync $(random)web-d
	rm -f output
	sleep 5
	curl --retry 10 --retry-delay 5 -sSfL -H 'Host:web-c.org' $(NODE_FQDN):8001 >> output
	curl --retry 10 --retry-delay 5 -sSfL -H 'Host:web-c.org' $(NODE_FQDN):8001 >> output
	curl --retry 10 --retry-delay 5 -sSfL -H 'Host:web-d.org' $(NODE_FQDN):8001 >> output
	curl --retry 10 --retry-delay 5 -sSfL -H 'Host:web-d.org' $(NODE_FQDN):8001 >> output
	grep 'My hostname is $(random)web-c-1' output | wc -l | grep 2
	grep 'My hostname is $(random)web-d-1' output | wc -l | grep 2
	@echo

	@echo "==> Testing with service terminate"
	tutum service terminate --sync $(random)web-d
	rm -f output
	sleep 5
	curl --retry 10 --retry-delay 5 -sSfL -H 'Host:web-c.org' $(NODE_FQDN):8001 >> output
	curl --retry 10 --retry-delay 5 -sSfL -H 'Host:web-c.org' $(NODE_FQDN):8001 >> output
	curl -sL -H 'Host:web-d.org' $(NODE_FQDN):8001 >> output
	curl -sL -H 'Host:web-d.org' $(NODE_FQDN):8001 >> output
	grep 'My hostname is $(random)web-c-1' output | wc -l | grep 2
	grep '503 Service Unavailable' output | wc -l | grep 2
	@echo

	@echo "==> Testing with service redeploy"
	tutum service redeploy --sync $(random)web-c
	rm -f output
	sleep 5
	curl --retry 10 --retry-delay 5 -sSfL -H 'Host:web-c.org' $(NODE_FQDN):8001 >> output
	curl --retry 10 --retry-delay 5 -sSfL -H 'Host:web-c.org' $(NODE_FQDN):8001 >> output
	curl -sL -H 'Host:web-d.org' $(NODE_FQDN):8001 >> output
	curl -sL -H 'Host:web-d.org' $(NODE_FQDN):8001 >> output
	grep 'My hostname is $(random)web-c-1' output | wc -l | grep 2
	grep '503 Service Unavailable' output | wc -l | grep 2
	@echo

	@echo "==> Testing with new links added"
	tutum service run -t 2 --sync --name $(random)web-e -e VIRTUAL_HOST=web-e.org tutum/hello-world
	tutum service set --link $(random)web-c:web-c --link $(random)web-e:web-e $(random)lb2
	rm -f output
	sleep 5
	curl --retry 10 --retry-delay 5 -sSfL -H 'Host:web-c.org' $(NODE_FQDN):8001 >> output
	curl --retry 10 --retry-delay 5 -sSfL -H 'Host:web-c.org' $(NODE_FQDN):8001 >> output
	curl -sL -H 'Host:web-d.org' $(NODE_FQDN):8001 >> output
	curl -sL -H 'Host:web-d.org' $(NODE_FQDN):8001 >> output
	curl --retry 10 --retry-delay 5 -sSfL -H 'Host:web-e.org' $(NODE_FQDN):8001 >> output
	curl --retry 10 --retry-delay 5 -sSfL -H 'Host:web-e.org' $(NODE_FQDN):8001 >> output
	grep 'My hostname is $(random)web-c-1' output | wc -l | grep 2
	grep '503 Service Unavailable' output | wc -l | grep 2
	grep 'My hostname is $(random)web-e-1' output | wc -l | grep 1
	grep 'My hostname is $(random)web-e-2' output | wc -l | grep 1
	@echo

	@echo "==> Testing with links removed"
	tutum service set --link $(random)web-e:web-e $(random)lb2
	rm -f output
	sleep 5
	curl -sL -H 'Host:web-c.org' $(NODE_FQDN):8001 >> output
	curl -sL -H 'Host:web-c.org' $(NODE_FQDN):8001 >> output
	curl --retry 10 --retry-delay 5 -sSfL -H 'Host:web-e.org' $(NODE_FQDN):8001 >> output
	curl --retry 10 --retry-delay 5 -sSfL -H 'Host:web-e.org' $(NODE_FQDN):8001 >> output
	grep 'My hostname is $(random)web-e-1' output | wc -l | grep 1
	grep 'My hostname is $(random)web-e-1' output | wc -l | grep 1
	grep '503 Service Unavailable' output | wc -l | grep 2
	@echo

	@echo "==> Testing with application service redeployed"
	tutum service set -e VIRTUAL_HOST="web-f.org" $(random)web-e
	tutum service redeploy --sync $(random)web-e
	rm -f output
	sleep 5
	curl -sL -H 'Host:web-e.org' $(NODE_FQDN):8001 >> output
	curl -sL -H 'Host:web-e.org' $(NODE_FQDN):8001 >> output
	curl --retry 10 --retry-delay 5 -sSfL -H 'Host:web-f.org' $(NODE_FQDN):8001 >> output
	curl --retry 10 --retry-delay 5 -sSfL -H 'Host:web-f.org' $(NODE_FQDN):8001 >> output
	grep 'My hostname is $(random)web-e-1' output | wc -l | grep 1
	grep 'My hostname is $(random)web-e-2' output | wc -l | grep 1
	grep '503 Service Unavailable' output | wc -l | grep 2
	@echo

	@echo "==> Dynamic link integration tests passed!"
	@echo

unittest:build
	@echo "====== Running unit test ======"
	@echo