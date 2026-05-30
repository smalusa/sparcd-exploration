$ErrorActionPreference = "Stop"

$env:PATH = "C:\Users\smalusa\.local\bin;$env:PATH"
$env:OS_CLIENT_CONFIG_FILE = "C:\Development\openstack\clouds.yaml"

Write-Host "== Load balancer =="
openstack --os-cloud openstack loadbalancer show js2-inference-smalusa-lb -c provisioning_status -c operating_status -c vip_address -c vip_port_id -f yaml

Write-Host "`n== Listener =="
openstack --os-cloud openstack loadbalancer listener show js2-inference-smalusa-443 -c allowed_cidrs -c provisioning_status -c operating_status -f yaml

Write-Host "`n== Pool members =="
openstack --os-cloud openstack loadbalancer member list js2-inference-smalusa-pool -f yaml

Write-Host "`n== Floating IP =="
openstack --os-cloud openstack floating ip show 149.165.159.15 -c floating_ip_address -c fixed_ip_address -c status -f yaml
