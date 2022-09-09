
mount_opt() {
    mkdir -p /opt/compiler-explorer
    mountpoint /opt/compiler-explorer || mount --bind /efs/compiler-explorer /opt/compiler-explorer

    mkdir -p /opt/intel
    mountpoint /opt/intel || mount --bind /efs/intel /opt/intel

    mkdir -p /opt/arm
    mountpoint /opt/arm || mount --bind /efs/arm /opt/arm

    [ -f /opt/.health ] || touch /opt/.health
    mountpoint /opt/.health || mount --bind /efs/.health /opt/.health

    ./mount-all-img.sh
}
