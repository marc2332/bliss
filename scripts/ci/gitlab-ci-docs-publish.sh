ADDRESS="https://bliss.gitlab-pages.esrf.fr/bliss"

cp scripts/ci/doc-index-template.html public/index.html

version_links=""

for bliss_tag in $@
do
    echo "LOOKING FOR $bliss_tag"
    # older published versions are not accessible via filesystem, must redownload them
    wget --recursive --page-requisites --html-extension --convert-links --cut-dirs=1 --no-parent --no-host-directories "$ADDRESS/$bliss_tag/" -P ./public
    
    # also download search index for the search bar to work
    wget "$ADDRESS/$bliss_tag/search/search_index.json" -P ./public/$bliss_tag/search/

    if [ -e ./public/$bliss_tag ]; then
        version_links=$version_links"<li><a href=\"$bliss_tag/\">$bliss_tag</a></li>\n"
    fi
done

sed -i "s|TEXT_TO_BE_REPLACED|${version_links}|" public/index.html
