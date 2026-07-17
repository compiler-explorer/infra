#!/usr/bin/env bash
set -euo pipefail

sfpi_version="${1:?sfpi version required}"
tt_metal_dep="${2:?tt-metal headers path required}"
sfpi_root="${3:?sfpi root required}"

mkdir -p "${sfpi_root}/build/sfpi" "${sfpi_root}/tt_metal"
cp -a "${sfpi_root}/include" "${sfpi_root}/build/sfpi/"

mkdir -p "${sfpi_root}/tt_metal/hw" "${sfpi_root}/tt_metal/tt-llk" "${sfpi_root}/tt_metal/hw/ckernels"
cp -a "${tt_metal_dep}/tt_metal/hw/inc" "${sfpi_root}/tt_metal/hw/"
cp -a "${tt_metal_dep}/tt_metal/tt-llk/common" "${sfpi_root}/tt_metal/tt-llk/"
mkdir -p "${sfpi_root}/tt_metal/tt-llk/tests/helpers"
cp -a "${tt_metal_dep}/tt_metal/tt-llk/tests/helpers/include" "${sfpi_root}/tt_metal/tt-llk/tests/helpers/"
cp -a "${tt_metal_dep}/tt_metal/tt-llk/tt_llk_wormhole_b0" "${sfpi_root}/tt_metal/tt-llk/"
cp -a "${tt_metal_dep}/tt_metal/tt-llk/tt_llk_blackhole" "${sfpi_root}/tt_metal/tt-llk/"
mkdir -p "${sfpi_root}/tt_metal/hw/ckernels/wormhole_b0/metal"
mkdir -p "${sfpi_root}/tt_metal/hw/ckernels/blackhole/metal"
cp -a "${tt_metal_dep}/tt_metal/hw/ckernels/wormhole_b0/metal/llk_api" \
  "${sfpi_root}/tt_metal/hw/ckernels/wormhole_b0/metal/"
cp -a "${tt_metal_dep}/tt_metal/hw/ckernels/blackhole/metal/llk_api" \
  "${sfpi_root}/tt_metal/hw/ckernels/blackhole/metal/"

case "${sfpi_version}" in
  7.55.0)
    cat > "${sfpi_root}/include/ce_sfpi_compat.h" <<'HEADER_EOF'
#pragma once

#include <cstdint>

#include "internal/risc_attribs.h"

#if defined(__riscv_xtttensixbh)
#include "internal/tt-1xx/blackhole/tensix.h"
#elif defined(__riscv_xtttensixwh)
#include "internal/tt-1xx/wormhole/tensix.h"
#else
#error "Unsupported SFPI architecture for instrn_buffer compatibility shim"
#endif

namespace ckernel {
inline volatile tt_reg_ptr std::uint32_t *const instrn_buffer =
    reinterpret_cast<volatile std::uint32_t *>(INSTRN_BUF_BASE);
}
HEADER_EOF
    ;;
  *)
    echo "Unsupported SFPI version: ${sfpi_version}" >&2
    exit 1
    ;;
esac
