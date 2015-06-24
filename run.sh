#!/bin/bash

if [ "${SSL_CERT}" = "**None**" ]; then
    unset SSL_CERT
fi

if [ "${DEFAULT_SSL_CERT}" = "**None**" ]; then
    unset DEFAULT_SSL_CERT
fi

exec python /haproxy/main.py
