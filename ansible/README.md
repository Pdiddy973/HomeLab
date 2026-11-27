# Ansible runbooks

Playbooks that Semaphore on iapetus (10.0.30.33) runs against the homelab.

- `inventory/hosts.yml`: every host, grouped by what it needs. `basic_test` lists the hosts that already have the `iapetus-ansible` key.
- `playbooks/ping.yml`: checks Ansible reaches each host in `basic_test`.
- `playbooks/check-updates.yml`: lists pending package updates in `basic_test` without installing anything.

`ansible.cfg` sits at the repo root, since Ansible reads it from the folder it runs in; Semaphore and a hand run from the root both pick it up.

In Semaphore, set the inventory to `ansible/inventory/hosts.yml` and the playbook path to `ansible/playbooks/<name>.yml`.
