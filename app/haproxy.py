import logging
import subprocess
import sys
import time

import tutum

from cfg import cfg_calc, cfg_save, cfg_to_text
from constants import *
import utils


# Global Var
HAPROXY_CURRENT_SUBPROCESS = None
LINKED_SERVICES_ENDPOINTS = None
PREVIOUS_CFG_TEXT = None

logger = logging.getLogger("tutum_haproxy")


def reload_haproxy(haproxy_process):
    if haproxy_process:
        # Reload haproxy
        logger.info("Reloading HAProxy")
        process = subprocess.Popen(HAPROXY_CMD + ["-sf", str(haproxy_process.pid)])
        haproxy_process.wait()
        logger.info("HAProxy reloaded")
        return process
    else:
        # Launch haproxy
        logger.info("Launching HAProxy")
        return subprocess.Popen(HAPROXY_CMD)


def run():
    vhost = utils.parse_vhost(VIRTUAL_HOST, os.environ)
    backend_routes = utils.parse_backend_routes(os.environ)
    cfg = cfg_calc(backend_routes, vhost)
    cfg_text = cfg_to_text(cfg)
    logger.info("HAProxy configuration:\n%s" % cfg_text)
    cfg_save(cfg_text, CONFIG_FILE)

    logger.info("Launching HAProxy")
    p = subprocess.Popen(HAPROXY_CMD)
    p.wait()


def fetch_tutum_obj(uri):
    while True:
        try:
            obj = tutum.Utils.fetch_by_resource_uri(uri)
            break
        except Exception as e:
            logging.error(e)
            time.sleep(API_ERROR_RETRY_TIME)
    return obj


def run_tutum(container_uri):
    global PREVIOUS_CFG_TEXT, HAPROXY_CURRENT_SUBPROCESS
    container = fetch_tutum_obj(container_uri)

    envvars = {}
    for pair in container.container_envvars:
        envvars[pair['key']] = pair['value']
    vhost = utils.parse_vhost(VIRTUAL_HOST, envvars)
    backend_routes = utils.parse_backend_routes_tutum(container.linked_to_container)

    cfg = cfg_calc(backend_routes, vhost)
    cfg_text = cfg_to_text(cfg)
    if PREVIOUS_CFG_TEXT != cfg_text:
        logger.info("HAProxy configuration:\n%s" % cfg_text)
        cfg_save(cfg_text, CONFIG_FILE)
        PREVIOUS_CFG_TEXT = cfg_text
        HAPROXY_CURRENT_SUBPROCESS = reload_haproxy(HAPROXY_CURRENT_SUBPROCESS)


def tutum_event_handler(event):
    global LINKED_SERVICES_ENDPOINTS
    # When service scale up/down or container start/stop/terminate/redeploy, reload the service
    if event.get("state", "") not in ["In progress", "Pending", "Terminating", "Starting", "Scaling", "Stopping"] and \
                    event.get("action", "").lower() == "update" and \
                    len(set(LINKED_SERVICES_ENDPOINTS).intersection(set(event.get("parents", [])))) > 0:
        run_tutum(TUTUM_CONTAINER_API_URI)

    # Add/remove services linked to haproxy
    if event.get("state", "") == "Success" and TUTUM_SERVICE_API_URI in event.get("parents", []):
        service = fetch_tutum_obj(TUTUM_SERVICE_API_URI)
        service_endpoints = [srv.get("to_service") for srv in service.linked_to_service]
        if LINKED_SERVICES_ENDPOINTS != service_endpoints:
            LINKED_SERVICES_ENDPOINTS = service_endpoints
            run_tutum(TUTUM_CONTAINER_API_URI)


def init_tutum_settings():
    global LINKED_SERVICES_ENDPOINTS
    service = fetch_tutum_obj(TUTUM_SERVICE_API_URI)
    LINKED_SERVICES_ENDPOINTS = [srv.get("to_service") for srv in service.linked_to_service]


def main():
    logging.basicConfig(stream=sys.stdout)
    logging.getLogger("tutum_haproxy").setLevel(logging.DEBUG if DEBUG else logging.INFO)

    # Tell the user the mode of autoupdate we are using, if any
    if TUTUM_SERVICE_API_URI and TUTUM_CONTAINER_API_URI:
        if TUTUM_AUTH:
            logger.info("HAProxy has access to Tutum API - will reload list of backends in real-time")
        else:
            logger.warning(
                "HAProxy doesn't have access to Tutum API and it's running in Tutum - you might want to give "
                "an API role to this service for automatic backend reconfiguration")
    else:
        logger.info("HAProxy is not running in Tutum")

    if TUTUM_SERVICE_API_URI and TUTUM_CONTAINER_API_URI and TUTUM_AUTH:
        init_tutum_settings()
        run_tutum(TUTUM_CONTAINER_API_URI)
        events = tutum.TutumEvents()
        events.on_message(tutum_event_handler)
        events.run_forever()
    else:
        while True:
            run()
            time.sleep(1)


if __name__ == "__main__":
    main()