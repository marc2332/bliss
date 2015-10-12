# Install

## virtualenv

<pre><code>
$ # construct and activate a new virtual environment:
$ # (if you are using an old virtualenv just ommit --system-site-packages option)
$ virtualenv --system-site-packages <your env. name>
$ . <your env. name>/bin/activate

$ # make sure we have latest pip:
$ python -m pip install pip --upgrade

$ # install beacon requirements:
$ # change to the beacon directory
$ python -m pip install -r requirements.txt
</code></pre>