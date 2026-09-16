from ase.calculators.vasp import Vasp as _Vasp  # type: ignore
from ase.calculators.vasp.create_input import (  # type: ignore
    float_keys,
    exp_keys,
    string_keys,
    int_keys,
    bool_keys,
    list_bool_keys,
    _from_vasp_bool,
    _args_without_comment,
    list_int_keys,
    list_float_keys,
    special_keys,
)
import numpy as np


class Vasp(_Vasp):
    """Subclass of ASE Vasp calculator with fixed read_incar method."""

    def read_incar(self, filename):
        """Method that imports settings from INCAR file.

        This is a modified version of the original read_incar method from ASE Vasp calculator.
        It fixes an issue where the original method fails to read certain lines in the INCAR file,
        such as comments that does not start with "#" or "!".

        Note that this still does not cover all formating options: https://www.vasp.at/wiki/INCAR
        """

        self.spinpol = False
        # START OF FIX: Use errors='ignore' to skip lines that cannot be decoded,
        # instead of crashing with UnicodeDecodeError.
        # They problem seems to be some files with encoding='latin-1'.
        # with open(filename) as fd:
        #     lines = fd.readlines()
        with open(filename, errors="ignore") as fd:
            lines = fd.readlines()
        # try:
        #     with open(filename, encoding='utf-8') as fd:
        #         lines = fd.readlines()
        # except UnicodeDecodeError:
        #     with open(filename, encoding='latin-1') as fd:
        #         lines = fd.readlines()
        # END OF FIX

        for line in lines:
            try:
                # Make multiplication, comments, and parameters easier to spot
                line = line.replace("*", " * ")
                line = line.replace("=", " = ")
                line = line.replace("#", "# ")
                data = line.split()
                # Skip empty and commented lines.
                if len(data) == 0:
                    continue
                elif data[0][0] in ["#", "!"]:
                    continue
                # START OF FIX: Skip lines that do not have the expected format of "key = value(s)"
                elif len(data) < 2 or data[1][0] != "=":
                    continue
                # END OF FIX
                key = data[0].lower()
                if "<Custom ASE key>" in line:
                    # This key was added with custom key-value pair formatting.
                    # Unconditionally add it, no type checking
                    # Get value between "=" and the comment, e.g.
                    # key = 1 2 3  # <Custom ASE key>
                    # value should be '1 2 3'

                    # Split at first occurence of "="
                    value = line.split("=", 1)[1]
                    # First "#" denotes beginning of comment
                    # Add everything before comment as a string to custom dict
                    value = value.split("#", 1)[0].strip()
                    self.input_params["custom"][key] = value
                elif key in float_keys:
                    self.float_params[key] = float(data[2])
                elif key in exp_keys:
                    self.exp_params[key] = float(data[2])
                elif key in string_keys:
                    self.string_params[key] = str(data[2])
                elif key in int_keys:
                    if key == "ispin":
                        # JRK added. not sure why we would want to leave ispin
                        # out
                        self.int_params[key] = int(data[2])
                        if int(data[2]) == 2:
                            self.spinpol = True
                    else:
                        self.int_params[key] = int(data[2])
                elif key in bool_keys:
                    val_char = data[2].lower().replace(".", "", 1)
                    if val_char.startswith("t"):
                        self.bool_params[key] = True
                    elif val_char.startswith("f"):
                        self.bool_params[key] = False
                    else:
                        raise ValueError(f'Invalid value "{data[2]}" for bool key "{key}"')

                elif key in list_bool_keys:
                    self.list_bool_params[key] = [
                        _from_vasp_bool(x) for x in _args_without_comment(data[2:])
                    ]

                elif key in list_int_keys:
                    self.list_int_params[key] = [int(x) for x in _args_without_comment(data[2:])]

                elif key in list_float_keys:
                    if key == "magmom":
                        lst = []
                        i = 2
                        while i < len(data):
                            if data[i] in ["#", "!"]:
                                break
                            if data[i] == "*":
                                b = lst.pop()
                                i += 1
                                for _ in range(int(b)):
                                    lst.append(float(data[i]))
                            else:
                                lst.append(float(data[i]))
                            i += 1
                        self.list_float_params["magmom"] = lst
                        lst = np.array(lst)
                        if self.atoms is not None:
                            self.atoms.set_initial_magnetic_moments(lst[self.resort])
                    else:
                        data = _args_without_comment(data)
                        self.list_float_params[key] = [float(x) for x in data[2:]]
                elif key in special_keys:
                    if key == "lreal":
                        val_char = data[2].lower().replace(".", "", 1)
                        if val_char.startswith("t"):
                            self.bool_params[key] = True
                        elif val_char.startswith("f"):
                            self.bool_params[key] = False
                        else:
                            self.special_params[key] = data[2]

                # non-registered keys
                elif data[2].lower() in {"t", "true", ".true."}:
                    self.bool_params[key] = True
                elif data[2].lower() in {"f", "false", ".false."}:
                    self.bool_params[key] = False
                elif data[2].isdigit():
                    self.int_params[key] = int(data[2])
                else:
                    try:
                        self.float_params[key] = float(data[2])
                    except ValueError:
                        self.string_params[key] = data[2]

            except KeyError as exc:
                raise KeyError(f'Keyword "{key}" in INCAR is not known by calculator.') from exc
            except IndexError as exc:
                raise IndexError(f'Value missing for keyword "{key}".') from exc
