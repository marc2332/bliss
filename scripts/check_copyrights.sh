




# To find problematic lines:
find ./ -name "*~" | xargs rm
grep -inr --exclude-dir="scripts/" copyright | grep -v .git | grep -v .xmi | grep -v "2015-2019" | grep -v footer  | grep ESRF


