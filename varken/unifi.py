# SPDX-FileCopyrightText: 2018 Boerderij
# SPDX-FileCopyrightText: 2026 HoneyBearTech
# SPDX-License-Identifier: MIT
"""UniFi: the traffic and load of a UniFi Security Gateway."""

from datetime import UTC, datetime
from logging import getLogger
from typing import TYPE_CHECKING

from requests import Request, Session

from varken.helpers import connection_handler

if TYPE_CHECKING:
    from varken.metrics import Metrics
    from varken.structures import UniFiServer


class UniFiAPI:
    """A UniFi controller through its API, signed in with a user name and password."""

    def __init__(self, server: UniFiServer, output: Metrics) -> None:
        """Sign in to the controller and find the site; `output` takes the points."""
        self.output = output
        self.server = server
        self.site = self.server.site
        # Create session to reduce server web thread load, and globally define pageSize for all requests
        self.session = Session()
        self.logger = getLogger()
        self.get_retry = True
        self.get_cookie()
        self.get_site()

    def __repr__(self) -> str:
        """Name the server as the log does."""
        return f'<unifi-{self.server.id}>'

    def get_cookie(self) -> None:
        """Sign in, and keep the session cookie the controller answers with."""
        endpoint = '/api/login'
        pre_cookies = {'username': self.server.username, 'password': self.server.password, 'remember': True}
        req = self.session.prepare_request(Request('POST', self.server.url + endpoint, json=pre_cookies))
        post = connection_handler(self.session, req, verify=self.server.verify_ssl, as_is_reply=True)

        if not post or not post.cookies.get('unifises'):
            self.logger.error('Could not retrieve session cookie from UniFi Controller')
            return

        cookies = {'unifises': post.cookies.get('unifises')}
        self.session.cookies.update(cookies)

    def get_site(self) -> None:
        """Find the configured site, by its name or its description, among the controller's sites."""
        endpoint = '/api/self/sites'
        req = self.session.prepare_request(Request('GET', self.server.url + endpoint))
        get = connection_handler(self.session, req, verify=self.server.verify_ssl)

        if not get:
            self.logger.error('Could not get list of sites from UniFi Controller')
            return
        site = [
            site['name']
            for site in get['data']
            if site['name'].lower() == self.server.site.lower() or site['desc'].lower() == self.server.site.lower()
        ]
        if site:
            self.site = site[0]
        else:
            self.logger.error('Could not map site %s to a site id/alias', self.server.site)

    def get_usg_stats(self) -> None:
        """Write a point with the gateway's traffic and load; a failed request signs in again and retries once."""
        now = datetime.now(UTC).astimezone().isoformat()
        endpoint = f'/api/s/{self.site}/stat/device'
        req = self.session.prepare_request(Request('GET', self.server.url + endpoint))
        get = connection_handler(self.session, req, verify=self.server.verify_ssl)

        if not get:
            if self.get_retry:
                self.get_retry = False
                self.logger.error('Attempting to reauthenticate for unifi-%s', self.server.id)
                self.get_cookie()
                self.get_usg_stats()
            else:
                self.get_retry = True
                self.logger.error('Disregarding Job get_usg_stats for unifi-%s', self.server.id)
            return

        if not self.get_retry:
            self.get_retry = True

        devices = {device['name']: device for device in get['data'] if device.get('name')}

        if devices.get(self.server.usg_name):
            device = devices[self.server.usg_name]
        else:
            self.logger.error('Could not find a USG named %s from your UniFi Controller', self.server.usg_name)
            return

        try:
            points = [
                {
                    'measurement': 'UniFi',
                    'tags': {'model': device['model'], 'name': device['name']},
                    'time': now,
                    'fields': {
                        'bytes_current': device['wan1']['bytes-r'],
                        'rx_bytes_total': device['wan1']['rx_bytes'],
                        'rx_bytes_current': device['wan1']['rx_bytes-r'],
                        'tx_bytes_total': device['wan1']['tx_bytes'],
                        'tx_bytes_current': device['wan1']['tx_bytes-r'],
                        'cpu_loadavg_1': float(device['sys_stats']['loadavg_1']),
                        'cpu_loadavg_5': float(device['sys_stats']['loadavg_5']),
                        'cpu_loadavg_15': float(device['sys_stats']['loadavg_15']),
                        'cpu_util': float(device['system-stats']['cpu']),
                        'mem_util': float(device['system-stats']['mem']),
                    },
                }
            ]
            self.output.write_points(points)
        except KeyError as e:
            self.logger.error('Error building payload for unifi. Discarding. Error: %s', e)
