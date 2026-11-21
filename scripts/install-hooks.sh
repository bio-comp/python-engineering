#!/bin/sh
# Install the two repository-native hooks without replacing existing custom hooks.
set -eu
root=$(git rev-parse --show-toplevel)
cd "$root"
if [ -n "$(git config --get core.hooksPath || true)" ]; then
    echo 'Existing core.hooksPath: refusing to replace' >&2
    exit 1
fi
hooks=$(git rev-parse --git-path hooks)
mkdir -p "$hooks"
for stage in pre-commit pre-push; do
    target="$hooks/$stage"
    if [ -e "$target" ] || [ -L "$target" ]; then
        echo "Existing hook $target: refusing to replace" >&2
        exit 1
    fi
done
for stage in pre-commit pre-push; do
    ln -s "../../scripts/$stage.py" "$hooks/$stage"
done
echo 'Installed native Git hooks for staged Ruff and outgoing-ref verification'
