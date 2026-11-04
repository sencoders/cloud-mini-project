# Task 5: VLSM allocation of 10.20.0.0/16

Allocate largest requirements first, using the smallest power-of-two address
block with at least H + 2 addresses. Each next network starts immediately after
the previous broadcast; all starts are correctly aligned to their prefix.

| Subnet | Required hosts | Calculation | Network | CIDR | Usable range | Broadcast | Usable hosts |
|---|---:|---|---|---|---|---|---:|
| app | 1,000 | 2^10 − 2 = 1,022 ≥ 1,000; /22 | 10.20.0.0 | 10.20.0.0/22 | 10.20.0.1–10.20.3.254 | 10.20.3.255 | 1,022 |
| public | 250 | 2^8 − 2 = 254 ≥ 250; /24 | 10.20.4.0 | 10.20.4.0/24 | 10.20.4.1–10.20.4.254 | 10.20.4.255 | 254 |
| data | 100 | 2^7 − 2 = 126 ≥ 100; /25 | 10.20.5.0 | 10.20.5.0/25 | 10.20.5.1–10.20.5.126 | 10.20.5.127 | 126 |
| management | 20 | 2^5 − 2 = 30 ≥ 20; /27 | 10.20.5.128 | 10.20.5.128/27 | 10.20.5.129–10.20.5.158 | 10.20.5.159 | 30 |

The next smaller blocks provide 510, 126, 62 and 14 usable hosts respectively,
which fail the corresponding requirements. Allocated address counts are
1,024 + 256 + 128 + 32 = 1,440; 65,536 − 1,440 = 64,096 addresses remain.
The first unallocated address is 10.20.5.160. The public load balancer and app
service placement are the assignment's hypothetical subnet design; these NACL
rules are simulated, not claimed to be installed as a cloud-provider firewall.

## Stateless rules and order (under half a page)

`nacl.json` checks rules in ascending number order. Inbound rule 100 denies
**all protocols/ports** from 198.51.100.0/24 before broad web allows. Moving that
deny below an allow for 80/443 would let abusive web packets match first.
Management SSH is restricted to 10.20.5.128/27. Unmatched traffic is denied.

A stateless NACL remembers no connection. Allowing a request does not allow its
reply automatically: outbound TCP 8000 reaches the app, while inbound TCP
1024–65535 from the app allows its replies to the load balancer's ephemeral
ports. Inbound web/management SSH requests need outbound TCP 1024–65535 replies
to client ephemeral ports anywhere. UDP and other unmatched traffic stay denied.
These port rules cannot distinguish an established reply from a new packet
with identical fields. Because 8000 is itself an ephemeral port, the outbound
client-reply rule also matches port 8000 outside app; blocking that would violate
the stated client ephemeral range. The abusive-range block applies inbound;
stateless outbound reply matching does not infer whether an inbound packet passed.

Run: `python tools/nacl_sim.py network/nacl.json network/packets_sample.jsonl --check`.
