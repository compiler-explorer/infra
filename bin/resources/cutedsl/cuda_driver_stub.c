/*
 * Minimal CUDA driver shim for compile-only CuTe DSL use.
 *
 * CUDA's lib64/stubs/libcuda.so is only a link stub. Older
 * nvidia-cutlass-dsl wheels still call driver entry points while producing
 * compile artifacts, so Compiler Explorer provides enough no-op symbols to
 * let compilation finish without launching kernels.
 */

#include <stddef.h>
#include <string.h>

typedef int CUdevice;
typedef int CUresult;
typedef unsigned long long CUdeviceptr;
typedef void *CUcontext;
typedef void *CUfunction;
typedef void *CUmodule;
typedef void *CUstream;

#define CUDA_SUCCESS 0
#define CU_DEVICE_ATTRIBUTE_COMPUTE_CAPABILITY_MAJOR 75
#define CU_DEVICE_ATTRIBUTE_COMPUTE_CAPABILITY_MINOR 76

static void *stub_handle = (void *)0x1;

CUresult cuInit(unsigned int flags) {
    (void)flags;
    return CUDA_SUCCESS;
}

CUresult cuDriverGetVersion(int *driver_version) {
    if (driver_version) {
        *driver_version = 12090;
    }
    return CUDA_SUCCESS;
}

CUresult cuGetErrorName(CUresult error, const char **name) {
    (void)error;
    if (name) {
        *name = "CUDA_SUCCESS";
    }
    return CUDA_SUCCESS;
}

CUresult cuGetErrorString(CUresult error, const char **str) {
    (void)error;
    if (str) {
        *str = "success";
    }
    return CUDA_SUCCESS;
}

CUresult cuDeviceGetCount(int *count) {
    if (count) {
        *count = 1;
    }
    return CUDA_SUCCESS;
}

CUresult cuDeviceGet(CUdevice *device, int ordinal) {
    if (device) {
        *device = ordinal;
    }
    return CUDA_SUCCESS;
}

CUresult cuDeviceGetName(char *name, int len, CUdevice device) {
    (void)device;
    if (name && len > 0) {
        strncpy(name, "Compiler Explorer CUDA driver stub", (size_t)len - 1);
        name[len - 1] = '\0';
    }
    return CUDA_SUCCESS;
}

CUresult cuDeviceComputeCapability(int *major, int *minor, CUdevice device) {
    (void)device;
    if (major) {
        *major = 9;
    }
    if (minor) {
        *minor = 0;
    }
    return CUDA_SUCCESS;
}

CUresult cuDeviceGetAttribute(int *pi, int attrib, CUdevice device) {
    (void)device;
    if (!pi) {
        return CUDA_SUCCESS;
    }
    if (attrib == CU_DEVICE_ATTRIBUTE_COMPUTE_CAPABILITY_MAJOR) {
        *pi = 9;
    } else if (attrib == CU_DEVICE_ATTRIBUTE_COMPUTE_CAPABILITY_MINOR) {
        *pi = 0;
    } else {
        *pi = 1;
    }
    return CUDA_SUCCESS;
}

CUresult cuCtxGetCurrent(CUcontext *ctx) {
    if (ctx) {
        *ctx = stub_handle;
    }
    return CUDA_SUCCESS;
}

CUresult cuCtxSetCurrent(CUcontext ctx) {
    (void)ctx;
    return CUDA_SUCCESS;
}

CUresult cuCtxCreate(CUcontext *ctx, unsigned int flags, CUdevice device) {
    (void)flags;
    (void)device;
    if (ctx) {
        *ctx = stub_handle;
    }
    return CUDA_SUCCESS;
}

CUresult cuCtxCreate_v2(CUcontext *ctx, unsigned int flags, CUdevice device) {
    return cuCtxCreate(ctx, flags, device);
}

CUresult cuCtxDestroy(CUcontext ctx) {
    (void)ctx;
    return CUDA_SUCCESS;
}

CUresult cuCtxDestroy_v2(CUcontext ctx) {
    return cuCtxDestroy(ctx);
}

CUresult cuCtxSynchronize(void) {
    return CUDA_SUCCESS;
}

CUresult cuModuleLoadData(CUmodule *module, const void *image) {
    (void)image;
    if (module) {
        *module = stub_handle;
    }
    return CUDA_SUCCESS;
}

CUresult cuModuleLoadDataEx(
    CUmodule *module,
    const void *image,
    unsigned int num_options,
    void *options,
    void *option_values) {
    (void)num_options;
    (void)options;
    (void)option_values;
    return cuModuleLoadData(module, image);
}

CUresult cuModuleUnload(CUmodule module) {
    (void)module;
    return CUDA_SUCCESS;
}

CUresult cuModuleGetFunction(CUfunction *function, CUmodule module, const char *name) {
    (void)module;
    (void)name;
    if (function) {
        *function = stub_handle;
    }
    return CUDA_SUCCESS;
}

CUresult cuFuncSetAttribute(CUfunction function, int attrib, int value) {
    (void)function;
    (void)attrib;
    (void)value;
    return CUDA_SUCCESS;
}

CUresult cuLaunchKernel(
    CUfunction function,
    unsigned int grid_dim_x,
    unsigned int grid_dim_y,
    unsigned int grid_dim_z,
    unsigned int block_dim_x,
    unsigned int block_dim_y,
    unsigned int block_dim_z,
    unsigned int shared_mem_bytes,
    CUstream stream,
    void **kernel_params,
    void **extra) {
    (void)function;
    (void)grid_dim_x;
    (void)grid_dim_y;
    (void)grid_dim_z;
    (void)block_dim_x;
    (void)block_dim_y;
    (void)block_dim_z;
    (void)shared_mem_bytes;
    (void)stream;
    (void)kernel_params;
    (void)extra;
    return CUDA_SUCCESS;
}

CUresult cuMemAlloc(CUdeviceptr *dptr, size_t bytesize) {
    (void)bytesize;
    if (dptr) {
        *dptr = 0x100000;
    }
    return CUDA_SUCCESS;
}

CUresult cuMemAlloc_v2(CUdeviceptr *dptr, size_t bytesize) {
    return cuMemAlloc(dptr, bytesize);
}

CUresult cuMemFree(CUdeviceptr dptr) {
    (void)dptr;
    return CUDA_SUCCESS;
}

CUresult cuMemFree_v2(CUdeviceptr dptr) {
    return cuMemFree(dptr);
}

CUresult cuMemcpyHtoD(CUdeviceptr dst_device, const void *src_host, size_t byte_count) {
    (void)dst_device;
    (void)src_host;
    (void)byte_count;
    return CUDA_SUCCESS;
}

CUresult cuMemcpyHtoD_v2(CUdeviceptr dst_device, const void *src_host, size_t byte_count) {
    return cuMemcpyHtoD(dst_device, src_host, byte_count);
}

CUresult cuMemcpyDtoH(void *dst_host, CUdeviceptr src_device, size_t byte_count) {
    (void)src_device;
    if (dst_host && byte_count > 0) {
        memset(dst_host, 0, byte_count);
    }
    return CUDA_SUCCESS;
}

CUresult cuMemcpyDtoH_v2(void *dst_host, CUdeviceptr src_device, size_t byte_count) {
    return cuMemcpyDtoH(dst_host, src_device, byte_count);
}
