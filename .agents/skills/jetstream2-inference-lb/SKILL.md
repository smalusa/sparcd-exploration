---
name: jetstream2-inference-lb
description: Jetstream2 inference load balancer operations. Use when creating, checking, repairing, testing, or updating the Octavia LB that exposes llm.jetstream-cloud.org through the SPARCd Jetstream2 project.
---

# Jetstream2 Inference Load Balancer

Use this skill for the SPARCd Jetstream2 Octavia load balancer that exposes the Jetstream2 direct inference API to this workstation.

## Current State

- Project: `BIO260073` (`1be924c0bcd5411e8ef1a7f0a57c693c`)
- Load balancer: `js2-inference-smalusa-lb`
- Listener: `js2-inference-smalusa-443`
- Pool: `js2-inference-smalusa-pool`
- Backend member: `149.165.156.93:443`
- Protocol: TCP passthrough
- VIP: `10.3.173.143`
- Floating IP: `149.165.159.15`
- Public hostname expected by clients: `llm.jetstream-cloud.org`
- Hosts entry needed on this workstation: `149.165.159.15 llm.jetstream-cloud.org`

The LB is TCP passthrough. Do not use the floating IP as the HTTPS hostname in clients; TLS SNI must remain `llm.jetstream-cloud.org`.

## OpenStack Auth

Credentials live outside the repo at `C:\Development\openstack\clouds.yaml`. Do not copy secrets into project files or skill files.

In PowerShell, configure commands like this:

```powershell
$env:PATH = "C:\Users\smalusa\.local\bin;$env:PATH"
$env:OS_CLIENT_CONFIG_FILE = "C:\Development\openstack\clouds.yaml"
openstack --os-cloud openstack token issue
```

If the Octavia commands are missing, install the OpenStack CLI with the Octavia plugin in the same `uv` tool environment:

```powershell
uv tool install --with python-octaviaclient python-openstackclient
```

## Safety Rules

- Keep OpenStack operations scoped to the existing `BIO260073` project unless the user explicitly asks otherwise.
- Treat the existing `SPARCDWebServer` instance and floating IP `149.165.173.165` as unrelated infrastructure. Do not modify them unless explicitly asked.
- Prefer a single-user `/32` listener ACL. Do not widen to `0.0.0.0/0` or broad ISP ranges unless the user explicitly asks and accepts the exposure.
- Avoid deleting the LB, listener, pool, health monitor, member, or floating IP unless the user asks for cleanup.
- Never commit OpenStack credentials or application credential secrets.

## Common Checks

Use the bundled helper for a quick status check:

```powershell
.agents\skills\jetstream2-inference-lb\scripts\status.ps1
```

Manual equivalent:

```powershell
$env:PATH = "C:\Users\smalusa\.local\bin;$env:PATH"
$env:OS_CLIENT_CONFIG_FILE = "C:\Development\openstack\clouds.yaml"
openstack --os-cloud openstack loadbalancer show js2-inference-smalusa-lb -c provisioning_status -c operating_status -c vip_address -c vip_port_id -f yaml
openstack --os-cloud openstack loadbalancer listener show js2-inference-smalusa-443 -c allowed_cidrs -c provisioning_status -c operating_status -f yaml
openstack --os-cloud openstack loadbalancer member list js2-inference-smalusa-pool -f yaml
openstack --os-cloud openstack floating ip show 149.165.159.15 -c floating_ip_address -c fixed_ip_address -c status -f yaml
```

## Update Listener ACL

When the workstation moves to another Wi-Fi network, update the listener ACL to the current public IPv4:

```powershell
.agents\skills\jetstream2-inference-lb\scripts\update-acl.ps1
```

Manual equivalent:

```powershell
$ip = Invoke-RestMethod -Uri "https://api.ipify.org" -UseBasicParsing
openstack --os-cloud openstack loadbalancer listener set --allowed-cidr "$ip/32" js2-inference-smalusa-443 --wait
```

The listener VIP is IPv4-only, so IPv6 CIDRs are not valid for this LB.

## Test Inference

Use the bundled test script:

```powershell
.agents\skills\jetstream2-inference-lb\scripts\test-inference.ps1
```

Manual model-list test that bypasses local DNS with `curl --resolve`:

```powershell
curl.exe --resolve llm.jetstream-cloud.org:443:149.165.159.15 https://llm.jetstream-cloud.org/llama-4-scout/v1/models
```

Expected model IDs include:

- `llama-4-scout`
- `Llama-4-Scout`
- `Llama-4-Scout-17B-16E-Instruct`
- `Kimi-K2.6`
- `moonshotai/Kimi-K2.6`
- `gpt-oss-120b`

## OpenCode Client Notes

The OpenCode provider must use the hostname URL so TLS SNI stays correct:

```jsonc
{
  "provider": {
    "jetstream2-llama": {
      "name": "Jetstream2 (LB - vLLM)",
      "npm": "@ai-sdk/openai-compatible",
      "options": {
        "baseURL": "https://llm.jetstream-cloud.org/llama-4-scout/v1/"
      }
    }
  }
}
```

If requests fail from OpenCode but `curl --resolve` works, check the Windows hosts file and DNS cache:

```powershell
Resolve-DnsName llm.jetstream-cloud.org -Type A
```

It should resolve to `149.165.159.15` on this workstation.

## Troubleshooting

- `openstack: 'loadbalancer' is not an openstack command`: reinstall with `uv tool install --with python-octaviaclient python-openstackclient`.
- Listener update fails with IPv6 compatibility error: use current public IPv4 only.
- `curl` in PowerShell acts like `Invoke-WebRequest`: use `curl.exe` explicitly.
- TLS failure when using `https://149.165.159.15/...`: use `https://llm.jetstream-cloud.org/...` plus hosts/DNS override or `curl.exe --resolve`.
- HTTP `401`: the request may be bypassing the LB or the backend may reject the source path. Verify the LB floating IP, listener ACL, and SNI/Host.
