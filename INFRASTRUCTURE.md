# Linux / systemd Infrastructure Hardening Sample

**Status:** self-owned implementation sample. Not client production history. Final persistent-executor acceptance is still pending, so this is not presented as a completed production deployment.

The goal of this work is to run automation/code workers without inheriting the interactive owner's workstation identity, credentials, filesystem access, or production authority.

## Implemented boundary pattern

A dedicated service identity is combined with systemd and AppArmor controls such as:

```ini
User=idrah-builder
NoNewPrivileges=yes
ProtectSystem=strict
ProtectHome=yes
PrivateDevices=yes
ProtectKernelTunables=yes
ProtectKernelModules=yes
ProtectControlGroups=yes
RestrictSUIDSGID=yes
LockPersonality=yes
CapabilityBoundingSet=
IPAddressDeny=any
IPAddressAllow=localhost
```

The service also uses explicit read/write path restrictions, process and memory limits, syscall filtering, and a dedicated state directory.

## Why these controls matter

- dedicated identity -> worker does not run as the owner
- `NoNewPrivileges` + empty capabilities -> no ambient privilege escalation
- filesystem allow-listing -> only assigned state/workspaces are writable
- `ProtectHome` -> owner browser/keyring/SSH material stays outside the worker
- network restriction -> outbound access is deliberately bounded
- task/memory/file-descriptor limits -> runaway jobs fail inside a constrained envelope

## Operating approach for VPS changes

For externally reachable services, I treat a successful local command as insufficient evidence. Before a firewall/proxy/binding change I capture the current listeners, service/container bindings, firewall state, externally visible behavior and a rollback path. After the change, I verify from outside the host that the unwanted port is actually unreachable while the intended HTTPS/webhook path still works.

That distinction matters with Docker-published ports and host firewall rules: configuration state and externally observed exposure are not always the same thing.

## Boundary

This note demonstrates engineering approach and implemented self-owned hardening controls. It does not claim prior client VPS deployments, SOC/compliance certification, penetration-test results, or unattended production authority.
