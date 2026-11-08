#!/bin/bash
# 从 netchop 二进制里找版本串
B=/opt/bio/netchop-3.1/Linux_x86_64/bin/netChop
echo "--- strings | grep -i 'netchop\|version\|3\.1'"
strings -a "$B" 2>/dev/null | grep -iE 'netchop|version|3\.1' | sort -u | head -30
echo
echo "--- launcher 里的版本提示"
grep -niE 'version|3\.1|release' /opt/bio/netchop-3.1/netchop | head -20
echo
echo "--- data/ 下所有文件名（含版本线索）"
find /opt/bio/netchop-3.1 -maxdepth 2 | head -40
echo
echo "--- etc/ 内容"
ls -la /opt/bio/netchop-3.1/etc 2>/dev/null
cat /opt/bio/netchop-3.1/etc/* 2>/dev/null | head -20
