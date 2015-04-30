WEB_CONTAINERS = web_a web_b web_c web_d
LB_CONTAINERS = lb1 lb2 lb3 lb4 lb5
SLEEP_TIME = 3

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
	rm -f key.pem ca.pem cert.pem
	@echo

create-cert:clean
	@echo "==> Generating certificate for tests"
	openssl req -x509 -newkey rsa:2048 -keyout key.pem -out ca.pem -days 1080 -nodes -subj '/CN=localhost/O=My Company Name LTD./C=US'
	cp key.pem cert.pem
	cat ca.pem >> cert.pem
	@echo

build:create-cert
	@set -e
	@echo "==> Building haproxy image"
	docker build -t lb .
	@echo

certs = $(shell awk 1 ORS='\\n' cert.pem)
test-without-tutum:build
	@set -e
	@echo "====== Running integration tests with Tutum ======"
	@echo "==> Running testing containers"
	docker run -d --name web_a -e HOSTNAME="web_a" tutum/hello-world
	docker run -d --name web_b -e HOSTNAME="web_b" tutum/hello-world
	docker run -d --name web_c -e HOSTNAME=web_c -e VIRTUAL_HOST=web_c.org tutum/hello-world
	docker run -d --name web_d -e HOSTNAME=web_d -e VIRTUAL_HOST="web_d.org, test.org" tutum/hello-world
	@echo

	@echo "==> Testing if haproxy is running properly"
	docker run -d --name lb1 --link web_a:web_a --link web_b:web_b -p 8000:80 lb
	sleep $(SLEEP_TIME)
	curl --retry 10 --retry-delay 5 -L -I http://localhost:8000 | grep "200 OK"
	@echo

	@echo "==> Testing virtual host - specified in haproxy cotnainer"
	docker run -d --name lb2 --link web_a:web_a --link web_b:web_b -e VIRTUAL_HOST=" web_a = www.web_a.org, www.test.org, web_b = www.web_b.org " -p 8001:80 lb
	sleep $(SLEEP_TIME)
	curl --retry 10 --retry-delay 5 -H 'Host:www.web_a.org' 127.0.0.1:8001 | grep 'My hostname is web_a'
	curl --retry 10 --retry-delay 5 -H 'Host:www.test.org' 127.0.0.1:8001 | grep 'My hostname is web_a'
	curl --retry 10 --retry-delay 5 -H 'Host:www.web_b.org' 127.0.0.1:8001 | grep 'My hostname is web_b'
	@echo

	@echo "==> Testing virtual host - specified in linked containers"
	docker run -d --name lb3 --link web_c:web_c --link web_d:web_d -p 8002:80 lb
	sleep $(SLEEP_TIME)
	curl --retry 10 --retry-delay 5 -H 'Host:web_c.org' 127.0.0.1:8002 | grep 'My hostname is web_c'
	curl --retry 10 --retry-delay 5 -H 'Host:test.org' 127.0.0.1:8002 | grep 'My hostname is web_d'
	curl --retry 10 --retry-delay 5 -H 'Host:web_d.org' 127.0.0.1:8002 | grep 'My hostname is web_d'
	@echo

	@echo "==> Testing SSL settings"
	docker run -d --name lb4 --link web_a:web_a -e SSL_CERT="$(certs)" -p 443:443 lb
	sleep $(SLEEP_TIME)
	curl --retry 10 --retry-delay 5 --cacert ca.pem -L https://localhost | grep 'My hostname is web_a'
	@echo

	@echo "==> Testing wildcard sub-domains on virtual host (HDR=hdr_end)"
	docker run -d --name lb5 --link web_c:web_c -e HDR="hdr_end" -p 8003:80 lb
	sleep $(SLEEP_TIME)
	curl --retry 10 --retry-delay 5 -H 'Host:www.web_c.org' 127.0.0.1:8003 | grep 'My hostname is web_c'
	@echo

test-with-tutum:build
	@echo "====== Running integration tests with Tutum ======"
	@echo

test-unittest:build
	@echo "====== Running unit test ======"
	@echo