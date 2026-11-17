# Security policy

## Reporting

Please report security issues privately to the maintainer rather than opening a
public issue. Do not include camera backups, `private/` session data, device
identifiers, or keys in a report.

## Scope

This project talks to a camera over USB and invokes upstream tools that run code
on the camera. The following are in scope:

- Path traversal or arbitrary file write in the installer
- Command injection through user-supplied paths
- Accidental inclusion of `private/` data in logs or releases
- Bypass of write confirmations or gates

## Out of scope

- Vulnerabilities in the upstream projects (report them upstream)
- Physical damage caused by ignoring the documented gates
- Regulatory compliance of enabling 5GHz in a given region

## Handling device data

`runs/` and the upstream session directories may contain device identifiers and
full library snapshots. Keep them private; never attach them to a public issue.
