# SSH-first Buildroot development

## Security model

SSH user `dnl` may upload arbitrary files only below `/home/dnl/work` and may
invoke the fixed `rasplayer-service` actions. Production Python remains
root-owned because RasPlayer itself runs as root. Granting an SSH account the
ability to install arbitrary unsigned Python into that process would be
equivalent to unrestricted root code execution.

Deployment therefore requires an Ed25519 release signature. The private
release key is root-equivalent authority: keep it off the Pi, outside the
generated image/rootfs, git-ignored, and separate from the SSH login key. The
Pi stores only the public key. A compromised `dnl` session can upload or
request installation but cannot activate modified code without a valid release
signature.

## One-time bootstrap

The signed installer and its public-key provisioning support must already be
present in the root filesystem. An older running image that has only the
original four/five-action `rasplayer-service` helper cannot install this trust
anchor over SSH without bypassing the existing privilege boundary. Bootstrap
that device once by flashing the new image or by installing it from a trusted
physical root console. After that, normal Python and approved helper updates do
not require reflashing.

Create or verify the repository-local development keypair:

```sh
sh buildroot/scripts/create-update-signing-key.sh
```

This command is idempotent: it generates a keypair only when neither key
exists, exports a missing public key from an existing private key, and refuses
a mismatched pair. The exact paths are:

- private: `.local/rasplayer-signing/rasplayer-release-private.pem`;
- public: `buildroot/rasplayer-update-public.pem`.

Both paths are git-ignored. The private key is never copied into Buildroot's
generated target or images. Treat it as root-equivalent authority and back it
up securely. The public key is the only signing artifact copied to the Pi.

After flashing, copy these three local files to the top level of the FAT boot
partition (for example `F:\`) without renaming them:

```text
buildroot/wifi.network
buildroot/dnl_authorized_keys
buildroot/rasplayer-update-public.pem
```

From PowerShell at the repository root, the exact copy commands are:

```powershell
Copy-Item -LiteralPath buildroot\wifi.network -Destination F:\
Copy-Item -LiteralPath buildroot\dnl_authorized_keys -Destination F:\
Copy-Item -LiteralPath buildroot\rasplayer-update-public.pem -Destination F:\
```

`S40provision` installs the public key as root-owned
`/etc/rasplayer-update-public.pem`. Keep the public-key file on the FAT
partition so provisioning remains stable across boots.

## Normal application deployment

The production layout is:

- `/opt/rasplayer/releases/<release>`: immutable root-owned application release;
- `/opt/rasplayer/current`: atomic active-release symlink;
- `/opt/rasplayer/previous`: rollback symlink;
- `/home/dnl/RasPlayer/Sounds`: `dnl`-writable media shared by every release;
- `/home/dnl/work`: unprivileged upload/staging area.

Buildroot initially installs `image-base`. Each signed update must contain the
complete fixed Python allowlist plus the current `rasplayer-service` binary:

```sh
sh buildroot/scripts/build-rasplayer-update.sh \
  dev-20260830-1 \
  /home/dnl/rasplayer-build/output/target/usr/bin/rasplayer-service \
  /tmp/rasplayer-update-dev-20260830-1
```

The bundle builder always uses
`.local/rasplayer-signing/rasplayer-release-private.pem` and invokes the
keypair check before signing. It does not accept an alternate key path.

Upload and apply it:

```sh
sh buildroot/scripts/deploy-rasplayer-update.sh \
  dnl@192.168.0.70 \
  /tmp/rasplayer-update-dev-20260830-1 \
  ~/.ssh/rasplayer_buildroot_ed25519
```

The remote script uploads only to `/home/dnl/work`. The privileged installer:

1. opens only the fixed staging directory and fixed allowlisted filenames;
2. verifies the Ed25519 manifest signature and every SHA-256 payload hash;
3. copies into a new root-owned release directory and fsyncs it;
4. stops RasPlayer under the shared service-control lock;
5. atomically switches `current` and installs the signed helper;
6. restarts RasPlayer and waits up to 20 seconds for manager, child, and
   `LOCAL_READY` state;
7. automatically restores and restarts the previous release/helper if health
   validation fails.

Manual rollback remains available:

```sh
rasplayer-service rollback
```

Use `rasplayer-service status` after deployment. Reusing an existing release
identifier is refused; use a new identifier for every iteration.

The bundle intentionally cannot update its own root-owned deployment verifier,
init/provisioning scripts, libraries, packages, kernel, or boot files. Those
remain part of the image trust base.

## Ultrasonic diagnostic updates

Once the bootstrap image is installed, a newly cross-compiled
`rasplayer-service` helper—including changes to the fixed
`ultrasonic-test` action—can be included as the required helper payload in a
signed application bundle. The transaction installs it with mode `04755` and
rolls it back together with the application release if health validation
fails. Run the diagnostic after deployment with:

```sh
rasplayer-service stop
rasplayer-service ultrasonic-test
rasplayer-service start
```

This cannot be safely bootstrapped onto a pre-installer physical image using
only the unprivileged SSH account; doing so would require an exploit or a
general root path, both of which are explicitly excluded.

## Changes that still require Buildroot rebuild/flash

A full reproducible image build and physical flash remains required for:

- Linux kernel, device tree, firmware, kernel configuration, or modules;
- bootloader/FAT contents, `config.txt`, `cmdline.txt`, or partition layout;
- Buildroot packages, shared libraries, Python extension modules, or toolchain;
- BusyBox configuration, users/groups, device nodes, permissions, or mounts;
- init, Wi-Fi, Dropbear, provisioning, diagnostics, deployment-verifier, or
  service-supervisor infrastructure;
- soundfont/system assets outside the approved application release;
- changes to the deployment allowlist, public-key trust model, or privilege
  boundary.

Ordinary changes to the eight RasPlayer Python files, media under `Sounds`, and
signed updates to the fixed service helper do not require an SD-card flash once
the bootstrap image is running.
