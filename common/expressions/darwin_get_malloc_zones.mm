/*
This file is a template for an LLDB expression using Objective-C++ syntax.

The Darwin malloc implementation provides an API to read heap metadata at runtime.
The function 'malloc_get_all_zones' is defined in '<malloc/malloc.h>' and provides a way to
enumerate allocated heap regions using the malloc zone introspection API.

Implementation for 'malloc_get_all_zones' can be found here:
https://github.com/apple-oss-distributions/libmalloc/blob/main/src/malloc.c

Based on LLDB 'heap_find' command: https://github.com/llvm-mirror/lldb/blob/master/examples/darwin/heap_find/heap.py.

This expression will return an array of structs, with 'lo_addr' and 'hi_addr' for each malloc region.
*/


// The calling Python function replaces {{ MAX_MATCHES }} with an integer value.
#define MAX_MATCHES {{MAX_MATCHES}}

#define KERN_SUCCESS 0
/* For region containing pointers */
#define MALLOC_PTR_REGION_RANGE_TYPE 2 

// Store information about memory allocations.
typedef struct vm_range_t {
    uintptr_t address;
    unsigned long size;
} vm_range_t;

// Function prototypes used for callback functions.
typedef void (*range_callback_t)(unsigned int task, void *baton, unsigned int type, uintptr_t ptr_addr,
                                 uintptr_t ptr_size);

typedef int (*memory_reader_t)(unsigned int task, uintptr_t remote_address, unsigned long size, void **local_memory);

typedef void (*vm_range_recorder_t)(unsigned int task, void *baton, unsigned int type, vm_range_t *range,
                                    unsigned int size);

// We only care about the pointer to enumerator, which is the first pointer in the struct.
// Full definition of malloc_introspection_t available in libmalloc/blob/main/include/malloc/malloc.h                                                            
typedef struct malloc_introspection_t {
    // Enumerates all the malloc pointers in use
    int (*enumerator)(unsigned int task, void *, unsigned int type_mask, uintptr_t zone_address, memory_reader_t reader,
                      vm_range_recorder_t recorder);
} malloc_introspection_t;

// We only care about the pointer to malloc_introspection_t which is the 13th pointer in the struct.
// Full definition of malloc_zone_t available in libmalloc/blob/main/include/malloc/malloc.h    
typedef struct malloc_zone_t {
    void *reserved1[12];
    struct malloc_introspection_t *introspect;
} malloc_zone_t;

// Information about memory regions to be returned to LLEF.
struct malloc_region {
    uintptr_t lo_addr;
    uintptr_t hi_addr;
};

typedef struct callback_baton_t {
    range_callback_t callback;
    unsigned int num_matches;
    malloc_region matches[MAX_MATCHES + 1]; // Null terminate
} callback_baton_t;

// Memory read callback function.
memory_reader_t task_peek = [](unsigned int task, uintptr_t remote_address, uintptr_t size,
                               void **local_memory) -> int {
    *local_memory = (void *)remote_address;
    return KERN_SUCCESS;
};

// Callback to populate structure with low, high malloc addresses.
range_callback_t range_callback = [](unsigned int task, void *baton, unsigned int type, uintptr_t ptr_addr,
                                     uintptr_t ptr_size) -> void {
    callback_baton_t *lldb_info = (callback_baton_t *)baton;
    // Upper limit for our array 
    if (lldb_info->num_matches < MAX_MATCHES) {
        uintptr_t lo = ptr_addr;
        uintptr_t hi = lo + ptr_size;
        lldb_info->matches[lldb_info->num_matches].lo_addr = lo;
        lldb_info->matches[lldb_info->num_matches].hi_addr = hi;
        lldb_info->num_matches++;
    }
};

// Callback function from introspect enumerator function. 
vm_range_recorder_t range_recorder = [](unsigned int task, void *baton, unsigned int type, vm_range_t *ranges,
                                          unsigned int size) -> void {
    range_callback_t callback = ((callback_baton_t *)baton)->callback;
    for (unsigned int i = 0; i < size; ++i) {
        // Call range_callback to record each allocation in baton. 
        callback(task, baton, type, ranges[i].address, ranges[i].size);
    }
};

uintptr_t *zones = 0;
unsigned int num_zones = 0;
unsigned int task = 0;

// Populate zones with pointer to a malloc_zone_t array representing heap zones.
int err = (int)malloc_get_all_zones(task, task_peek, &zones, &num_zones);

// baton struct used to store data on heap regions between callbacks.
callback_baton_t baton = {range_callback, 0, {0}};

if (KERN_SUCCESS == err) {
    // Enumerate over all heap zones.
    for (unsigned int i = 0; i < num_zones; ++i) {
        const malloc_zone_t *zone = (const malloc_zone_t *)zones[i];
        /* Introspection API will call our callback for each heap region (rather than each allocation as in
        * malloc_info) */
        if (zone && zone->introspect)
            zone->introspect->enumerator(task, &baton, MALLOC_PTR_REGION_RANGE_TYPE, (uintptr_t)zone, task_peek,
            range_recorder);
    }
}
/* return the value */
baton.matches