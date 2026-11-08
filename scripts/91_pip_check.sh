#!/usr/bin/env bash
# Can we get pip / richer deps in WSL? (network was confirmed earlier)
set -uo pipefail
echo "############ apt candidates ############"
apt-cache policy python3-pip 2>/dev/null | head -6 | sed 's/^/  /'
echo
echo "############ try installing pip (fast path) ############"
timeout 180 apt-get install -y -q python3-pip 2>&1 | tail -5 | sed 's/^/  /'
echo
echo "############ pip now? ############"
python3 -m pip --version 2>&1 | sed 's/^/  /'
