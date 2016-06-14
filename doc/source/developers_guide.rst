.. _bliss-developers-guide:

Developer's Guide
=================

Bliss development is powered by git_. The project is hosted on the
`ESRF Gitlab`_.

.. _bliss-develop-quick-start:

Quick Start
-----------

To clone bliss::

    git clone git@gitlab.esrf.fr:bliss/bliss.git

... or you can always download the latest
`tar.gz <http://gitlab.esrf.fr/bliss/bliss/repository/archive.tar.gz>`_,
`tar.bz2 <http://gitlab.esrf.fr/bliss/bliss/repository/archive.tar.bz2>`_ or
`zip <http://gitlab.esrf.fr/bliss/bliss/repository/archive.zip>`_.

Bliss has some dependencies on third-party software. The complete list of
dependencies can be found in the
`requirements <http://gitlab.esrf.fr/bliss/bliss/blob/master/requirements.txt>`_
file.

Your work environment is a matter of taste. If you want to isolate your bliss
development it is a good idea to use virtualenv. The bliss project proposes
pew_ which is a tool to manage multiple virtual environments.

Here is a quick recipe on how to start::

    pew new bliss_dev
    pip install -U pip               # python 2.6 needs to upgrade pip
    pip install -r requirements.txt

Next time you open a console to work on bliss simply do::

    pew workon bliss_dev

When you start developing inside bliss you will want to test your code. There
are several options:

1. before each test, reinstall bliss with::

     python setup.py install

2. add your <bliss root dir>/bliss to the PYTHONPATH environment variable

3. figure out where virtualenv site-packages directory is and create a symbolic
   link there to <bliss root dir>/bliss

Workflow
--------

Bliss project promotes a development based on `Feature Branch Workflow`_:

    The core idea behind the `Feature Branch Workflow`_ is that all feature
    development should take place in a dedicated branch instead of the master
    branch. This encapsulation makes it easy for multiple developers to work
    on a particular feature without disturbing the main codebase. It also means
    **the master branch will never contain broken code**, which is a huge
    advantage for continuous integration environments.

    Encapsulating feature development also makes it possible to leverage pull
    requests, which are a way to initiate discussions around a branch. They give
    other developers the opportunity to sign off on a feature before it gets
    integrated into the official project. Or, if you get stuck in the middle of
    a feature, you can open a pull request asking for suggestions from your
    colleagues. The point is, pull requests make it incredibly easy for your
    team to comment on each other’s work.


Use case story 1: Adding a new controller
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

John has been asked by beamline ID00 to integrate a new pressure meter from
Alibaba Inc, in their experiments.

* First, he checks the :mod:`~bliss.controllers` repository to see if the
  device is already implemented

* If not, he creates a new
  `issue <http://gitlab.esrf.fr/bliss/bliss/issues/new?issue>`_ on gitlab.
  He assigns it to himself and adds labels *new feature* and *plugin*.
  He is very happy to receive a comment by his colleague Maria that happened
  to receive a similar request from ID99. They quickly agree on a shared
  development

* They both agree to work on a new branch called *alibaba_pressure_meter*.
  Since John is going on vacation, it is up to poor Maria to start developing

* She clones the Bliss repository (see :ref:`bliss-develop-quick-start`)
  and creates a new branch called *alibaba_pressure_meter*::

    git checkout -b alibaba_pressure_meter

* She is a fan of :term:`TDD`, so she starts thinking how she would like
  to control the device and then she starts writing simple unit tests.
  They will all fail in the beginning but that doesn't scare her at all
  because now she knows exactly what to do to make them work

* After some development, Maria is happy with the result so she pushes her
  work to gitlab. She can immediately see on the Bliss `ESRF Gitlab`_
  project page a new log entry with the work she just pushed.
  Gitlab even offers to create a *merge request* so she just clicks on
  it, fills in the missing data in the form and assigns her colleague
  Marco to integrate her merge request. Maria is quite confident because
  she knows that an extra pair of eyes will help catch any issue with her
  proposition

* Marco makes some comments on Maria's code directly on the gitlab merge
  request web page. Maria realizes that she forgot to document one of the
  most important methods so she fixes the commit. Marco can now accept
  the merge request

* John comes back from vacation and he is suprised to see the code for
  his device is already available in the master branch. Since his use case
  is a little different that Maria's, he realizes that he needs to add a
  couple more functions so he makes a new
  `issue <http://gitlab.esrf.fr/bliss/bliss/issues/new?issue>`_ on gitlab
  and the process repeats again


Contributing
------------

You can contribute to Bliss in many ways: from simple (or hard) bug fixes to
writting new controller extensions, introduce new features or writing
documentation. No matter how you are contributing, the following principles
apply:

* Try to use the same code style as used in the rest of the project. See
  the :ref:`bliss-style-guide` below for more information

* New features should be documented. Include examples and use cases where
  appropriate

* Add appropriate unit tests


Bliss Module Template
---------------------

Here is a template that you can use to start writing a new bliss module::

    # -*- coding: utf-8 -*-
    #
    # This file is part of the bliss project
    #
    # Copyright (c) 2016 Beamline Control Unit, ESRF
    # Distributed under the GNU LGPLv3. See LICENSE for more info.

    """A brief description goes here.

    Long description here with examples if possible

    If you have submodules document them here with autosummary:

    .. autosummary::
        :nosignatures:
        :toctree:

        module1
        module2
    """

    __all__ = [] # list of members to export

    # standard module imports

    # third-party module imports

    # local bliss imports


Example of a motor controller extension::

    # -*- coding: utf-8 -*-
    #
    # This file is part of the bliss project
    #
    # Copyright (c) 2016 Beamline Control Unit, ESRF
    # Distributed under the GNU LGPLv3. See LICENSE for more info.

    """IcePAP motor controller

    To instantiate a new IcePAP motor controller, configure it with::

        plugin: emotion
        class: IcePAP
        host: iceid00a
        axes:
          - name: th
            address: 01
            unit: deg
            steps_per_unit: 1
            velocity: 0        # unit/s
            acceleration: 0    # unit/s/s
            backlash:          # unit

    ... and so on and so forth

    .. autosummary::
        :nosignatures:
        :toctree:

        libicepap
    """

    __all__ = ['IcePAP']

    import os
    import sys
    import string

    import gevent

    from bliss.controllers.motor import Controller


    class IcePAP(Controller):
        '''The IcePAP motor controller'''

        pass

.. _bliss-style-guide:

Bliss Style Guide
-----------------

The Bliss style guide summarizes the Bliss coding guide lines. When adding
code to Bliss (new feature, new extension or simply a patch) make sure you
follow these guide lines.

In general the Bliss Style Guide closely follows :pep:`8` with some small
differences and extensions.

General Layout
--------------

Indentation:
  4 real spaces.  No tabs, no exceptions.

Maximum line length:
  79 characters with a soft limit for 84 if absolutely necessary.  Try
  to avoid too nested code by cleverly placing `break`, `continue` and
  `return` statements.

Continuing long statements:
  To continue a statement you can use backslashes in which case you should
  align the next line with the last dot or equal sign, or indent four
  spaces::

    this_is_a_very_long(function_call, 'with many parameters') \
        .that_returns_an_object_with_an_attribute

    MyModel.query.filter(MyModel.scalar > 120) \
                 .order_by(MyModel.name.desc()) \
                 .limit(10)

  If you break in a statement with parentheses or braces, align to the
  braces::

    this_is_a_very_long(function_call, 'with many parameters',
                        23, 42, 'and even more')

  For lists or tuples with many items, break immediately after the
  opening brace::

    items = [
        'this is the first', 'set of items', 'with more items',
        'to come in this line', 'like this'
    ]

Blank lines:
  Top level functions and classes are separated by two lines, everything
  else by one.  Do not use too many blank lines to separate logical
  segments in code.  Example::

    def hello(name):
        print 'Hello %s!' % name


    def goodbye(name):
        print 'See you %s.' % name


    class MyClass(object):
        """This is a simple docstring"""

        def __init__(self, name):
            self.name = name

        def get_annoying_name(self):
            return self.name.upper() + '!!!!111'

Expressions and Statements
--------------------------

General whitespace rules:
  - No whitespace for unary operators that are not words
    (e.g.: ``-``, ``~`` etc.) as well on the inner side of parentheses.
  - Whitespace is placed between binary operators.

  Good::

    exp = -1.05
    value = (item_value / item_count) * offset / exp
    value = my_list[index]
    value = my_dict['key']

  Bad::

    exp = - 1.05
    value = ( item_value / item_count ) * offset / exp
    value = (item_value/item_count)*offset/exp
    value=( item_value/item_count ) * offset/exp
    value = my_list[ index ]
    value = my_dict ['key']

Yoda statements are a no-go:
  Never compare constant with variable, always variable with constant:

  Good::

    if method == 'md5':
        pass

  Bad::

    if 'md5' == method:
        pass

Comparisons:
  - against arbitrary types: ``==`` and ``!=``
  - against singletons with ``is`` and ``is not`` (eg: ``foo is not
    None``)
  - never compare something with ``True`` or ``False`` (for example never
    do ``foo == False``, do ``not foo`` instead)

Negated containment checks:
  use ``foo not in bar`` instead of ``not foo in bar``

Instance checks:
  ``isinstance(a, C)`` instead of ``type(A) is C``, but try to avoid
  instance checks in general.  Check for features.


Naming Conventions
------------------

- Class names: ``CamelCase``, with acronyms kept uppercase (``HTTPWriter``
  and not ``HttpWriter``)
- Variable names: ``lowercase_with_underscores``
- Method and function names: ``lowercase_with_underscores``
- Constants: ``UPPERCASE_WITH_UNDERSCORES``
- precompiled regular expressions: ``name_re``

Protected members are prefixed with a single underscore.  Double
underscores are reserved for mixin classes.

On classes with keywords, trailing underscores are appended.  Clashes with
builtins are allowed and **must not** be resolved by appending an
underline to the variable name.  If the function needs to access a
shadowed builtin, rebind the builtin to a different name instead.

Function and method arguments:
  - class methods: ``cls`` as first parameter
  - instance methods: ``self`` as first parameter
  - lambdas for properties might have the first parameter replaced
    with ``x`` like in ``display_name = property(lambda x: x.real_name
    or x.username)``


Docstrings
----------

Docstring conventions:
  All docstrings are formatted with reStructuredText as understood by
  Sphinx.  Depending on the number of lines in the docstring, they are
  laid out differently.  If it's just one line, the closing triple
  quote is on the same line as the opening, otherwise the text is on
  the same line as the opening quote and the triple quote that closes
  the string on its own line::

    def foo():
        """This is a simple docstring"""


    def bar():
        """This is a longer docstring with so much information in there
        that it spans three lines.  In this case the closing triple quote
        is on its own line.
        """

Module header:
  The module header consists of an utf-8 encoding declaration (if non
  ASCII letters are used, but it is recommended all the time) and a
  standard docstring::

    # -*- coding: utf-8 -*-
    #
    # This file is part of the bliss project
    #
    # Copyright (c) 2016 Beamline Control Unit, ESRF
    # Distributed under the GNU LGPLv3. See LICENSE for more info.

    """A brief description goes here.

    Long description here with examples if possible

    If you have submodules document them here with autosummary:

    .. autosummary::
        :nosignatures:
        :toctree:

        module1
        module2
    """


Comments
--------

Rules for comments are similar to docstrings.  Both are formatted with
reStructuredText.  If a comment is used to document an attribute, put a
colon after the opening pound sign (``#``)::

    class User(object):

        #: the name of the user as unicode string
        name = Column(String)

        #: the sha1 hash of the password + inline salt
        pw_hash = Column(String)


.. _Feature Branch Workflow: https://www.atlassian.com/git/tutorials/comparing-workflows/feature-branch-workflow
