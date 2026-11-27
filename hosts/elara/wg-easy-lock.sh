#!/bin/sh
# Lets only Management, Trusted and Home Assistant reach wg-easy's web page on TCP 51821
set -e
iptables -N WGEASY-LOCK 2>/dev/null || iptables -F WGEASY-LOCK
for src in 10.0.1.0/24 10.0.10.0/24 10.0.30.30; do
  iptables -A WGEASY-LOCK -s "$src" -j RETURN
done
iptables -A WGEASY-LOCK -j DROP
iptables -C DOCKER-USER -p tcp -m conntrack --ctorigdstport 51821 --ctdir ORIGINAL -j WGEASY-LOCK 2>/dev/null || \
  iptables -I DOCKER-USER -p tcp -m conntrack --ctorigdstport 51821 --ctdir ORIGINAL -j WGEASY-LOCK
