---
name: lookup_ticket_status
track: bonus
kind: read
provider: local_ticket_store
requires_env: []
inputs: [ticket_id]
outputs: [ticket, snapshot_at, source, trust_boundary]
side_effect: none
requires_confirmation: false
---
# lookup_ticket_status

Returns the current status, owner team, and next step for one exact fictional
`LAB-...` ticket ID. It can read seeded mock tickets and tickets created locally
by `create_ticket`. It never lists ticket IDs and does not modify ticket state.
