import logging
import os
import sys

import tutum

from haproxy import Haproxy
from parser import parse_uuid_from_resource_uri

__version__ = '0.2'
tutum.user_agent = "tutum-haproxy/%s" % __version__

DEBUG = os.getenv("DEBUG", False)

logger = logging.getLogger("haproxy")


def run_haproxy():
    haproxy = Haproxy()
    haproxy.update()


def tutum_event_handler(event):
    logger.debug(event)
    # When service scale up/down or container start/stop/terminate/redeploy, reload the service
    if event.get("state", "") not in ["In progress", "Pending", "Terminating", "Starting", "Scaling", "Stopping"] and \
                    event.get("type", "").lower() in ["container", "service"] and \
                    len(set(Haproxy.cls_linked_services).intersection(set(event.get("parents", [])))) > 0:
        logger.info("Tutum event detected: %s %s is %s" %
                    (event["type"], parse_uuid_from_resource_uri(event.get("resource_uri", "")), event["state"]))
        run_haproxy()

    # Add/remove services linked to haproxy
    if event.get("state", "") == "Success" and Haproxy.cls_service_uri in event.get("parents", []):
        service = Haproxy.fetch_tutum_obj(Haproxy.cls_service_uri)
        service_endpoints = [srv.get("to_service") for srv in service.linked_to_service]
        if Haproxy.cls_linked_services != service_endpoints:
            removed = ", ".join(set(Haproxy.cls_linked_services) - set(service_endpoints))
            added = ", ".join(set(service_endpoints) - set(Haproxy.cls_linked_services))
            changes = "Tutum event detected:"
            if removed:
                changes += " linked removed: %s" % removed
            if added:
                changes += " linked added: %s" % added
            logger.info(changes)
            Haproxy.cls_linked_services = service_endpoints
            run_haproxy()


def main():
    logging.basicConfig(stream=sys.stdout)
    logging.getLogger("haproxy").setLevel(logging.DEBUG if DEBUG else logging.INFO)

    if Haproxy.cls_container_uri and Haproxy.cls_service_uri:
        if Haproxy.cls_tutum_auth:
            logger.info("HAProxy has access to Tutum API - will reload list of backends in real-time")
        else:
            logger.warning(
                "HAProxy doesn't have access to Tutum API and it's running in Tutum - you might want to give "
                "an API role to this service for automatic backend reconfiguration")
    else:
        logger.info("HAProxy is not running in Tutum")

    if Haproxy.cls_container_uri and Haproxy.cls_service_uri and Haproxy.cls_tutum_auth:
        events = tutum.TutumEvents()
        events.on_open(run_haproxy)
        events.on_message(tutum_event_handler)
        events.run_forever()
    else:
        run_haproxy()


if __name__ == "__main__":
    main()
