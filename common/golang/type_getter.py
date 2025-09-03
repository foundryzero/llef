"""A utility class that parses type names into corresponding structures."""

import math
from dataclasses import dataclass
from typing import Union

from common.golang.types import (
    GoType,
    GoTypeArray,
    GoTypeBool,
    GoTypeComplex64,
    GoTypeComplex128,
    GoTypeFloat32,
    GoTypeFloat64,
    GoTypeInt,
    GoTypeInt8,
    GoTypeInt16,
    GoTypeInt32,
    GoTypeInt64,
    GoTypeMap,
    GoTypePointer,
    GoTypeSlice,
    GoTypeString,
    GoTypeStruct,
    GoTypeStructField,
    GoTypeUint,
    GoTypeUint8,
    GoTypeUint16,
    GoTypeUint32,
    GoTypeUint64,
    GoTypeUintptr,
    GoTypeUnsafePointer,
    TypeHeader,
)
from common.state import LLEFState


@dataclass(frozen=True)
class SimpleType:
    """
    SimpleType represents information about a unit type, such as int/bool/unsafe.Pointer.
    """

    go_type: type[GoType]
    size: int
    alignment: int


class TypeGetter:
    """
    TypeGetter is a parser that turns type names into the corresponding structures. It's used when a user-provided type
    does not exactly match any of those present in the runtime, so we attempt to construct it from scratch.
    """

    __version: tuple[int, int]
    __ptr_size: int
    __name_to_type: dict[str, GoType]

    __simple_map: dict[str, SimpleType]

    def __slice_to_type(self, slice_repr: str) -> Union[GoTypeSlice, None]:
        """
        Parses the string representation of a Go slice type. The string must start with "[]".

        :param slice_repr str: The string representation of a Go slice type.
        :return Union[GoTypeSlice, None]: Returns a GoTypeSlice if the provided string is valid, otherwise None.
        """
        resolved: Union[GoTypeSlice, None] = None
        elem_type = self.string_to_type(slice_repr[2:])
        if elem_type is not None:
            header = TypeHeader()
            header.align = self.__ptr_size

            # Slices store three ints: base address, length, capacity.
            header.size = 3 * self.__ptr_size
            resolved = GoTypeSlice(header=header, version=self.__version)
            resolved.child_type = elem_type

        return resolved

    def __array_to_type(self, array_repr: str) -> Union[GoTypeArray, None]:
        """
        Parses the string representation of a Go array type. The string must start with "[N]", where N is a number.

        :param array_repr str: The string representation of a Go array type.
        :return Union[GoTypeArray, None]: Returns a GoTypeArray if the provided string is valid, otherwise None.
        """
        resolved: Union[GoTypeArray, None] = None
        partitioned = array_repr[1:].split("]", maxsplit=1)
        if len(partitioned) == 2:
            [length_string, elem_string] = partitioned

            valid_length = True
            length = 0
            try:
                length = int(length_string, base=0)
            except ValueError:
                valid_length = False

            if valid_length:
                elem_type = self.string_to_type(elem_string)
                if elem_type is not None:
                    header = TypeHeader()
                    header.align = elem_type.header.align
                    rounded_size = ((elem_type.header.size + header.align - 1) // header.align) * header.align
                    header.size = length * rounded_size
                    resolved = GoTypeArray(header=header, version=self.__version)
                    resolved.length = length
                    resolved.child_type = elem_type
        return resolved

    def __pointer_to_type(self, pointer_repr: str) -> Union[GoTypePointer, None]:
        """
        Parses the string representation of a Go pointer type. The string must start with "*".

        :param pointer_repr str: The string representation of a Go pointer type.
        :return Union[GoTypePointer, None]: Returns a GoTypePointer if the provided string is valid, otherwise None.
        """
        resolved: Union[GoTypePointer, None] = None
        deref_type = self.string_to_type(pointer_repr[1:])
        if deref_type is not None:
            header = TypeHeader()
            header.align = self.__ptr_size
            header.size = self.__ptr_size
            resolved = GoTypePointer(header=header, version=self.__version)
            resolved.child_type = deref_type
        return resolved

    def __struct_to_type(self, struct_repr: str) -> Union[GoTypeStruct, None]:
        """
        Parses the string representation of a Go struct type. The string must start with "struct".

        :param struct_repr str: The string representation of a Go struct type.
        :return Union[GoTypeStruct, None]: Returns a GoTypeStruct if the provided string is valid, otherwise None.
        """
        resolved: Union[GoTypeStruct, None] = None
        body = struct_repr[6:].strip()
        if body.startswith("{") and body.endswith("}"):
            body = body[1:-1].strip()

            valid = True
            field_list: list[GoTypeStructField] = []

            # Track level of {} nestedness.
            level = 0
            field_string = ""
            fields = []
            for char in body:
                if level == 0 and char == ";":
                    fields.append(field_string)
                    field_string = ""
                else:
                    field_string += char
                    if char == "{":
                        level += 1
                    elif char == "}":
                        level -= 1
            if len(field_string) > 0:
                fields.append(field_string)

            offset = 0
            alignment = 1
            for field in fields:
                partitioned = field.strip().split(" ", maxsplit=1)
                if len(partitioned) == 2:
                    [name, field_string] = partitioned
                    field_type = self.string_to_type(field_string)
                    if field_type is not None:
                        alignment = math.lcm(alignment, field_type.header.align)
                        # pad until the field can live in the struct
                        while offset % field_type.header.align != 0:
                            offset += 1

                        struct_field = GoTypeStructField(offset=offset, name=name, type_addr=0)
                        offset += field_type.header.size
                        struct_field.type = field_type
                        field_list.append(struct_field)

                    else:
                        valid = False
                        break
                else:
                    valid = False
                    break

            if valid:
                header = TypeHeader()
                header.align = alignment
                header.size = offset
                resolved = GoTypeStruct(header=header, version=self.__version)
                resolved.fields = field_list
        return resolved

    def __map_to_type(self, map_repr: str) -> Union[GoTypeMap, None]:
        """
        Parses the string representation of a Go map type. The string must start with "map[".

        :param map_repr str: The string representation of a Go map type.
        :return Union[GoTypeMap, None]: Returns a GoTypeMap if the provided string is valid, otherwise None.
        """
        resolved: Union[GoTypeMap, None] = None
        body = map_repr[4:]
        # Track level of [] nestedness.
        level = 1

        i = 0
        while i < len(body):
            if body[i] == "[":
                level += 1
            elif body[i] == "]":
                level -= 1
            if level == 0:
                break
            i += 1

        if i < len(body) - 1:
            key_string = body[:i]
            val_string = body[i + 1 :]
            key_type = self.string_to_type(key_string)
            val_type = self.string_to_type(val_string)
            if key_type is not None and val_type is not None:
                header = TypeHeader()
                header.align = self.__ptr_size
                header.size = self.__ptr_size
                resolved = GoTypeMap(header=header, version=self.__version)
                resolved.key_type = key_type
                resolved.child_type = val_type

                (go_min_version, _) = self.__version
                if go_min_version < 24:
                    # Old map type.
                    bucket_str = (
                        f"struct {{ topbits [8]uint8; keys [8]{key_string}; "
                        f"elems [8]{val_string}; overflow uintptr }}"
                    )
                else:
                    # New (Swiss) map type.
                    bucket_str = f"struct {{ ctrl uint64; slots [8]struct {{ key {key_string}; elem {val_string} }} }}"
                resolved.bucket_type = self.string_to_type(bucket_str)
        return resolved

    def __construct_from_simple(self, simple_type: SimpleType) -> GoType:
        """
        Converts an entry in the simple map into an actual GoType.

        :param SimpleType simple_triple: The type, size and alignment.
        :return GoType: A GoType with the provided characteristics.
        """
        header = TypeHeader()
        header.align = simple_type.alignment
        header.size = simple_type.size
        return simple_type.go_type(header=header, version=self.__version)

    def string_to_type(self, type_repr: str) -> Union[GoType, None]:
        """
        Parses the string representation of any Go type.
        This is not a fully-compliant parser: for example, do not use characters such as "{}[];" in struct field names.

        :param type_repr str: The string representation of a Go type.
        :return Union[GoType, None]: Returns a GoType object if the provided string is valid, otherwise None.
        """

        resolved: Union[GoType, None] = None

        if LLEFState.go_state.moduledata_info is not None:
            # First check if easily available from the binary:
            resolved = self.__name_to_type.get(type_repr)
            if resolved is None:
                # If not, parse it ourselves.

                simple_triple = self.__simple_map.get(type_repr)
                if simple_triple is not None:
                    # Simple data types.
                    resolved = self.__construct_from_simple(simple_triple)

                else:
                    # Complex data types.
                    if type_repr.startswith("[]"):
                        resolved = self.__slice_to_type(type_repr)

                    elif type_repr.startswith("["):
                        resolved = self.__array_to_type(type_repr)

                    elif type_repr.startswith("*"):
                        resolved = self.__pointer_to_type(type_repr)

                    elif type_repr.startswith("struct"):
                        resolved = self.__struct_to_type(type_repr)

                    elif type_repr.startswith("map["):
                        resolved = self.__map_to_type(type_repr)

                    elif type_repr.startswith("func") or type_repr.startswith("chan"):
                        # We don't unpack these types, so just leave them as raw pointers.
                        resolved = self.__construct_from_simple(self.__simple_map["uintptr"])

                    elif type_repr.startswith("interface"):
                        pass

        return resolved

    def __init__(self, type_structs: dict[int, GoType]) -> None:
        """
        Set up internal state, such as the map from type names to types.

        :param dict[int, GoType] type_structs: The type_structs object from moduledata_info.
        """
        self.__version = LLEFState.go_state.pclntab_info.version_bounds
        self.__ptr_size = LLEFState.go_state.pclntab_info.ptr_size
        self.__name_to_type: dict[str, GoType] = {}
        for go_type in type_structs.values():
            self.__name_to_type[go_type.header.name] = go_type

        self.__simple_map = {
            "bool": SimpleType(go_type=GoTypeBool, size=1, alignment=1),
            "complex64": SimpleType(go_type=GoTypeComplex64, size=8, alignment=4),
            "complex128": SimpleType(go_type=GoTypeComplex128, size=16, alignment=8),
            "float32": SimpleType(go_type=GoTypeFloat32, size=4, alignment=4),
            "float64": SimpleType(go_type=GoTypeFloat64, size=8, alignment=8),
            "int": SimpleType(go_type=GoTypeInt, size=self.__ptr_size, alignment=self.__ptr_size),
            "int8": SimpleType(go_type=GoTypeInt8, size=1, alignment=1),
            "int16": SimpleType(go_type=GoTypeInt16, size=2, alignment=2),
            "int32": SimpleType(go_type=GoTypeInt32, size=4, alignment=4),
            "int64": SimpleType(go_type=GoTypeInt64, size=8, alignment=8),
            "uint": SimpleType(go_type=GoTypeUint, size=self.__ptr_size, alignment=self.__ptr_size),
            "uint8": SimpleType(go_type=GoTypeUint8, size=1, alignment=1),
            "uint16": SimpleType(go_type=GoTypeUint16, size=2, alignment=2),
            "uint32": SimpleType(go_type=GoTypeUint32, size=4, alignment=4),
            "uint64": SimpleType(go_type=GoTypeUint64, size=8, alignment=8),
            "string": SimpleType(go_type=GoTypeString, size=self.__ptr_size * 2, alignment=self.__ptr_size),
            "uintptr": SimpleType(go_type=GoTypeUintptr, size=self.__ptr_size, alignment=self.__ptr_size),
            "unsafe.Pointer": SimpleType(go_type=GoTypeUnsafePointer, size=self.__ptr_size, alignment=self.__ptr_size),
        }
