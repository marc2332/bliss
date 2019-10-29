#!/bin/sh

echo "Optimize a list of SVG files"
echo "The original files will be lost (but now it's too late)"

exec_script()
{
    scour_options=--enable-viewboxing --enable-id-stripping --enable-comment-stripping --shorten-ids --nindent=0 --indent=none --remove-metadata --disable-embed-rasters

    for filename in "$@"
    do
        echo "Optimize $filename"
        scour -i $filename -o "${filename}__scour" $scour_options
        rm $filename
        mv "${filename}__scour" $filename
    done
}

if [ $# -eq 0 ]
then
    exec_script `find bliss/flint/resources/icons | grep .svg`
else
    exec_script $@
fi
