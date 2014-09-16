#!/bin/bash

# This pre-commit script ensures that a user.name has been defined in
# local git config.

# Takes first 8 characters of git user.name
USER_NAME=`git config --get user.name`
CUT_USER_NAME=$(echo $USER_NAME | cut -b1-8)

# If user.name starts with "blissadm" -> error
if [ "$CUT_USER_NAME" == "blissadm" ]; then
    echo "ERROR : GIT not configured for EMotion commit"
    echo "        user.name == $USER.NAME"
    echo "  please use :"
    echo "       git sig <yourname> "
    echo "  to change the commit signature."
    exit 1
else
    MESSAGE="ok to commit in EMotion as \"$USER_NAME\" ? (press enter or ctrl-C)"
    exec < /dev/tty
    read -p "$MESSAGE"
    exit 0
fi
