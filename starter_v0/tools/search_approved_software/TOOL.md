---
name: search_approved_software
track: bonus
kind: read
provider: local_approved_software_catalog
requires_env: []
inputs: [query, operating_system, approval_status, top_k]
outputs: [results, snapshot_at, source, trust_boundary]
side_effect: none
requires_confirmation: false
---
# search_approved_software

Searches the fictional Northstar Labs approved-software catalog by product name,
alias, operating system, and approval status. The result explains whether a
product is approved, conditional, or blocked and how employees can request it.
The tool is read-only and never installs software.
