# vim: tabstop=4 shiftwidth=4 softtabstop=4

# Copyright 2012 Cloudbase Solutions Srl
#
#    Licensed under the Apache License, Version 2.0 (the "License"); you may
#    not use this file except in compliance with the License. You may obtain
#    a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
#    WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
#    License for the specific language governing permissions and limitations
#    under the License.

import re

from cloudbaseinit.openstack.common import cfg
from cloudbaseinit.openstack.common import log as logging
from cloudbaseinit.osutils import factory as osutils_factory
from cloudbaseinit.plugins import base

LOG = logging.getLogger(__name__)

opts = [
    cfg.StrOpt('network_adapter', default=None, help='Network adapter to '
               'configure. If not specified, the first two adapters will '
               'be configured (if available)')
]

CONF = cfg.CONF
CONF.register_opts(opts)


class NetworkConfigPlugin(base.BasePlugin):
    def execute(self, service):
        meta_data = service.get_meta_data('openstack')
        if 'network_config' not in meta_data:
            return (base.PLUGIN_EXECUTION_DONE, False)

        network_config = meta_data['network_config']
        if 'content_path' not in network_config:
            return (base.PLUGIN_EXECUTION_DONE, False)

        content_path = network_config['content_path']
        content_name = content_path.rsplit('/', 1)[-1]
        debian_network_conf = service.get_content('openstack', content_name)

        LOG.debug('network config content:\n%s' % debian_network_conf)

        # Get available network adapters
        osutils = osutils_factory.OSUtilsFactory().get_os_utils()
        available_adapters = osutils.get_network_adapters()

        network_adapter_name = CONF.network_adapter
        LOG.info('adapter: \'%s\'' % network_adapter_name)
        if network_adapter_name:
            available_adapters = [network_adapter_name]

        # First NIC
        if len(available_adapters) >= 1:
            network_adapter_name = available_adapters[0]
            # TODO (alexpilotti): implement a proper grammar
            m = re.search(r'iface eth0 inet static\s+'
                          r'address\s+(?P<address>[^\s]+)\s+'
                          r'netmask\s+(?P<netmask>[^\s]+)\s+'
                          r'broadcast\s+(?P<broadcast>[^\s]+)\s+'
                          r'gateway\s+(?P<gateway>[^\s]+)\s+'
                          r'dns\-nameservers\s+(?P<dnsnameservers>[^\r\n]+)\s+',
                          debian_network_conf)
            if not m:
                raise Exception("network_config format not recognized")

            address = m.group('address')
            netmask = m.group('netmask')
            broadcast = m.group('broadcast')
            gateway = m.group('gateway')
            dnsnameservers = m.group('dnsnameservers').strip().split(' ')

            LOG.info('Configuring first network adapter: \'%s\'' % network_adapter_name)
            reboot_required = osutils.set_static_network_config(
                network_adapter_name, address, netmask, broadcast, gateway, dnsnameservers)
        else:
             raise Exception("No network adapter available")

        # Second NIC
        if len(available_adapters) >= 2:
            network_adapter_name = available_adapters[1]

            m = re.search(r'iface eth1 inet static\s+'
                          r'address\s+(?P<address>[^\s]+)\s+'
                          r'netmask\s+(?P<netmask>[^\s]+)\s+'
                          r'broadcast\s+(?P<broadcast>[^\s]+)\s+'
                          r'up\s+route\s+add\s+-net\s+(?P<r_destination>[^\s]+)\s+netmask\s+(?P<r_netmask>[^\s]+)\s+gw\s+(?P<r_gateway>[^\s]+)',
                          debian_network_conf)
            if not m:
                raise Exception("network_config format not recognized")

            address = m.group('address')
            netmask = m.group('netmask')
            broadcast = m.group('broadcast')
            r_destination = m.group('r_destination')
            r_netmask = m.group('r_netmask')
            r_gateway = m.group('r_gateway')

            LOG.info('Configuring second network adapter: \'%s\'' % network_adapter_name)
            reboot_required = reboot_required or osutils.set_static_network_config(
                network_adapter_name, address, netmask, broadcast, r_gateway, dnsnameservers)

            LOG.info('Adding static route')
            osutils.add_static_route(r_destination, r_netmask, r_gateway, 1, 1)

        return (base.PLUGIN_EXECUTION_DONE, reboot_required)
