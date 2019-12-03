DOMAIN="bliss.gitlab.esrf.fr"
ADDRESS="https://bliss.gitlab-pages.esrf.fr/bliss"
echo "<!DOCTYPE html>" > public/index.html
echo "<html lang=en>" >> public/index.html
echo "<head><title>Bliss Versions</title><h1>Bliss</h1></head>" >> public/index.html
echo "<body>" >> public/index.html

for bliss_tag in $@
do
    echo "LOOKING FOR $bliss_tag"
    wget --recursive --page-requisites --html-extension --convert-links --cut-dirs=1 --no-parent --no-host-directories "$ADDRESS/$bliss_tag/" -P ./public
    test -e ./public/$bliss_tag && echo "<ul><a href=\"./$bliss_tag/index.html\">$bliss_tag</a></ul>" >> public/index.html
done
echo "</body>" >> public/index.html
echo "</html>" >> public/index.html
