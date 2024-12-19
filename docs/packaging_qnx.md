## Packing QNX

QNX is a _proprietary_ compiler for which we have been given permissiong to use and install with the educational license. For reference: Matt has an email Dec 19, 2024, 1:01 PM UTC subject "ETAS-VOS / QNX Alignment Discussion Points" granting the permission.

Packaging the QNX compilers is a pain. They have to be installed via a byzantine process downloading installers from [the website](https://www.qnx.com/download/group.html?programid=29178) and applying the license (type the license number and an empty password). The login for the site is in Matt's 1pass; speak to him if you're on the team and you'd like access.

### Installation

Install on a local linux machine with a process similar to:
- download the Linux host from QNX Software Centre
- run the .run file with bash in a terminal (bear in mind it will launch a GUI)
- accept the license
- specify the installation path (e.g. `qnx`) for the installation software itself.
- this then automatically launches the Software Centre GUI
- inside the GUI:
  - log in
  - "Add Installation" and install QNX 8 (not the SDP)
  - select "Advanced Installation Variants" and select all architectures as well as experimental packages (not sure what those are but why not)
  - click through and install (probably to `qnx800`)

(With thanks to `@doodspav` on the C++ language Slack)

The license file was found to have been installed in `~/.qnx/licenses/license` and was manually copied to a safe location on the network.

For each version supported, we then manually tar Jcvf up the `qnx800` or similar directory and `aws s3 cp` the image to the `s3://compiler-explorer/opt-nonfree/qnx-800.tar.xz`.

### Running

The compiler requires some environment variables to run:
- `QNX_SHARED_LICENSE_FILE` points at the license file.
- `QNX_HOST` needs to point at the `host/linux/x86_64/` subdir.
- `QNX_TARGET` needs to point at the `target/qnx` subdir.

The compiler's targeting is controlled by the `-V` command e.g. `-Vgcc_ntoaarch64le` (defaulting to x86).
