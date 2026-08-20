# OCI ARM evidence node

The intended shape is one Always Free-labeled `VM.Standard.A1.Flex` instance in the tenancy home region, sized at no more than the currently documented total free allowance (2 OCPUs and 12 GB RAM) with the default 50 GB Always Free boot volume. Capacity can be unavailable, and idle Always Free instances can be reclaimed; either case simply removes this optional provider.

Use an Always Free-eligible Ubuntu image, an SSH public key, and a security list allowing TCP 22 only from the operator's current public IP/CIDR. Do not open application ports. The node needs outbound HTTPS only.

After copying or cloning this repository on the instance, run `sudo bash Projects/AurumBuild/oci/bootstrap-oci-arm.sh`. The dedicated unprivileged `aurum-arm` user receives no login shell, repository write credential, cloud API key, or promotion authority. Every six hours it resolves the branch to an exact commit SHA, verifies that detached commit in a digest-pinned ARM container, and writes local evidence under `/var/lib/aurum-arm/evidence/`.

OCI ARM is `VERIFY-ONLY`; it is never accepted as BBPI4 physical evidence.
