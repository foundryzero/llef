/*
This file is a template for an LLDB expression using Objective-C++ syntax.

The Darwin malloc implementation provides an API to read heap metadata at runtime.
The function malloc_size returns a value which is guaranteed to be at least the size of the 
allocated memory for that pointer.

Implementation for 'malloc_size' can be found here:
https://github.com/apple-oss-distributions/libmalloc/blob/main/src/malloc.c

This expression will return a structure containing a uint64 number of entries plus an array of uint64 sizes.
*/

// These values are replaced by Python script before being interpreted by LLDB.
#define COUNT {{COUNT}}
#define BASE_ADDR {{BASE_ADDR}}
#define STEP {{STEP}}

struct {
  uint64_t num_allocations;
  uint64_t sizes[COUNT];
} result;

result.num_allocations = COUNT;

for (uint64_t i = 0; i < COUNT; ++i) {
    // Return size of memory block at pointer
    result.sizes[i] = (uint64_t)malloc_size((const void *)(BASE_ADDR + i * STEP));
}

// Return to LLDB
result
