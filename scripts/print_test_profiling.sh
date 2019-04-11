#!/bin/sh
echo ""
echo ""
echo "========================== profiler statistics ==========================="
echo ""
head -n4 prof/combined.txt 
echo ""
echo "========================== most time consuming (top 30) ==========================="
echo ""
head -n7 prof/combined.txt |tail -n 1
cat prof/combined.txt | grep '/bliss/' | sort -g -rk4 | head -n 30
echo ""
echo ""
echo "========================== most time consuming per call (top 30) ==========================="
echo ""
head -n7 prof/combined.txt |tail -n 1
cat prof/combined.txt | grep '/bliss/bliss/bliss/' | sort -g -rk5 | head -n 30

