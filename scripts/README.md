### Use scripts

##### To bump version of all packages run
WIN: .\bump_version.ps1 major || minor || patch
LINUX: ./bump_version.sh major || minor || patch

##### To build all packages run
WIN: .\build_all.ps1
LINUX: ./build_all.sh

##### To publish all to pypi
WIN: .\publish_all.ps1
LINUX: ./publish_all.sh
