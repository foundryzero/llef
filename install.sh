#!/bin/bash

install () {
    echo "command script import \"$( dirname -- "$( readlink -f -- "$0"; )"; )/llef.py\"" > $HOME/.lldbinit;
    echo "settings set stop-disassembly-display never" >> $HOME/.lldbinit;
}

manualinstall () {
    echo "Paste these lines into ~/.lldbinit";
    echo "";
    echo "command script import \"$( dirname -- "$( readlink -f -- "$0"; )"; )/llef.py\"";
    echo "settings set stop-disassembly-display never";
}

while true; do
    read -p "Automatic install will overwrite $HOME/.lldbinit - Enter 'y' continue or 'n' to view manual instructions? " yn
    case $yn in
        [Yy]* ) install; break;;
        [Nn]* ) manualinstall; break;;
        * ) echo "Please answer yes or no.";;
    esac
done

