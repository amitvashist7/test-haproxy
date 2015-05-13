WEB_CONTAINERS = web-a web-b web-c web-d web-e
LB_CONTAINERS = lb1 lb2 lb3 lb4 lb5 lb6 lb7
NODE_FQDN = http://302a494c-tifayuki.node.tutum.io
services = $(shell tutum service ps -q)
random := $(shell awk 'BEGIN{srand();printf("%d", 65536*rand())}')

test:test-unittest test-without-tutum test-with-tutum ;

test-docker-available:
	@set -e
	@echo "==> Testing docker environment"
	docker version || (echo "==> Failed: cannot run docker" && false)
	@echo

clean:test-docker-available
	@set -e
	@echo "==> Cleaning tmp files and containers"
	docker rm -f $(WEB_CONTAINERS) $(LB_CONTAINERS) > /dev/null 2>&1 || true
	rm -f key.pem ca.pem cert.pem output
	@echo

create-cert:clean
	@set -e
	@echo "==> Generating certificate for tests"
	openssl req -x509 -newkey rsa:2048 -keyout key.pem -out ca.pem -days 1080 -nodes -subj '/CN=localhost/O=My Company Name LTD./C=US'
	cp key.pem cert.pem
	cat ca.pem >> cert.pem
	@echo

build:create-cert
	@set -e
	@echo "==> Building haproxy image"
	docker build -t tifayuki/haproxy-test .
	@echo

certs = $(shell awk 1 ORS='\\n' cert.pem)
test-without-tutum:build
	@set -e
	@echo "====== Running integration tests with Tutum ======"

	@echo "==> Testing if haproxy is running properly"
	docker run -d --name web-a -e HOSTNAME="web-a" tutum/hello-world
	docker run -d --name web-b -e HOSTNAME="web-b" tutum/hello-world
	docker run -d --name lb1 --link web-a:web-a --link web-b:web-b -p 8000:80 tifayuki/haproxy-test
	wget --spider --retry-connrefused --no-check-certificate -T 5 http://localhost:8000
	curl --retry 10 --retry-delay 5 -L -I http://localhost:8000 | grep "200 OK"
	@echo

	@echo "==> Testing virtual host: specified in haproxy cotnainer"
	docker run -d --name lb2 --link web-a:web-a --link web-b:web-b -e VIRTUAL_HOST=" web-a = www.web-a.org, www.test.org, web-b = www.web-b.org " -p 8001:80 tifayuki/haproxy-test
	wget --spider --retry-connrefused --no-check-certificate -q -T 5 127.0.0.1:8001 || true
	curl --retry 10 --retry-delay 5 -H 'Host:www.web-a.org' 127.0.0.1:8001 | grep 'My hostname is web-a'
	curl --retry 10 --retry-delay 5 -H 'Host:www.test.org' 127.0.0.1:8001 | grep 'My hostname is web-a'
	curl --retry 10 --retry-delay 5 -H 'Host:www.web-b.org' 127.0.0.1:8001 | grep 'My hostname is web-b'
	@echo

	@echo "==> Testing virtual host: specified in linked containers"
	docker run -d --name web-c -e HOSTNAME=web-c -e VIRTUAL_HOST=web-c.org tutum/hello-world
	docker run -d --name web-d -e HOSTNAME=web-d -e VIRTUAL_HOST="web-d.org, test.org" tutum/hello-world
	docker run -d --name lb3 --link web-c:web-c --link web-d:web-d -p 8002:80 tifayuki/haproxy-test
	wget --spider --retry-connrefused --no-check-certificate -q -T 5 127.0.0.1:8002 || true
	curl --retry 10 --retry-delay 5 -sSfL -H 'Host:web-c.org' 127.0.0.1:8002 | grep 'My hostname is web-c'
	curl --retry 10 --retry-delay 5 -sSfL -H 'Host:test.org' 127.0.0.1:8002 | grep 'My hostname is web-d'
	curl --retry 10 --retry-delay 5 -sSfL -H 'Host:web-d.org' 127.0.0.1:8002 | grep 'My hostname is web-d'
	@echo

	@echo "==> Testing SSL settings"
	docker run -d --name lb4 --link web-a:web-a -e SSL_CERT="$(certs)" -p 443:443 tifayuki/haproxy-test
	sleep 5
	curl --retry 10 --retry-delay 5 -sSfL --cacert ca.pem -L https://localhost | grep 'My hostname is web-a'
	@echo

	@echo "==> Testing wildcard sub-domains on virtual host (HDR=hdr_end/hdr_beg)"
	docker run -d --name lb5 --link web-c:web-c -e HDR="hdr_end" -p 8003:80 tifayuki/haproxy-test
	wget --spider --retry-connrefused --no-check-certificate -q -T 5 127.0.0.1:8003 || true
	curl --retry 10 --retry-delay 5 -sSfL -H 'Host:www.web-c.org' 127.0.0.1:8003 | grep 'My hostname is web-c'
	docker run -d --name lb6 --link web-c:web-c -e HDR=hdr_beg -e FRONTEND_PORT=8005 -p 8005:8005 tifayuki/haproxy-test
	wget --spider --retry-connrefused --no-check-certificate -q -T 5 127.0.0.1:8005 || true
	curl --retry 10 --retry-delay 5 -sSfL -H 'Host:web-c.org:8005' 127.0.0.1:8005 | grep 'My hostname is web-c'
	@echo

	@echo "==> Testing VIRTUAL_HOST with non-default FRONTEND_PORT"
	docker run -d --name web-e -e HOSTNAME=web-e -e VIRTUAL_HOST="web-e.org:8004" tutum/hello-world
	docker run -d --name lb7 --link web-e:web-e -e FRONTEND_PORT=8004 -p 8004:8004 tifayuki/haproxy-test
	wget --spider --retry-connrefused --no-check-certificate -q -T 5 127.0.0.1:8004 || true
	curl --retry 10 --retry-delay 5 -sSfL -H 'Host:web-e.org:8004' 127.0.0.1:8004 | grep 'My hostname is web-e'

push-image: build
	@echo "=> Pushing the image to tifayuki/haproxy"
	@echo "=> Logging in to docker"
	@docker login -u $(DOCKER_USER) -p $(DOCKER_PASS) -e a@a.com
	docker push tifayuki/haproxy-test
	@echo

clean-tutum-service:
	@echo "==> Terminating containers in Tuttum"
	tutum service terminate $(services) || true
	@echo

test-with-tutum:push-image clean-tutum-service
	@set -e
	@echo "====== Running integration tests with Tutum ======"

	@echo "==> Testing if haproxy is running properly with tutum"
	tutum service run --sync --name $(random)web-a -e HOSTNAME="web-a" tutum/hello-world
	tutum service run --sync --name $(random)web-b -e HOSTNAME="web-b" tutum/hello-world
	tutum service run --sync --name $(random)lb1 --link $(random)web-a:web-a --link $(random)web-b:web-b -p 8000:80 tifayuki/haproxy-test
	wget --spider --retry-connrefused --no-check-certificate -q -T 5 $(NODE_FQDN):8000 || true
	curl --retry 10 --retry-delay 5 -sSfL -I $(NODE_FQDN):8000 | grep "200 OK"
	@echo

	@echo "==> Testing virtual host: specified in haproxy cotnainer with tutum"
	tutum service run --role global --sync --name $(random)lb2 --link $(random)web-a:web-a --link $(random)web-b:web-b -e VIRTUAL_HOST=" web-a = www.web-a.org, www.test.org, web-b = www.web-b.org " -p 8001:80 tifayuki/haproxy-test
	wget --spider --retry-connrefused --no-check-certificate -q -T 5 $(NODE_FQDN):8001 || true
	curl --retry 10 --retry-delay 5 -sSfL -H 'Host:www.web-a.org' $(NODE_FQDN):8001 | grep 'My hostname is web-a'
	curl --retry 10 --retry-delay 5 -sSfL -H 'Host:www.test.org' $(NODE_FQDN):8001 | grep 'My hostname is web-a'
	curl --retry 10 --retry-delay 5 -sSfL -H 'Host:www.web-b.org' $(NODE_FQDN):8001 | grep 'My hostname is web-b'
	@echo

	@echo "==> Testing virtual host: specified in linked containers with tutum"
	tutum service run --sync --name $(random)web-c -e HOSTNAME=web-c -e VIRTUAL_HOST=web-c.org tutum/hello-world
	tutum service run --sync --name $(random)web-d -e HOSTNAME=web-d -e VIRTUAL_HOST="web-d.org, test.org" tutum/hello-world
	tutum service run --role global --sync --name $(random)lb3 --link $(random)web-c:web-c --link $(random)web-d:web-d -p 8002:80 tifayuki/haproxy-test
	wget --spider --retry-connrefused --no-check-certificate -q -T 5 $(NODE_FQDN):8002 || true
	curl --retry 10 --retry-delay 5 -sSfL -H 'Host:web-c.org' $(NODE_FQDN):8002| grep 'My hostname is web-c'
	curl --retry 10 --retry-delay 5 -sSfL -H 'Host:test.org' $(NODE_FQDN):8002 | grep 'My hostname is web-d'
	curl --retry 10 --retry-delay 5 -sSfL -H 'Host:web-d.org' $(NODE_FQDN):8002 | grep 'My hostname is web-d'
	@echo

	@echo "==> Testing wildcard sub-domains on virtual host (HDR=hdr_end)"
	tutum service run --role global --name $(random)lb4 --link $(random)web-c:web-c -e HDR="hdr_end" -p 8003:80 tifayuki/haproxy-test
	wget --spider --retry-connrefused --no-check-certificate -q -T 5 $(NODE_FQDN):8003 || true
	curl --retry 10 --retry-delay 5 -sSfL -H 'Host:www.web-c.org' $(NODE_FQDN):8003 | grep 'My hostname is web-c'
	@echo

	@echo "==> Testing container stop"
	tutum service run -t 2 --sync --name $(random)web-f -e VIRTUAL_HOST=web-f.org tutum/hello-world
	tutum service run -t 2 --sync --name $(random)web-g -e VIRTUAL_HOST=web-g.org tutum/hello-world
	tutum service run --role global --name $(random)lb5 --link $(random)web-f:$(random)web-f --link $(random)web-g:$(random)web-g -p 8004:80 tifayuki/haproxy-test
	wget --spider --retry-connrefused --no-check-certificate -q -T 5 $(NODE_FQDN):8004 || true
	tutum container stop --sync $(random)web-f-1
	tutum container stop --sync $(random)web-g-1
	rm -f output
	sleep 5
	curl --retry 10 --retry-delay 5 -sSfL -H 'Host:web-f.org' $(NODE_FQDN):8004 >> output
	curl --retry 10 --retry-delay 5 -sSfL -H 'Host:web-f.org' $(NODE_FQDN):8004 >> output
	curl --retry 10 --retry-delay 5 -sSfL -H 'Host:web-g.org' $(NODE_FQDN):8004 >> output
	curl --retry 10 --retry-delay 5 -sSfL -H 'Host:web-g.org' $(NODE_FQDN):8004 >> output
	grep 'My hostname is $(random)web-f-2' output | wc -l | grep 2
	grep 'My hostname is $(random)web-g-2' output | wc -l | grep 2
	@echo

	@echo "==> Testing container start"
	tutum container start --sync $(random)web-f-1
	tutum container start --sync $(random)web-g-1
	rm -f output
	sleep 5
	curl --retry 10 --retry-delay 5 -sSfL -H 'Host:web-f.org' $(NODE_FQDN):8004 >> output
	curl --retry 10 --retry-delay 5 -sSfL -H 'Host:web-f.org' $(NODE_FQDN):8004 >> output
	curl --retry 10 --retry-delay 5 -sSfL -H 'Host:web-g.org' $(NODE_FQDN):8004 >> output
	curl --retry 10 --retry-delay 5 -sSfL -H 'Host:web-g.org' $(NODE_FQDN):8004 >> output
	grep 'My hostname is $(random)web-f-1' output | wc -l | grep 1
	grep 'My hostname is $(random)web-f-2' output | wc -l | grep 1
	grep 'My hostname is $(random)web-g-1' output | wc -l | grep 1
	grep 'My hostname is $(random)web-g-2' output | wc -l | grep 1
	@echo

	@echo "==> Testing container terminate"
	tutum container terminate --sync $(random)web-f-2
	tutum container terminate --sync $(random)web-g-2
	rm -f output
	sleep 5
	curl --retry 10 --retry-delay 5 -sSfL -H 'Host:web-f.org' $(NODE_FQDN):8004 >> output
	curl --retry 10 --retry-delay 5 -sSfL -H 'Host:web-f.org' $(NODE_FQDN):8004 >> output
	curl --retry 10 --retry-delay 5 -sSfL -H 'Host:web-g.org' $(NODE_FQDN):8004 >> output
	curl --retry 10 --retry-delay 5 -sSfL -H 'Host:web-g.org' $(NODE_FQDN):8004 >> output
	grep 'My hostname is $(random)web-f-1' output | wc -l | grep 2
	grep 'My hostname is $(random)web-g-1' output | wc -l | grep 2
	@echo

	@echo "==> Testing container redeploy"
	tutum container redeploy --sync $(random)web-f-1
	tutum container redeploy --sync $(random)web-g-1
	rm -f output
	sleep 5
	curl --retry 10 --retry-delay 5 -sSfL -H 'Host:web-f.org' $(NODE_FQDN):8004 >> output
	curl --retry 10 --retry-delay 5 -sSfL -H 'Host:web-f.org' $(NODE_FQDN):8004 >> output
	curl --retry 10 --retry-delay 5 -sSfL -H 'Host:web-g.org' $(NODE_FQDN):8004 >> output
	curl --retry 10 --retry-delay 5 -sSfL -H 'Host:web-g.org' $(NODE_FQDN):8004 >> output
	grep 'My hostname is $(random)web-f-1' output | wc -l | grep 2
	grep 'My hostname is $(random)web-g-1' output | wc -l | grep 2
	@echo

	@echo "==> Testing with service scale up"
	tutum service scale --sync $(random)web-f 2
	tutum service scale --sync $(random)web-g 2
	rm -f output
	sleep 5
	curl --retry 10 --retry-delay 5 -sSfL -H 'Host:web-f.org' $(NODE_FQDN):8004 >> output
	curl --retry 10 --retry-delay 5 -sSfL -H 'Host:web-f.org' $(NODE_FQDN):8004 >> output
	curl --retry 10 --retry-delay 5 -sSfL -H 'Host:web-g.org' $(NODE_FQDN):8004 >> output
	curl --retry 10 --retry-delay 5 -sSfL -H 'Host:web-g.org' $(NODE_FQDN):8004 >> output
	grep 'My hostname is $(random)web-f-1' output | wc -l | grep 1
	grep 'My hostname is $(random)web-f-2' output | wc -l | grep 1
	grep 'My hostname is $(random)web-g-1' output | wc -l | grep 1
	grep 'My hostname is $(random)web-g-2' output | wc -l | grep 1
	@echo

	@echo "==> Testing with service scale down"
	tutum service scale --sync $(random)web-f 1
	tutum service scale --sync $(random)web-g 1
	rm -f output
	sleep 5
	curl --retry 10 --retry-delay 5 -sSfL -H 'Host:web-f.org' $(NODE_FQDN):8004 >> output
	curl --retry 10 --retry-delay 5 -sSfL -H 'Host:web-f.org' $(NODE_FQDN):8004 >> output
	curl --retry 10 --retry-delay 5 -sSfL -H 'Host:web-g.org' $(NODE_FQDN):8004 >> output
	curl --retry 10 --retry-delay 5 -sSfL -H 'Host:web-g.org' $(NODE_FQDN):8004 >> output
	grep 'My hostname is $(random)web-f-1' output | wc -l | grep 2
	grep 'My hostname is $(random)web-g-1' output | wc -l | grep 2
	@echo

	@echo "==> Testing with service stop"
	tutum service stop --sync $(random)web-g
	rm -f output
	sleep 5
	curl --retry 10 --retry-delay 5 -sSfL -H 'Host:web-f.org' $(NODE_FQDN):8004 >> output
	curl --retry 10 --retry-delay 5 -sSfL -H 'Host:web-f.org' $(NODE_FQDN):8004 >> output
	curl -sL -H 'Host:web-g.org' $(NODE_FQDN):8004 >> output
	curl -sL -H 'Host:web-g.org' $(NODE_FQDN):8004 >> output
	grep 'My hostname is $(random)web-f-1' output | wc -l | grep 2
	grep '503 Service Unavailable' output | wc -l | grep 2
	@echo

	@echo "==> Testing with service start"
	tutum service start --sync $(random)web-g
	rm -f output
	sleep 5
	curl --retry 10 --retry-delay 5 -sSfL -H 'Host:web-f.org' $(NODE_FQDN):8004 >> output
	curl --retry 10 --retry-delay 5 -sSfL -H 'Host:web-f.org' $(NODE_FQDN):8004 >> output
	curl --retry 10 --retry-delay 5 -sSfL -H 'Host:web-g.org' $(NODE_FQDN):8004 >> output
	curl --retry 10 --retry-delay 5 -sSfL -H 'Host:web-g.org' $(NODE_FQDN):8004 >> output
	grep 'My hostname is $(random)web-f-1' output | wc -l | grep 2
	grep 'My hostname is $(random)web-g-1' output | wc -l | grep 2
	@echo

	@echo "==> Testing with service terminate"
	tutum service terminate --sync $(random)web-g
	rm -f output
	sleep 5
	curl --retry 10 --retry-delay 5 -sSfL -H 'Host:web-f.org' $(NODE_FQDN):8004 >> output
	curl --retry 10 --retry-delay 5 -sSfL -H 'Host:web-f.org' $(NODE_FQDN):8004 >> output
	curl -sL -H 'Host:web-g.org' $(NODE_FQDN):8004 >> output
	curl -sL -H 'Host:web-g.org' $(NODE_FQDN):8004 >> output
	grep 'My hostname is $(random)web-f-1' output | wc -l | grep 2
	grep '503 Service Unavailable' output | wc -l | grep 2
	@echo

	@echo "==> Testing with service redeploy"
	tutum service redeploy --sync $(random)web-f
	rm -f output
	sleep 5
	curl --retry 10 --retry-delay 5 -sSfL -H 'Host:web-f.org' $(NODE_FQDN):8004 >> output
	curl --retry 10 --retry-delay 5 -sSfL -H 'Host:web-f.org' $(NODE_FQDN):8004 >> output
	curl -sL -H 'Host:web-g.org' $(NODE_FQDN):8004 >> output
	curl -sL -H 'Host:web-g.org' $(NODE_FQDN):8004 >> output
	grep 'My hostname is $(random)web-f-1' output | wc -l | grep 2
	grep '503 Service Unavailable' output | wc -l | grep 2
	@echo

test-unittest:build
	@echo "====== Running unit test ======"
	@echo