import ipaddress
import json

import pytest

from tools.nacl_sim import decide, load_rules


@pytest.mark.parametrize('direction,protocol,port,address,expected', [
    ('inbound','tcp',80,'198.51.100.0','deny'),
    ('inbound','tcp',443,'198.51.100.255','deny'),
    ('inbound','udp',443,'198.51.100.9','deny'),
    ('inbound','tcp',80,'203.0.113.7','allow'),
    ('inbound','tcp',443,'203.0.113.7','allow'),
    ('inbound','udp',80,'203.0.113.7','deny'),
    ('inbound','tcp',22,'10.20.5.129','allow'),
    ('inbound','tcp',22,'10.20.5.158','allow'),
    ('inbound','tcp',22,'10.20.5.127','deny'),
    ('inbound','tcp',22,'10.20.5.160','deny'),
    ('inbound','tcp',22,'203.0.113.7','deny'),
    ('inbound','tcp',1024,'10.20.0.1','allow'),
    ('inbound','tcp',65535,'10.20.3.254','allow'),
    ('inbound','tcp',1023,'10.20.0.1','deny'),
    ('inbound','tcp',65535,'10.20.4.1','deny'),
    ('inbound','udp',60000,'10.20.0.1','deny'),
    ('outbound','tcp',8000,'10.20.1.1','allow'),
    ('outbound','tcp',1024,'192.0.2.55','allow'),
    ('outbound','tcp',65535,'192.0.2.55','allow'),
    ('outbound','tcp',1023,'192.0.2.55','deny'),
    ('outbound','tcp',80,'10.20.1.1','deny'),
    ('outbound','udp',8000,'10.20.1.1','deny'),
    ('outbound','tcp',8000,'192.0.2.55','allow'),
    ('outbound','tcp',60000,'198.51.100.9','allow'),
])
def test_stateless_nacl(direction, protocol, port, address, expected):
    action, number = decide(load_rules('network/nacl.json'),
        {'direction': direction, 'protocol': protocol, 'port': port, 'address': address})
    assert action == expected


def test_vlsm_smallest_blocks_contiguous_and_inside_parent():
    parent = ipaddress.ip_network('10.20.0.0/16')
    networks = [ipaddress.ip_network(n) for n in
                ['10.20.0.0/22','10.20.4.0/24','10.20.5.0/25','10.20.5.128/27']]
    for n, hosts in zip(networks,[1000,250,100,20]):
        assert n.subnet_of(parent) and n.num_addresses-2 >= hosts
        assert n.num_addresses//2-2 < hosts
    assert int(networks[0].network_address) == int(parent.network_address)
    assert all(int(a.broadcast_address)+1 == int(b.network_address) for a,b in zip(networks,networks[1:]))
    rules = json.load(open('network/nacl.json'))
    assert rules['inbound'][0]['action'] == 'deny' and rules['inbound'][0]['protocol'] == 'all'
