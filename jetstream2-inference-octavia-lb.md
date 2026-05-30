# Jetstream2 Inference API via Octavia Load Balancer

This handoff describes how to create an OpenStack Octavia TCP passthrough load balancer for the Jetstream2 direct inference API. It is written for a different target project, different users, and user-specific allowed IP addresses.

## Inputs

Collect these values before starting:

- OpenStack auth for the target project: OpenRC path or `OS_CLOUD` name
- Target project/allocation name
- User allowed public IP CIDR, usually `<USER_PUBLIC_IP>/32`
- Whether to allocate a new floating IP or use an existing one
- Desired resource name prefix, for example `js2-inference-<username>`

## Backend

- Inference backend IP: `149.165.156.93`
- Backend port: `443`
- Protocol: TCP passthrough
- Client must preserve SNI/Host for `llm.jetstream-cloud.org`

## Discover Project State

Authenticate first:

```bash
source <OPENRC>
```

Then inspect available resources:

```bash
openstack project show <PROJECT>
openstack network list
openstack subnet list
openstack floating ip list
openstack loadbalancer list
openstack loadbalancer listener list
```

Choose:

- Private subnet for the LB VIP, usually `auto_allocated_subnet_v4`
- Public network for the floating IP, usually `public`

## Create Load Balancer

Create the LB:

```bash
openstack loadbalancer create \
  --name <PREFIX>-lb \
  --vip-subnet-id <PRIVATE_SUBNET_ID> \
  --wait
```

Create the TCP listener with the user allowlist:

```bash
openstack loadbalancer listener create \
  --name <PREFIX>-443 \
  --protocol TCP \
  --protocol-port 443 \
  --allowed-cidr <USER_PUBLIC_IP>/32 \
  --wait \
  <PREFIX>-lb
```

Create the TCP pool:

```bash
openstack loadbalancer pool create \
  --name <PREFIX>-pool \
  --lb-algorithm ROUND_ROBIN \
  --listener <PREFIX>-443 \
  --protocol TCP \
  --wait
```

Add the Jetstream2 inference service as the backend member:

```bash
openstack loadbalancer member create \
  --address 149.165.156.93 \
  --protocol-port 443 \
  --wait \
  <PREFIX>-pool
```

Add a TCP health monitor:

```bash
openstack loadbalancer healthmonitor create \
  --delay 10 \
  --timeout 5 \
  --max-retries 3 \
  --type TCP \
  --wait \
  <PREFIX>-pool
```

## Attach Floating IP

Allocate a new floating IP:

```bash
openstack floating ip create public
```

Get the LB VIP port:

```bash
openstack loadbalancer show <PREFIX>-lb -c vip_port_id -f value
```

Attach the floating IP:

```bash
openstack floating ip set --port <VIP_PORT_ID> <FLOATING_IP_ID>
```

## Verify

Check LB state:

```bash
openstack loadbalancer show <PREFIX>-lb \
  -c provisioning_status -c operating_status -c vip_address -c vip_port_id -f yaml
```

Check listener ACL:

```bash
openstack loadbalancer listener show <PREFIX>-443 \
  -c allowed_cidrs -c provisioning_status -c operating_status -f yaml
```

Check backend member:

```bash
openstack loadbalancer member list <PREFIX>-pool -f yaml
```

Check floating IP:

```bash
openstack floating ip show <FLOATING_IP_ID> \
  -c floating_ip_address -c fixed_ip_address -c status -f yaml
```

## Test From Allowed IP

Test the models endpoint from the allowed user IP:

```bash
curl --resolve llm.jetstream-cloud.org:443:<LB_FLOATING_IP> \
  https://llm.jetstream-cloud.org/gpt-oss-120b/v1/models
```

Test a prompt:

```bash
curl --resolve llm.jetstream-cloud.org:443:<LB_FLOATING_IP> \
  https://llm.jetstream-cloud.org/gpt-oss-120b/v1/chat/completions \
  -H 'Content-Type: application/json' \
  -d '{"model":"gpt-oss-120b","messages":[{"role":"user","content":"Reply with only the word ok."}],"max_tokens":64,"temperature":0}'
```

Expected results:

- `/models` returns a model list
- `/chat/completions` returns assistant content `ok`

## OpenCode Client Notes

If the client uses OpenCode:

- Base URL must use hostname, not raw floating IP: `https://llm.jetstream-cloud.org/gpt-oss-120b/v1`
- Add DNS or hosts override so `llm.jetstream-cloud.org` resolves to `<LB_FLOATING_IP>`
- Model: `gpt-oss-120b`
- API key: any non-empty string if client requires one

## Failure Branches

- If pool member is unhealthy, confirm Octavia can route to `149.165.156.93:443` from the target project.
- If allowed client times out, verify listener `allowed_cidrs` exactly includes the user's public IP as `/32`.
- If TLS fails, ensure client connects with SNI `llm.jetstream-cloud.org` via `--resolve` or DNS override.
- If backend returns `401`, the LB source may not be accepted by Jetstream2 inference network policy. Use a proxy VM in the project instead.

## Cleanup

Remove all created LB resources:

```bash
openstack loadbalancer delete --cascade --wait <PREFIX>-lb
```
