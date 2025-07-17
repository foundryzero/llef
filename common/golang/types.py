"""Python version of the Go typing system. A little-endian architecture is assumed throughout this file."""

import struct
from dataclasses import dataclass
from typing import Union

from lldb import SBError, SBProcess

from common.golang.constants import (
    GO_TUNE_ENTROPY_SOFTNESS,
    GO_TUNE_LONG_SLICE,
    GO_TUNE_LONG_STRING,
    GO_TUNE_MAX_SWISSMAP_DIRS,
    GO_TUNE_SLICE_RATE,
    GO_TUNE_SLICE_THRESHOLD,
    GO_TUNE_STRING_RATE,
    GO_TUNE_STRING_THRESHOLD,
)
from common.golang.data import (
    Confidence,
    GoData,
    GoDataArray,
    GoDataBad,
    GoDataBool,
    GoDataComplex,
    GoDataFloat,
    GoDataInteger,
    GoDataMap,
    GoDataPointer,
    GoDataSlice,
    GoDataString,
    GoDataStruct,
    GoDataUnparsed,
)
from common.golang.util_stateless import entropy, rate_candidate_length, read_varint


class TypeHeader:
    """
    Used as a data structure to store common information present for every possible type.
    """

    size: int
    ptrbytes: int
    t_hash: int
    tflag: int
    align: int
    fieldalign: int
    kind: int
    name: str

    def __str__(self) -> str:
        return (
            f"(size={self.size} ptrbytes={self.ptrbytes} hash={hex(self.t_hash)} tflag={self.tflag} align={self.align}"
            f" fieldalign={self.fieldalign} kind={hex(self.kind & 31)} name='{self.name}')"
        )


@dataclass(frozen=True)
class PopulateInfo:
    """
    Reduce length of populate() signature by packaging some read-only parameters in a struct.
    """

    types: int
    etypes: int
    ptr_size: int
    ptr_spec: str  # for struct.unpack, e.g. Q for ptr_size == 8 bytes and L for 4 bytes.


@dataclass(frozen=True)
class ExtractInfo:
    """
    Reduce length of extract_at() signature by packaging some read-only parameters in a struct.
    """

    proc: SBProcess
    ptr_size: int
    type_structs: dict[int, "GoType"]


def safe_read_unsigned(info: ExtractInfo, addr: int, size: int) -> Union[int, None]:
    """
    Wraps proc.ReadUnsignedFromMemory to avoid internal LLDB errors when parameters are out of bounds.
    Uses the same endianness as LLDB understands the target to be using.

    :param ExtractInfo info: Contains the process to perform the read on, and the pointer size.
    :param int addr: The address to begin reading at.
    :param int size: The number of bytes to read as the unsigned integer.
    :return Union[int, None]: If the operation succeeded, returns the integer. Else None.
    """
    pointer_too_big = 1 << (info.ptr_size * 8)
    if addr >= 0 and size > 0 and addr + size <= pointer_too_big:
        err = SBError()
        value = info.proc.ReadUnsignedFromMemory(addr, size, err)
        if err.Success():
            return value
    return None


def safe_read_bytes(info: ExtractInfo, addr: int, size: int) -> Union[bytes, None]:
    """
    Wraps proc.ReadMemory to avoid internal LLDB errors when parameters are out of bounds.

    :param ExtractInfo info: Contains the process to perform the read on, and the pointer size.
    :param int addr: The address to begin reading at.
    :param int size: The number of bytes to read.
    :return Union[bytes, None]: If the operation succeeded, returns the byte string. Else None.
    """
    pointer_too_big = 1 << (info.ptr_size * 8)
    if addr >= 0 and size > 0 and addr + size <= pointer_too_big:
        err = SBError()
        buffer = info.proc.ReadMemory(addr, size, err)
        if err.Success() and buffer is not None:
            return buffer
    return None


class GoType:
    """
    The base class from which all Python versions of Go types inherit.
    """

    header: TypeHeader
    version: tuple[int, int]

    # The following pattern occurs several times for different purposes in different type structs, but "child" is
    # common enough that we put it here as an example.
    # ..._addr and ..._type take default values 0 and None respectively. Upon populate(), ..._addr may get set to
    # a non-zero address. This indicates that, at a later time, code should come along and set ..._type to the
    # corresponding GoType as looked up in the type_structs dictionary. We can't set it now as it might not exist yet!
    child_addr: int
    child_type: Union["GoType", None]

    def __init__(self, header: TypeHeader, version: tuple[int, int]) -> None:
        self.header = header
        self.child_addr = 0  # indicate none until told otherwise.
        self.child_type = None
        self.version = version

    def populate(self, type_section: bytes, offset: int, info: PopulateInfo) -> Union[list[int], None]:
        """
        Overridden by complex datatypes: reads further data included after the header to populate type-specific fields
        with extra information.

        :param bytes type_section: Slice of program memory that the ModuleData structure refers to as the type section.
        :param int offset: The offset in the section that immediately follows the header for this type.
        :param PopulateInfo info: Packaged properties of the binary that we need to correctly continue parsing.
        :return Union[list[int], None]: If extra parsing succeeds, returns a list of pointers to other type information
                                        structures that we may need to parse recursively. Otherwise None.
        """
        return []

    def fixup_types(self, type_structs: dict[int, "GoType"]) -> None:
        """
        Overridden by complex datatypes: is called on each type after a full type_structs dictionary has been built.
        Allows them to populate any ..._type fields by looking up ..._addr addresses.

        :param dict[int, GoType] type_structs: The completed mapping from type information structure address to
                                               subclasses of GoType.
        """

    def extract_at(self, info: ExtractInfo, addr: int, seen: set[int], depth: int) -> GoData:
        """
        Overriden by most classes: reads the memory from an address to attempt to extract the object of this type,
        and all of its children. The children are encapsulated in the GoData object. Also calculates a heuristic, which
        is a confidence level of the address provided actually being of this type.

        :param SBProcess proc: The LLDB process object currently being worked on.
        :param int addr: The memory address to start unpacking at.
        :param int ptr_size: The size of a pointer in bytes.
        :param set[int] seen: A set, initially empty, to keep track of pointers already dereferenced.
        :param int depth: How deeply down nested structures/arrays/slices to unpack.
        :return GoData: A Python object replicating the Go object after unpacking.
        """

        return GoDataPointer(heuristic=Confidence.CERTAIN.to_float(), address=addr)

    def get_underlying_type(self, depth: int) -> str:
        """
        Implemented by each type: Returns the underlying type for this GoType.

        :param int depth: Avoid infinite recursion by tracking how deeply we've dereferenced.
        :return str: The type represented by this GoType, in Go syntax, without using type synonyms.
        """
        return "?"

    @classmethod
    def make_from(cls, header: TypeHeader, version: tuple[int, int]) -> Union["GoType", None]:
        """
        Selects the correct subclass of GoType based on the Kind, and returns an initialised object of it.

        :param TypeHeader header: An already-completed TypeHeader, containing the Kind attribute.
        :return Union[GoType, None]: If the Kind was valid, an initialised object for the subclass of GoType.
                                     Otherwise None.
        """
        enum: dict[int, type[GoType]] = {
            0: GoTypeInvalid,
            1: GoTypeBool,
            2: GoTypeInt,
            3: GoTypeInt8,
            4: GoTypeInt16,
            5: GoTypeInt32,
            6: GoTypeInt64,
            7: GoTypeUint,
            8: GoTypeUint8,
            9: GoTypeUint16,
            10: GoTypeUint32,
            11: GoTypeUint64,
            12: GoTypeUintptr,
            13: GoTypeFloat32,
            14: GoTypeFloat64,
            15: GoTypeComplex64,
            16: GoTypeComplex128,
            17: GoTypeArray,
            18: GoTypeChan,
            19: GoTypeFunc,
            20: GoTypeInterface,
            21: GoTypeMap,
            22: GoTypePointer,
            23: GoTypeSlice,
            24: GoTypeString,
            25: GoTypeStruct,
            26: GoTypeUnsafePointer,
        }

        # Type enum is only lower 5 bits.
        subtype = enum.get(header.kind & 0b11111)
        if subtype:
            # calls GoType.__init__ since subtype does not redefine.
            return subtype(header, version)
        return None

    def __str__(self) -> str:
        return self.__class__.__name__ + str(self.header)


class GoTypeInvalid(GoType):
    def get_underlying_type(self, depth: int) -> str:
        return "invalid"

    def extract_at(self, info: ExtractInfo, addr: int, seen: set[int], depth: int) -> GoData:
        return GoDataBad(heuristic=Confidence.JUNK.to_float())


class GoTypeBool(GoType):
    def get_underlying_type(self, depth: int) -> str:
        return "bool"

    def extract_at(self, info: ExtractInfo, addr: int, seen: set[int], depth: int) -> GoData:
        extracted: Union[GoData, None] = None

        val = safe_read_unsigned(info, addr, 1)
        if val is not None:
            if val == 1:
                extracted = GoDataBool(heuristic=Confidence.CERTAIN.to_float(), value=True)
            elif val == 0:
                extracted = GoDataBool(heuristic=Confidence.CERTAIN.to_float(), value=False)

        if extracted is None:
            extracted = GoDataBad(heuristic=Confidence.JUNK.to_float())
        return extracted


class GoTypeInt(GoType):
    def get_underlying_type(self, depth: int) -> str:
        return "int"

    def extract_at(self, info: ExtractInfo, addr: int, seen: set[int], depth: int) -> GoData:
        val = safe_read_unsigned(info, addr, info.ptr_size)
        if val is not None:
            sign_bit = 1 << (info.ptr_size - 1)
            # convert unsigned to signed
            val -= (val & sign_bit) << 1
            return GoDataInteger(heuristic=Confidence.CERTAIN.to_float(), value=val)
        return GoDataBad(heuristic=Confidence.JUNK.to_float())


class GoTypeInt8(GoType):
    def get_underlying_type(self, depth: int) -> str:
        return "int8"

    def extract_at(self, info: ExtractInfo, addr: int, seen: set[int], depth: int) -> GoData:
        val = safe_read_unsigned(info, addr, 1)
        if val is not None:
            sign_bit = 1 << 7
            # convert unsigned to signed
            val -= (val & sign_bit) << 1
            return GoDataInteger(heuristic=Confidence.CERTAIN.to_float(), value=val)
        return GoDataBad(heuristic=Confidence.JUNK.to_float())


class GoTypeInt16(GoType):
    def get_underlying_type(self, depth: int) -> str:
        return "int16"

    def extract_at(self, info: ExtractInfo, addr: int, seen: set[int], depth: int) -> GoData:
        val = safe_read_unsigned(info, addr, 2)
        if val is not None:
            sign_bit = 1 << 15
            # convert unsigned to signed
            val -= (val & sign_bit) << 1
            return GoDataInteger(heuristic=Confidence.CERTAIN.to_float(), value=val)
        return GoDataBad(heuristic=Confidence.JUNK.to_float())


class GoTypeInt32(GoType):
    def get_underlying_type(self, depth: int) -> str:
        return "int32"

    def extract_at(self, info: ExtractInfo, addr: int, seen: set[int], depth: int) -> GoData:
        val = safe_read_unsigned(info, addr, 4)
        if val is not None:
            sign_bit = 1 << 31
            # convert unsigned to signed
            val -= (val & sign_bit) << 1
            return GoDataInteger(heuristic=Confidence.CERTAIN.to_float(), value=val)
        return GoDataBad(heuristic=Confidence.JUNK.to_float())


class GoTypeInt64(GoType):
    def get_underlying_type(self, depth: int) -> str:
        return "int64"

    def extract_at(self, info: ExtractInfo, addr: int, seen: set[int], depth: int) -> GoData:
        val = safe_read_unsigned(info, addr, 8)
        if val is not None:
            sign_bit = 1 << 63
            # convert unsigned to signed
            val -= (val & sign_bit) << 1
            return GoDataInteger(heuristic=Confidence.CERTAIN.to_float(), value=val)
        return GoDataBad(heuristic=Confidence.JUNK.to_float())


class GoTypeUint(GoType):
    def get_underlying_type(self, depth: int) -> str:
        return "uint"

    def extract_at(self, info: ExtractInfo, addr: int, seen: set[int], depth: int) -> GoData:
        val = safe_read_unsigned(info, addr, info.ptr_size)
        if val is not None:
            return GoDataInteger(heuristic=Confidence.CERTAIN.to_float(), value=val)
        return GoDataBad(heuristic=Confidence.JUNK.to_float())


class GoTypeUint8(GoType):
    def get_underlying_type(self, depth: int) -> str:
        return "uint8"

    def extract_at(self, info: ExtractInfo, addr: int, seen: set[int], depth: int) -> GoData:
        val = safe_read_unsigned(info, addr, 1)
        if val is not None:
            return GoDataInteger(heuristic=Confidence.CERTAIN.to_float(), value=val)
        return GoDataBad(heuristic=Confidence.JUNK.to_float())


class GoTypeUint16(GoType):
    def get_underlying_type(self, depth: int) -> str:
        return "uint16"

    def extract_at(self, info: ExtractInfo, addr: int, seen: set[int], depth: int) -> GoData:
        val = safe_read_unsigned(info, addr, 2)
        if val is not None:
            return GoDataInteger(heuristic=Confidence.CERTAIN.to_float(), value=val)
        return GoDataBad(heuristic=Confidence.JUNK.to_float())


class GoTypeUint32(GoType):
    def get_underlying_type(self, depth: int) -> str:
        return "uint32"

    def extract_at(self, info: ExtractInfo, addr: int, seen: set[int], depth: int) -> GoData:
        val = safe_read_unsigned(info, addr, 4)
        if val is not None:
            return GoDataInteger(heuristic=Confidence.CERTAIN.to_float(), value=val)
        return GoDataBad(heuristic=Confidence.JUNK.to_float())


class GoTypeUint64(GoType):
    def get_underlying_type(self, depth: int) -> str:
        return "uint64"

    def extract_at(self, info: ExtractInfo, addr: int, seen: set[int], depth: int) -> GoData:
        val = safe_read_unsigned(info, addr, 8)
        if val is not None:
            return GoDataInteger(heuristic=Confidence.CERTAIN.to_float(), value=val)
        return GoDataBad(heuristic=Confidence.JUNK.to_float())


class GoTypeUintptr(GoType):
    def get_underlying_type(self, depth: int) -> str:
        return "uintptr"

    def extract_at(self, info: ExtractInfo, addr: int, seen: set[int], depth: int) -> GoData:
        val = safe_read_unsigned(info, addr, info.ptr_size)
        if val is not None:
            return GoDataPointer(heuristic=Confidence.CERTAIN.to_float(), address=val)
        return GoDataBad(heuristic=Confidence.JUNK.to_float())


class GoTypeFloat32(GoType):
    def get_underlying_type(self, depth: int) -> str:
        return "float32"

    def extract_at(self, info: ExtractInfo, addr: int, seen: set[int], depth: int) -> GoData:
        data = safe_read_bytes(info, addr, 4)
        if data is not None:
            extracted: tuple[float] = struct.unpack("<f", data)
            return GoDataFloat(heuristic=Confidence.CERTAIN.to_float(), value=extracted[0])
        return GoDataBad(heuristic=Confidence.JUNK.to_float())


class GoTypeFloat64(GoType):
    def get_underlying_type(self, depth: int) -> str:
        return "float64"

    def extract_at(self, info: ExtractInfo, addr: int, seen: set[int], depth: int) -> GoData:
        data = safe_read_bytes(info, addr, 8)
        if data is not None:
            extracted: tuple[float] = struct.unpack("<d", data)
            return GoDataFloat(heuristic=Confidence.CERTAIN.to_float(), value=extracted[0])
        return GoDataBad(heuristic=Confidence.JUNK.to_float())


class GoTypeComplex64(GoType):
    def get_underlying_type(self, depth: int) -> str:
        return "complex64"

    def extract_at(self, info: ExtractInfo, addr: int, seen: set[int], depth: int) -> GoData:
        data = safe_read_bytes(info, addr, 8)
        if data is not None:
            extracted: tuple[float, float] = struct.unpack("<ff", data)
            return GoDataComplex(heuristic=Confidence.CERTAIN.to_float(), real=extracted[0], imag=extracted[1])
        return GoDataBad(heuristic=Confidence.JUNK.to_float())


class GoTypeComplex128(GoType):
    def get_underlying_type(self, depth: int) -> str:
        return "complex128"

    def extract_at(self, info: ExtractInfo, addr: int, seen: set[int], depth: int) -> GoData:
        data = safe_read_bytes(info, addr, 16)
        if data is not None:
            extracted: tuple[float, float] = struct.unpack("<dd", data)
            return GoDataComplex(heuristic=Confidence.CERTAIN.to_float(), real=extracted[0], imag=extracted[1])
        return GoDataBad(heuristic=Confidence.JUNK.to_float())


class GoTypeArray(GoType):
    length: int

    def populate(self, type_section: bytes, offset: int, info: PopulateInfo) -> Union[list[int], None]:
        (sub_elem, sup_slice, this_len) = struct.unpack_from("<" + info.ptr_spec * 3, type_section, offset)
        self.child_addr = sub_elem
        self.length = this_len
        return [sub_elem, sup_slice]

    def fixup_types(self, type_structs: dict[int, "GoType"]) -> None:
        self.child_type = type_structs.get(self.child_addr, None)

    def get_underlying_type(self, depth: int) -> str:
        if depth > 0:
            subtype = "?"
            if self.child_type is not None:
                subtype = self.child_type.get_underlying_type(depth - 1)
            return f"[{self.length}]{subtype}"
        else:
            return self.header.name

    def extract_at(self, info: ExtractInfo, addr: int, seen: set[int], depth: int) -> GoData:
        extracted: Union[GoData, None] = None

        if self.child_type is not None:
            align = self.child_type.header.align
            elem_size = ((self.child_type.header.size + align - 1) // align) * align

            if addr % align == 0 and elem_size * self.length == self.header.size:
                if depth > 0:

                    values = []
                    heuristic_sum = 0.0
                    if self.length > 0:
                        valid = True
                        for i in range(self.length):
                            elem = self.child_type.extract_at(info, addr + i * elem_size, seen, depth - 1)
                            if isinstance(elem, GoDataBad):
                                # then the memory doesn't actually exist for this element,
                                # so the memory for the array does not exist either.
                                valid = False
                                break

                            heuristic_sum += elem.heuristic
                            values.append(elem)

                        if valid:
                            extracted = GoDataArray(heuristic=heuristic_sum / self.length, contents=values)

                    else:
                        extracted = GoDataArray(heuristic=Confidence.CERTAIN.to_float(), contents=[])

                else:
                    extracted = GoDataUnparsed(heuristic=Confidence.CERTAIN.to_float(), address=addr)

        if extracted is None:
            extracted = GoDataBad(heuristic=Confidence.JUNK.to_float())
        return extracted


class GoTypeChan(GoType):
    direction: int

    def populate(self, type_section: bytes, offset: int, info: PopulateInfo) -> Union[list[int], None]:
        (sub_elem, direction) = struct.unpack_from("<" + info.ptr_spec * 2, type_section, offset)
        self.child_addr = sub_elem
        self.direction = direction
        return [sub_elem]

    def fixup_types(self, type_structs: dict[int, "GoType"]) -> None:
        self.child_type = type_structs.get(self.child_addr, None)

    def get_underlying_type(self, depth: int) -> str:
        if depth > 0:
            subtype = "?"
            if self.child_type is not None:
                subtype = self.child_type.get_underlying_type(depth - 1)

            base_name = "chan"
            if self.direction == 1:
                # Receiving channel
                base_name = "<-" + base_name
            elif self.direction == 2:
                # Sending channel
                base_name = base_name + "<-"

            return f"{base_name} {subtype}"
        else:
            return self.header.name


class GoTypeFunc(GoType):
    input_addrs: list[int]
    input_types: list[Union[GoType, None]]  # the _types lists will be instantiated and filled later.
    output_addrs: list[int]
    output_types: list[Union[GoType, None]]
    is_variadic: bool

    def populate(self, type_section: bytes, offset: int, info: PopulateInfo) -> Union[list[int], None]:
        # the size of param count fields and the uncommon offset addition is NOT pointer size dependent.
        (num_param_in, num_param_out) = struct.unpack_from("<HH", type_section, offset)

        # We consumed 32 bits. On 32-bit, read the next byte: on 64-bit, need 32 bits of padding.
        offset += info.ptr_size

        # num_param_out & 0x8000 indicates if the function is variadic (last input is a slice)
        self.is_variadic = num_param_out & 0x8000 != 0
        num_param_out &= 0x7FFF

        has_uncommon = self.header.tflag & 1 == 1
        if has_uncommon:
            offset += 16

        self.input_addrs = list(struct.unpack_from("<" + info.ptr_spec * num_param_in, type_section, offset))
        offset += num_param_in * info.ptr_size
        self.output_addrs = list(struct.unpack_from("<" + info.ptr_spec * num_param_out, type_section, offset))

        return self.input_addrs + self.output_addrs

    def fixup_types(self, type_structs: dict[int, "GoType"]) -> None:
        self.input_types = []
        for addr in self.input_addrs:
            self.input_types.append(type_structs.get(addr, None))

        self.output_types = []
        for addr in self.output_addrs:
            self.output_types.append(type_structs.get(addr, None))

    def get_underlying_type(self, depth: int) -> str:
        if depth > 0:
            inputs = []
            for t in self.input_types:
                if t is not None:
                    inputs.append(t.get_underlying_type(depth - 1))
                else:
                    inputs.append("?")
            if self.is_variadic:
                inputs[-1] = "..." + inputs[-1].removeprefix("[]")

            outputs = []
            for t in self.output_types:
                if t is not None:
                    outputs.append(t.get_underlying_type(depth - 1))
                else:
                    outputs.append("?")

            build = f"func({', '.join(inputs)})"
            output_str = ", ".join(outputs)
            if len(outputs) == 1:
                build += f" {output_str}"
            elif len(outputs) > 1:
                build += f" ({output_str})"
        else:
            build = self.header.name
        return build


class GoTypeInterfaceMethod:
    name: str
    type_addr: int
    type: Union[GoType, None]

    def __init__(self, name: str, type_addr: int):
        self.type_addr = type_addr
        self.name = name
        self.type = None


class GoTypeInterface(GoType):
    methods: list[GoTypeInterfaceMethod]

    def populate(self, type_section: bytes, offset: int, info: PopulateInfo) -> Union[list[int], None]:
        self.methods = []
        (go_min_version, _) = self.version
        (methods_base, methods_len) = struct.unpack_from("<" + info.ptr_spec * 2, type_section, offset + info.ptr_size)
        # Each method structure in the methods table is a struct of two 32-bit integers.
        for i in range(methods_len):
            imethod_ptr = methods_base + i * 8
            if info.types <= imethod_ptr < info.etypes:
                imethod_offset = imethod_ptr - info.types
                (name_off, type_off) = struct.unpack_from("<II", type_section, imethod_offset)

                name_off += 1
                if go_min_version <= 16:
                    # In this case, the length is big-endian no matter the architecture.
                    (length,) = struct.unpack_from(">H", type_section, name_off)
                    name_off += 2
                else:
                    length, name_off = read_varint(type_section, name_off)

                name = type_section[name_off : name_off + length].decode("utf-8", "replace")

                imethod = GoTypeInterfaceMethod(name=name, type_addr=info.types + type_off)
                self.methods.append(imethod)

        return list(map(lambda x: x.type_addr, self.methods))

    def fixup_types(self, type_structs: dict[int, "GoType"]) -> None:
        for method in self.methods:
            method.type = type_structs.get(method.type_addr)

    def get_underlying_type(self, depth: int) -> str:
        if depth > 0:
            build = ""
            for method in self.methods:
                if method.type is not None:
                    func_name = method.type.get_underlying_type(depth - 1)

                    # Replace func with the actual function name.
                    build += f"{method.name}{func_name.removeprefix('func')}; "
            build = build.removesuffix("; ")
            if len(build) > 0:
                build = f"interface {{ {build} }}"
            else:
                build = "interface {}"
        else:
            build = self.header.name
        return build

    def extract_at(self, info: ExtractInfo, addr: int, seen: set[int], depth: int) -> GoData:
        extracted: Union[GoData, None] = None

        type_ptr: Union[int, None] = None
        fail_nicely = False  # Set to True if we get a successful initial read (so the memory actually exists).

        if len(self.methods) == 0:
            # Empty interface type. This is two ptr_sized integers: first a type pointer, then the data pointer.
            type_ptr = safe_read_unsigned(info, addr, info.ptr_size)
            if type_ptr is not None:
                fail_nicely = True
        else:
            # Non-empty interface type. This is two ptr_sized integers: first an ITab pointer, then the data pointer.
            # Concrete (dynamic) type is available inside ITab.
            itab_ptr = safe_read_unsigned(info, addr, info.ptr_size)
            if itab_ptr is not None:
                fail_nicely = True
                type_ptr = safe_read_unsigned(info, itab_ptr + info.ptr_size, info.ptr_size)

        # Treat this like dereferencing a typed pointer.
        if type_ptr is not None:
            header = TypeHeader()
            extractor = GoTypePointer(header=header, version=self.version)
            extractor.child_type = info.type_structs.get(type_ptr)
            extracted = extractor.extract_at(info, addr + info.ptr_size, seen, depth)

        if extracted is None:
            if fail_nicely:
                extracted = GoDataPointer(heuristic=Confidence.LOW.to_float(), address=addr + info.ptr_size)
            else:
                extracted = GoDataBad(heuristic=Confidence.JUNK.to_float())
        return extracted


class GoTypeMap(GoType):

    key_addr: int
    key_type: Union[GoType, None]
    bucket_addr: int
    bucket_type: Union[GoType, None]

    def populate(self, type_section: bytes, offset: int, info: PopulateInfo) -> Union[list[int], None]:
        (self.key_addr, self.child_addr, self.bucket_addr) = struct.unpack_from(
            "<" + info.ptr_spec * 3, type_section, offset
        )
        self.key_type = None
        self.bucket_type = None
        return [self.key_addr, self.child_addr, self.bucket_addr]

    def fixup_types(self, type_structs: dict[int, "GoType"]) -> None:
        self.key_type = type_structs.get(self.key_addr, None)
        self.child_type = type_structs.get(self.child_addr, None)
        self.bucket_type = type_structs.get(self.bucket_addr, None)

    def get_underlying_type(self, depth: int) -> str:
        key_str = "?"
        if self.key_type is not None:
            key_str = self.key_type.get_underlying_type(depth)
        val_str = "?"
        if self.child_type is not None:
            val_str = self.child_type.get_underlying_type(depth)
        return f"map[{key_str}]{val_str}"

    def extract_at(self, info: ExtractInfo, addr: int, seen: set[int], depth: int) -> GoData:
        extracted: Union[GoData, None] = None

        if self.bucket_type is not None:
            (go_min_version, _) = self.version
            # Minimum version is only lifted to 24 if we are sure the new map implementation is being used
            # (the programmer can choose to use the old version even in 1.24).
            parser: Union[SwissMapParser, NoSwissMapParser]
            if go_min_version < 24:
                parser = NoSwissMapParser(info, self.bucket_type, seen, self.version)
            else:
                parser = SwissMapParser(info, self.bucket_type, seen)
            extracted = parser.parse(addr, depth)
            # changes to seen are still present, since it was passed by reference.

        if extracted is None:
            extracted = GoDataBad(heuristic=Confidence.JUNK.to_float())
        return extracted


class GoTypePointer(GoType):
    def populate(self, type_section: bytes, offset: int, info: PopulateInfo) -> Union[list[int], None]:
        (sub_elem,) = struct.unpack_from("<" + info.ptr_spec, type_section, offset)
        self.child_addr = sub_elem
        return [sub_elem]

    def fixup_types(self, type_structs: dict[int, "GoType"]) -> None:
        self.child_type = type_structs.get(self.child_addr, None)

    def get_underlying_type(self, depth: int) -> str:
        subtype = "?"
        if self.child_type is not None:
            if depth > 0:
                subtype = self.child_type.get_underlying_type(depth - 1)
            else:
                subtype = self.child_type.header.name
        return f"*{subtype}"

    def extract_at(self, info: ExtractInfo, addr: int, seen: set[int], depth: int) -> GoData:
        extracted: Union[GoData, None] = None

        if self.child_type:
            child_ptr = safe_read_unsigned(info, addr, info.ptr_size)
            if child_ptr is not None:
                if child_ptr > 0:
                    if child_ptr not in seen:
                        seen.add(child_ptr)
                        # changes to seen are reflected everywhere, so we'll never dereference again in this extraction.
                        # this is good because we can reduce duplication of displayed information.
                        dereferenced = self.child_type.extract_at(info, child_ptr, seen, depth)
                        if not isinstance(dereferenced, GoDataBad):
                            extracted = dereferenced
                        else:
                            # Then this pointer is not of this type - either memory does not exist, or data is illegal.
                            extracted = GoDataPointer(heuristic=Confidence.JUNK.to_float(), address=child_ptr)
                    else:
                        # Circular references. Slightly downgrade confidence.
                        extracted = GoDataUnparsed(heuristic=Confidence.HIGH.to_float(), address=child_ptr)
                else:
                    # A valid, but null, pointer. Of course these come up - but downgrade the confidence.
                    extracted = GoDataPointer(heuristic=Confidence.MEDIUM.to_float(), address=0)

        if extracted is None:
            extracted = GoDataBad(heuristic=Confidence.JUNK.to_float())
        return extracted


class GoTypeSlice(GoType):
    def populate(self, type_section: bytes, offset: int, info: PopulateInfo) -> Union[list[int], None]:
        (sub_elem,) = struct.unpack_from("<" + info.ptr_spec, type_section, offset)
        self.child_addr = sub_elem
        return [sub_elem]

    def fixup_types(self, type_structs: dict[int, "GoType"]) -> None:
        self.child_type = type_structs.get(self.child_addr, None)

    def get_underlying_type(self, depth: int) -> str:
        subtype = "?"
        if self.child_type is not None:
            subtype = self.child_type.get_underlying_type(depth)
        return f"[]{subtype}"

    def extract_at(self, info: ExtractInfo, addr: int, seen: set[int], depth: int) -> GoData:
        extracted: Union[GoData, None] = None

        if self.child_type:
            align = self.child_type.header.align
            elem_size = ((self.child_type.header.size + align - 1) // align) * align

            base = safe_read_unsigned(info, addr, info.ptr_size)
            length = safe_read_unsigned(info, addr + info.ptr_size, info.ptr_size)
            cap = safe_read_unsigned(info, addr + 2 * info.ptr_size, info.ptr_size)
            if base is not None and length is not None and cap is not None and base % align == 0 and cap >= length:
                values = []

                if cap > 0:
                    # The relationship between length and capacity can present a useful heuristic.
                    # Many Go slices have length = capacity, or the length is very small, or
                    # it is >= 50% of the capacity since Go doubles when reallocating.
                    length_score = min(
                        rate_candidate_length(length, GO_TUNE_SLICE_THRESHOLD, GO_TUNE_SLICE_RATE),
                        rate_candidate_length(cap, 2 * GO_TUNE_SLICE_THRESHOLD, 2 * GO_TUNE_SLICE_RATE),
                    )

                    if depth > 0:
                        if length > 0:
                            heuristic_sum = 0.0

                            # Don't extract a huge number of elements!
                            num_extract = min(length, GO_TUNE_LONG_SLICE)
                            valid = True
                            for i in range(num_extract):
                                elem = self.child_type.extract_at(info, base + i * elem_size, seen, depth - 1)
                                if isinstance(elem, GoDataBad):
                                    valid = False
                                    break

                                heuristic_sum += elem.heuristic
                                values.append(elem)

                            if valid:
                                # Successful parsing here.
                                score = (length_score + (heuristic_sum / num_extract)) / 2
                                extracted = GoDataSlice(
                                    heuristic=score, base=base, length=length, capacity=cap, contents=values
                                )
                            else:
                                # The underlying memory is bad. But we'll still communicate extracted slice
                                # information, (at a low confidence).
                                extracted = GoDataSlice(
                                    heuristic=Confidence.LOW.to_float(),
                                    base=base,
                                    length=length,
                                    capacity=cap,
                                    contents=[],
                                )
                        else:
                            # Length of 0.
                            extracted = GoDataSlice(
                                heuristic=length_score, base=base, length=length, capacity=cap, contents=[]
                            )
                    else:
                        # Ran out of depth.
                        extracted = GoDataUnparsed(heuristic=length_score, address=base)
                else:
                    # Capacity of 0 is quite unusual.
                    extracted = GoDataSlice(
                        heuristic=Confidence.LOW.to_float(), base=base, length=length, capacity=cap, contents=[]
                    )

        if extracted is None:
            extracted = GoDataBad(heuristic=Confidence.JUNK.to_float())
        return extracted


class GoTypeString(GoType):
    def get_underlying_type(self, depth: int) -> str:
        return "string"

    def extract_at(self, info: ExtractInfo, addr: int, seen: set[int], depth: int) -> GoData:
        extracted: Union[GoData, None] = None

        str_start = safe_read_unsigned(info, addr, info.ptr_size)
        length = safe_read_unsigned(info, addr + info.ptr_size, info.ptr_size)

        if str_start is not None and length is not None:
            if length > 0:
                score = rate_candidate_length(length, GO_TUNE_STRING_THRESHOLD, GO_TUNE_STRING_RATE)

                # Only extract the start of a very long string.
                num_extract = min(length, GO_TUNE_LONG_STRING)
                data = safe_read_bytes(info, str_start, num_extract)
                if data is not None:
                    decoded = data.decode("utf-8", "replace")
                    str_len = len(decoded)
                    num_printable = 0
                    for char in decoded:
                        if char.isprintable():
                            num_printable += 1

                    if str_len > 0:
                        score = (score + num_printable / str_len) / 2
                    else:
                        # Then decoding just went utterly wrong.
                        score /= 2
                    extracted = GoDataString(heuristic=score, base=str_start, length=length, contents=data)

                else:
                    # the underlying data is bad. severely tank the heuristic, but keep base and length info.
                    extracted = GoDataString(heuristic=score * 0.2, base=str_start, length=length, contents=b"")
            else:
                # Since Go strings are immutable, it's highly unlikely the empty string comes up that much.
                # This is probably something else.
                extracted = GoDataString(heuristic=Confidence.LOW.to_float(), base=str_start, length=0, contents=b"")

        if extracted is None:
            extracted = GoDataBad(heuristic=Confidence.JUNK.to_float())
        return extracted


class GoTypeStructField:
    offset: int
    name: str
    type_addr: int
    type: Union[GoType, None]

    def __init__(self, offset: int, name: str, type_addr: int):
        self.offset = offset
        self.type_addr = type_addr
        self.name = name
        self.type = None


class GoTypeStruct(GoType):
    fields: list[GoTypeStructField]

    def populate(self, type_section: bytes, offset: int, info: PopulateInfo) -> Union[list[int], None]:
        (go_min_version, go_max_version) = self.version
        (_, fields_addr, fields_len) = struct.unpack_from("<" + info.ptr_spec * 3, type_section, offset)
        self.fields = []

        for i in range(fields_len):
            # Each field struct is 3 pointers wide.
            addr = fields_addr + i * 3 * info.ptr_size
            if info.types <= addr < info.etypes:
                field_struct_offset = addr - info.types
                (field_name_ptr, field_type, field_offset) = struct.unpack_from(
                    "<" + info.ptr_spec * 3, type_section, field_struct_offset
                )

                field_name_ptr = field_name_ptr - info.types + 1

                if go_min_version <= 16:
                    # In this case, the length is big-endian no matter the architecture.
                    (length,) = struct.unpack_from(">H", type_section, field_name_ptr)
                    field_name_ptr += 2
                else:
                    length, field_name_ptr = read_varint(type_section, field_name_ptr)

                name = type_section[field_name_ptr : field_name_ptr + length].decode("utf-8", "replace")

                # And in Go 1.9 through Go 1.18, the field_offset is stored left-shifted by one.
                if go_min_version >= 9 and go_max_version <= 18:
                    field_offset >>= 1
                field = GoTypeStructField(field_offset, name, field_type)
                self.fields.append(field)

        # Ensure we list fields in order of ascending offset.
        self.fields.sort(key=lambda x: x.offset)
        return list(map(lambda x: x.type_addr, self.fields))

    def fixup_types(self, type_structs: dict[int, "GoType"]) -> None:
        for field in self.fields:
            field.type = type_structs.get(field.type_addr, None)

    def get_underlying_type(self, depth: int) -> str:
        build = ""
        if depth > 0:
            for field in self.fields:
                type_str = "?"
                if field.type is not None:
                    type_str = field.type.get_underlying_type(depth - 1)
                build += f"{field.name} {type_str}; "

            build = build.removesuffix("; ")
            if len(build) > 0:
                build = f"struct {{ {build} }}"
            else:
                build = "struct {}"
        else:
            build = self.header.name

        return build

    def extract_at(self, info: ExtractInfo, addr: int, seen: set[int], depth: int) -> GoData:
        extracted: Union[GoData, None] = None
        store = []

        if depth > 0:
            if len(self.fields) > 0:
                heuristic_sum = 0.0

                for field in self.fields:
                    value: GoData = GoDataBad(heuristic=Confidence.JUNK.to_float())
                    if field.type is not None:
                        value = field.type.extract_at(info, addr + field.offset, seen, depth - 1)

                    if isinstance(value, GoDataBad):
                        # it may be uninitialised, while the previous fields in the struct contain good information.
                        # so just return what we've got so far.
                        break

                    heuristic_sum += value.heuristic
                    store.append((field.name, value))

                if len(store) > 0:
                    extracted = GoDataStruct(heuristic=heuristic_sum / len(store), fields=store)
            else:
                # Empty struct.
                extracted = GoDataStruct(heuristic=Confidence.CERTAIN.to_float(), fields=[])
        else:
            # Ran out of depth.
            extracted = GoDataUnparsed(heuristic=Confidence.CERTAIN.to_float(), address=addr)

        if extracted is None:
            extracted = GoDataBad(heuristic=Confidence.JUNK.to_float())
        return extracted


class GoTypeUnsafePointer(GoType):
    def get_underlying_type(self, depth: int) -> str:
        return "unsafe.Pointer"

    def extract_at(self, info: ExtractInfo, addr: int, seen: set[int], depth: int) -> GoData:
        child_ptr = safe_read_unsigned(info, addr, info.ptr_size)
        if child_ptr is not None:
            return GoDataPointer(heuristic=Confidence.CERTAIN.to_float(), address=child_ptr)
        return GoDataBad(heuristic=Confidence.JUNK.to_float())


class NoSwissMapParser:
    """
    A single-use parser for pre-1.24 maps (non-Swiss).
    """

    info: ExtractInfo
    version: tuple[int, int]
    bucket_type: GoType

    # the seen-address set is always passed around by reference, so keep a reference here for easy access.
    # In the unpacking of an entire object we never wish to unpack the same pointer twice (for brevity).
    seen_pointers: set[int]

    def __init__(self, info: ExtractInfo, bucket_type: GoType, seen: set[int], version: tuple[int, int]):
        self.info = info
        self.bucket_type = bucket_type
        self.seen_pointers = seen
        self.version = version

    def __parse_bucket(
        self, nest_depth: int, bucket: GoDataStruct, overflow_depth: int
    ) -> Union[list[tuple[GoData, GoData]], None]:
        """
        Reads the contents of a single bucket, which could be from the main bucket array or an overflow bucket.

        :param int nest_depth: The further depth allowed when extracting the key and value objects.
        :param GoDataStruct bucket: The unpacked bucket object.
        :param int overflow_depth: The number of further overflow buckets that can be followed before giving up.
        :return Union[list[tuple[GoData, GoData]], None]: If parsing succeeded, a list of pairs key/value. Else None.
        """
        from_bucket: Union[list[tuple[GoData, GoData]], None] = None
        accesser = dict(bucket.fields)
        valid = True
        try:
            topbits = accesser["topbits"]
            keys = accesser["keys"]
            elems = accesser["elems"]
            overflow = accesser["overflow"]
        except KeyError:
            valid = False

        # Check bucket structure is as expected.
        if (
            valid
            and isinstance(topbits, GoDataArray)
            and isinstance(keys, GoDataArray)
            and isinstance(elems, GoDataArray)
            and isinstance(overflow, GoDataPointer)
        ):
            bucket_size = len(topbits.contents)
            if bucket_size > 0 and len(keys.contents) == bucket_size and len(elems.contents) == bucket_size:
                from_bucket = []
                for i in range(bucket_size):
                    header_byte_obj = topbits.contents[i]
                    key_obj = keys.contents[i]
                    elem_obj = elems.contents[i]

                    # Check bucket structure is as expected.
                    if isinstance(header_byte_obj, GoDataInteger):
                        h = header_byte_obj.value

                        # h-values 0, 1 and 4 mean an empty cell.
                        if h not in (0, 1, 4):
                            from_bucket.append((key_obj, elem_obj))

                if overflow.address > 0 and self.bucket_type is not None:
                    overflow_bucket_object = self.bucket_type.extract_at(
                        self.info, overflow.address, self.seen_pointers, nest_depth
                    )
                    if isinstance(overflow_bucket_object, GoDataStruct) and overflow_depth > 0:
                        from_overflow = self.__parse_bucket(nest_depth, overflow_bucket_object, overflow_depth - 1)
                        if from_overflow is not None:
                            from_bucket.extend(from_overflow)

        return from_bucket

    def __parse_bucket_list(self, nest_depth: int, buckets_object: GoData, confidence: float) -> Union[GoData, None]:
        """
        Extracts data from the main buckets array of the map, and calculates an average heuristic.

        :param int nest_depth: The further depth allowed when extracting the key and value objects.
        :param GoData buckets_object: The unpacked fixed-length array of bucket objects.
        :param float confidence: The current confidence level from 0.0-1.0.
        :return Union[GoData, None]: If parsing succeeds, returns a populated GoDataMap. Otherwise None.
        """
        extracted: Union[GoData, None] = None

        if isinstance(buckets_object, GoDataArray):
            bucket_list = buckets_object.contents
            valid = True
            entries: list[tuple[GoData, GoData]] = []
            for bucket in bucket_list:
                if isinstance(bucket, GoDataStruct):
                    bucket_data = self.__parse_bucket(nest_depth, bucket, 8)
                    if bucket_data is None:
                        valid = False
                        break
                    entries.extend(bucket_data)
                else:
                    valid = False
                    break

            # Empty map case was already handled. So presume bad data if len(entries) == 0.
            if valid and len(entries) > 0:
                heuristic_sum = 0.0
                for key, val in entries:
                    heuristic_sum += key.heuristic
                    heuristic_sum += val.heuristic
                heuristic_avg = heuristic_sum / (2 * len(entries))
                heuristic = (3 * heuristic_avg + confidence) / 4

                extracted = GoDataMap(heuristic=heuristic, entries=entries)

        return extracted

    def parse(self, addr: int, nest_depth: int) -> GoData:
        """
        Extracts data from the header structure of the map. This is the first function to be called to parse a map.

        :param int addr: The memory address (resident in self.proc) to begin unpacking at.
        :param int nest_depth: The further depth allowed when extracting the key and value objects.
        :return GoData: Returns GoDataMap/GoDataUnparsed/GoDataBad depending on the situation.
        """
        extracted: Union[GoData, None] = None

        count = safe_read_unsigned(self.info, addr, self.info.ptr_size)
        log2_of_num_buckets = safe_read_unsigned(self.info, addr + self.info.ptr_size + 1, 1)
        seed = safe_read_unsigned(self.info, addr + self.info.ptr_size + 4, 4)
        buckets = safe_read_unsigned(self.info, addr + self.info.ptr_size + 8, self.info.ptr_size)
        if count is not None and log2_of_num_buckets is not None and seed is not None and buckets is not None:
            seed_bits = f"{seed:032b}"

            confidence = entropy(seed_bits) ** GO_TUNE_ENTROPY_SOFTNESS

            if nest_depth > 0:
                if count > 0:
                    if self.bucket_type is not None:
                        num_buckets = 2**log2_of_num_buckets

                        # To aid in parsing, create a temporary type that is just used to extract
                        # this array of buckets.
                        buckets_type_header = TypeHeader()
                        buckets_type_header.align = self.bucket_type.header.align
                        buckets_type_header.size = self.bucket_type.header.size * num_buckets

                        buckets_type = GoTypeArray(buckets_type_header, self.version)
                        buckets_type.length = num_buckets
                        buckets_type.child_type = self.bucket_type
                        # We'll lose 1 unit of depth in unpacking the array,
                        # and 1 unit in unpacking the bucket structs.
                        # Add 1 to compensate the loss of 2, so we unpack the children at nest_depth - 1.
                        buckets_object = buckets_type.extract_at(self.info, buckets, self.seen_pointers, nest_depth + 1)

                        extracted = self.__parse_bucket_list(nest_depth, buckets_object, confidence)

                else:
                    # No entries in the map.
                    extracted = GoDataMap(heuristic=confidence, entries=[])
            else:
                # Ran out of nest_depth.
                extracted = GoDataUnparsed(heuristic=confidence, address=addr)

        if extracted is None:
            extracted = GoDataBad(heuristic=Confidence.JUNK.to_float())
        return extracted


class SwissMapParser:
    """
    A single-use parser for the new Go "Swiss" map type introduced in version 1.24.
    """

    info: ExtractInfo
    ptr_spec: str
    group_type: GoType

    seen_pointers: set[int]

    def __init__(self, info: ExtractInfo, group_type: GoType, seen: set[int]):
        self.info = info
        self.group_type = group_type
        self.seen_pointers = seen
        if self.info.ptr_size == 4:
            self.ptr_spec = "I"
        else:
            self.ptr_spec = "Q"

    def __unpack_slot(self, slot_obj: GoData) -> Union[tuple[GoData, GoData], None]:
        """
        The structure of the slot struct in a group type is known. Unpack that slot to return the key/value pair.

        :param GoData slot_obj: The unpacked slot object.
        :return Union[tuple[GoData, GoData], None]: A pair of key and value, or None if slot structure did not conform.
        """
        if isinstance(slot_obj, GoDataStruct):
            accesser = dict(slot_obj.fields)
            key_obj = accesser.get("key")
            elem_obj = accesser.get("elem")
            if key_obj is not None and elem_obj is not None:
                return (key_obj, elem_obj)
        return None

    def __parse_group(self, group_ptr: int, nest_depth: int) -> Union[list[tuple[GoData, GoData]], None]:
        """
        Given a pointer to a group (a.k.a. bucket), extract a list of valid entries.

        :param int group_ptr: The base address of the group relative to the address space for self.proc.
        :param int nest_depth: The further depth allowed when extracting the key and value objects.
        :return Union[list[tuple[GoData, GoData]], None]: If parsing succeeded, a list of key/value pairs. Else None.
        """
        from_group: Union[list[tuple[GoData, GoData]], None] = None
        # We lose 1 unit of depth unpacking the group,
        # 1 unit unpacking the slots array and 1 unpacking an individual slot.
        # Add 2 to compensate the loss of 3, so we unpack the children at nest_depth - 1.
        group_obj = self.group_type.extract_at(self.info, group_ptr, self.seen_pointers, nest_depth + 2)

        # Check extracted group has expected structure.
        if isinstance(group_obj, GoDataStruct):
            accesser = dict(group_obj.fields)
            ctrl_obj = accesser.get("ctrl")
            slots_obj = accesser.get("slots")
            if ctrl_obj is not None and slots_obj is not None:
                if isinstance(ctrl_obj, GoDataInteger) and isinstance(slots_obj, GoDataArray):
                    # Go hardcodes 8 as the number of slots in a bucket.
                    # The ctrl field is a uint64, and it consists of 8 packed bytes.
                    if len(slots_obj.contents) == 8:
                        from_group = []
                        # The 0th control byte is stored at the lowest address.
                        # ctrl.value was read as little-endian, so packing little-endian gets the bytes in memory order.
                        ctrl_bytes = ctrl_obj.value.to_bytes(8, "little")
                        for i in range(8):
                            ctrl = ctrl_bytes[i]
                            slot_obj = slots_obj.contents[i]
                            # A slot is full if and only if bit 7 (MSB) is unset in its control byte.
                            if ctrl & 0x80 == 0:
                                # Slot is valid.
                                unpacked = self.__unpack_slot(slot_obj)
                                if unpacked is None:
                                    from_group = None
                                    break
                                from_group.append(unpacked)
        return from_group

    def __parse_table(self, table_ptr: int, nest_depth: int) -> Union[list[tuple[GoData, GoData]], None]:
        """
        Given a pointer to a table (an array of groups), parse them all and concatenate results.

        :param int table_ptr: The base address of the table relative to the address space for self.proc.
        :param int nest_depth: The further depth allowed when extracting the key and value objects.
        :return Union[list[tuple[GoData, GoData]], None]: If parsing succeeded, a list of key/value pairs. Else None.
        """
        from_table: Union[list[tuple[GoData, GoData]], None] = None

        groups_reference_base = table_ptr + 8 + self.info.ptr_size
        # data is a pointer to an array of groups.
        data = safe_read_unsigned(self.info, groups_reference_base, self.info.ptr_size)
        length = safe_read_unsigned(self.info, groups_reference_base + self.info.ptr_size, self.info.ptr_size)

        if data is not None and length is not None:
            from_table = []
            length += 1  # the stored length is the actual length subtract 1.
            group_size = self.group_type.header.size
            for i in range(length):
                from_group = self.__parse_group(data + i * group_size, nest_depth)
                if from_group is None:
                    from_table = None
                    break

                from_table.extend(from_group)

        return from_table

    def parse(self, addr: int, nest_depth: int) -> GoData:
        """
        Extracts data from the header structure of the map. This is the first function to be called to parse a map.

        :param int addr: The memory address (resident in self.proc) to begin unpacking at.
        :param int nest_depth: The further depth allowed when extracting the key and value objects.
        :return GoData: Returns GoDataMap/GoDataUnparsed/GoDataBad depending on the situation.
        """
        extracted: Union[GoData, None] = None

        length = safe_read_unsigned(self.info, addr, 8)
        seed = safe_read_unsigned(self.info, addr + 8, self.info.ptr_size)
        dir_ptr = safe_read_unsigned(self.info, addr + 8 + self.info.ptr_size, self.info.ptr_size)
        dir_len = safe_read_unsigned(self.info, addr + 8 + 2 * self.info.ptr_size, self.info.ptr_size)
        if length is not None and seed is not None and dir_ptr is not None and dir_len is not None:
            seed_bits = f"{seed:064b}"
            if self.info.ptr_size == 4:
                seed_bits = seed_bits[32:]
            confidence = entropy(seed_bits) ** GO_TUNE_ENTROPY_SOFTNESS

            if nest_depth > 0:
                if length > 0:

                    entries: Union[list[tuple[GoData, GoData]], None] = []
                    if dir_len == 0:
                        # Small map type. So dir_ptr points to a group.
                        entries = self.__parse_group(dir_ptr, nest_depth)
                    else:
                        # Regular map type. dir_ptr points to an array of tables.
                        if dir_len > GO_TUNE_MAX_SWISSMAP_DIRS:
                            # This is a very large number of directories: don't parse all of them.
                            dir_len = GO_TUNE_MAX_SWISSMAP_DIRS
                            # We doubt this is actually a map.
                            confidence = 0.0

                        table_array = safe_read_bytes(self.info, dir_ptr, self.info.ptr_size * dir_len)
                        if table_array is not None:
                            for (table_ptr,) in struct.iter_unpack("<" + self.ptr_spec, table_array):
                                from_table = self.__parse_table(table_ptr, nest_depth)
                                if from_table is None:
                                    entries = None
                                    break
                                # The next line is well-typed because if entries is None, then we already broke.
                                entries.extend(from_table)  # type:ignore[union-attr]

                    if entries is not None and len(entries) > 0:
                        # A valid map.
                        heuristic_sum = 0.0
                        for key, val in entries:
                            heuristic_sum += key.heuristic
                            heuristic_sum += val.heuristic
                        heuristic_avg = heuristic_sum / (2 * len(entries))
                        heuristic = (3 * heuristic_avg + confidence) / 4
                        extracted = GoDataMap(heuristic=heuristic, entries=entries)

                else:
                    # Empty map.
                    extracted = GoDataMap(heuristic=confidence, entries=[])
            else:
                # Ran out of depth.
                extracted = GoDataUnparsed(heuristic=confidence, address=addr)

        if extracted is None:
            extracted = GoDataBad(heuristic=Confidence.JUNK.to_float())
        return extracted
