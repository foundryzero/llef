#!/bin/bash

install () {
    echo "command script import \"$( dirname -- "$( readlink -f -- "$0"; )"; )/llef.py\"" > $HOME/.lldbinit;
    echo "settings set stop-disassembly-display never" >> $HOME/.lldbinit;

    while true; do
        read -p "LLDB uses AT&T disassembly syntax for x86 binaries would you like to force intel syntax? [y/n] " yn
        case $yn in
            [Yy]* ) echo "settings set target.x86-disassembly-flavor intel" >> $HOME/.lldbinit; break;;
            [Nn]* ) exit ; break;;
            * ) echo "Please answer 'y' or 'n'.";;
        esac
    done
}

manualinstall () {
    echo "Paste these lines into ~/.lldbinit";
    echo "";
    echo "command script import \"$( dirname -- "$( readlink -f -- "$0"; )"; )/llef.py\"";
    echo "settings set stop-disassembly-display never";
    echo "";
    echo "Optionally include the following line to use intel disassembly syntax for x86 binaries rather than AT&T";
    echo "";
    echo "settings set target.x86-disassembly-flavor intel";
}

while true; do
    read -p "Automatic install will overwrite $HOME/.lldbinit - Enter 'y' continue or 'n' to view manual instructions? [y/n] " yn
    case $yn in
        [Yy]* ) install; break;;
        [Nn]* ) manualinstall; break;;
        * ) echo "Please answer 'y' or 'n'.";;
    esac
done

