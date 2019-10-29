#!/bin/sh

echo "Export a list of SVG files into PNG files"
echo "The 'svg' extension is automatically replaced by 'png'"

exec_script()
{
    for filename in "$@"
    do
        echo "Export $filename"
        png_filename="$(dirname "$filename")/$(basename "$filename" .svg).png"
        inkscape --file="${filename}" --export-png=${png_filename} --export-area-page
    done
}

if [ $# -eq 0 ]
then
    exec_script `find bliss/flint/resources/icons | grep .svg`
else
    exec_script $@
fi
