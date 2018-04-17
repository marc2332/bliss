# Developer\'s Guide

The BLISS project is hosted on the [ESRF Gitlab](https://gitlab.esrf.fr/bliss/bliss).

## Cloning

To clone bliss:

    $ git clone git@gitlab.esrf.fr:bliss/bliss.git

Bliss has some dependencies on third-party software. The complete list
of dependencies can be obtained from the `setup.py` script:

    $ python setup.py egg_info

(see `bliss.egg_info/requirements.txt`).

Your work environment is a matter of taste. If you want to isolate your
bliss development it is a good idea to use virtualenv or Conda.

## Workflow

Bliss project promotes a development based on [Feature Branch
Workflow](https://www.atlassian.com/git/tutorials/comparing-workflows/feature-branch-workflow):

> The core idea behind the [Feature Branch
> Workflow](https://www.atlassian.com/git/tutorials/comparing-workflows/feature-branch-workflow)
> is that all feature development should take place in a dedicated
> branch instead of the master branch. This encapsulation makes it easy
> for multiple developers to work on a particular feature without
> disturbing the main codebase. It also means **the master branch will
> never contain broken code**, which is a huge advantage for continuous
> integration environments.
>
> Encapsulating feature development also makes it possible to leverage
> pull requests, which are a way to initiate discussions around a
> branch. They give other developers the opportunity to sign off on a
> feature before it gets integrated into the official project. Or, if
> you get stuck in the middle of a feature, you can open a pull request
> asking for suggestions from your colleagues. The point is, pull
> requests make it incredibly easy for your team to comment on each
> other's work.

### Use case story 1: Adding a new controller

John has been asked by beamline ID00 to integrate a new pressure meter
from Alibaba Inc, in their experiments.

-   First, he checks the [\~bliss.controllers]{role="mod"} repository to
    see if the device is already implemented
-   If not, he creates a new
    [issue](http://gitlab.esrf.fr/bliss/bliss/issues/new?issue) on
    gitlab. He assigns it to himself and adds labels *new feature* and
    *plugin*. He is very happy to receive a comment by his colleague
    Maria that happened to receive a similar request from ID99. They
    quickly agree on a shared development
-   They both agree to work on a new branch called
    *alibaba\_pressure\_meter*. Since John is going on vacation, it is
    up to poor Maria to start developing
-   She clones the Bliss repository and creates a new branch
    called *alibaba\_pressure\_meter*:

        $ git checkout -b alibaba_pressure_meter

-   She is a fan of [TDD]{role="term"}, so she starts thinking how she
    would like to control the device and then she starts writing simple
    unit tests. They will all fail in the beginning but that doesn\'t
    scare her at all because now she knows exactly what to do to make
    them work
-   After some development, Maria is happy with the result so she pushes
    her work to gitlab. She can immediately see on the Bliss [ESRF
    Gitlab]() project page a new log entry with the work she just
    pushed. Gitlab even offers to create a *merge request* so she just
    clicks on it, fills in the missing data in the form and assigns her
    colleague Marco to integrate her merge request. Maria is quite
    confident because she knows that an extra pair of eyes will help
    catch any issue with her proposition
-   Marco makes some comments on Maria\'s code directly on the gitlab
    merge request web page. Maria realizes that she forgot to document
    one of the most important methods so she fixes the commit. Marco can
    now accept the merge request
-   John comes back from vacation and he is suprised to see the code for
    his device is already available in the master branch. Since his use
    case is a little different that Maria\'s, he realizes that he needs
    to add a couple more functions so he makes a new
    [issue](http://gitlab.esrf.fr/bliss/bliss/issues/new?issue) on
    gitlab and the process repeats again

## Contributing

You can contribute to Bliss in many ways: from simple (or hard) bug
fixes to writting new controller extensions, introduce new features or
writing documentation. No matter how you are contributing, the following
principles apply:

-   Try to use the same code style as used in the rest of the project.
    See the [bliss-style-guide]{role="ref"} below for more information
-   New features should be documented. Include examples and use cases
    where appropriate
-   Add appropriate unit tests

## Bliss Module Template

Here is a template that you can use to start writing a new bliss module:

```python
# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2016 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

"""A brief description goes here.

Long description here with examples if possible
"""

__all__ = [] # list of members to export

# standard module imports

# third-party module imports

# local bliss imports
```

Example of a motor controller extension:

```python
# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2016 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

"""ExampleController motor controller

To instantiate a new ExampleController motor controller, configure it with:

```yaml
    plugin: emotion
    class: ExampleController
    host: iceid00a
    axes:
      - name: th
        address: 01
        unit: deg
        steps_per_unit: 1
        velocity: 0        # unit/s
        acceleration: 0    # unit/s/s
        backlash:          # unit
```

"""

__all__ = ['ExampleController']

import os
import sys
import string

import gevent

from bliss.controllers.motor import Controller

class ExampleController(Controller):
    """
    The ExampleController motor controller.
    """

    def move(self, axis, position, wait=False):
        """
        Move the given axis to the given absolute position

        Note:
            using `wait=True` will block the current :class:`~gevent.Greenlet`.

        See Also:
            :meth:`~ExampleController.rmove`

        Args:
            axis (int): valid axis number (1..8, 11..18, ...,)
            position (int): position (steps)
            wait (bool): wait or not for motion to end [default: False]

        Returns:
            int: actual position where motor is (steps)
        """
        pass

```

Bliss Style Guide
-----------------

The Bliss style guide summarizes the Bliss coding guidelines. When
adding code to Bliss (new feature, new extension or simply a patch) make
sure you follow these guide lines.

In general the Bliss Style Guide closely follows [PEP8](https://www.python.org/dev/peps/pep-0008/) with
some small differences and extensions.

General Layout
--------------

Indentation:

:   4 real spaces. No tabs, no exceptions.

Maximum line length:

:   79 characters with a soft limit for 84 if absolutely necessary. Try
    to avoid too nested code by cleverly placing break, continue and
    return statements.

Continuing long statements:

:   To continue a statement you can use backslashes in which case you
    should align the next line with the last dot or equal sign, or
    indent four spaces:

        this_is_a_very_long(function_call, 'with many parameters') \
            .that_returns_an_object_with_an_attribute

        MyModel.query.filter(MyModel.scalar > 120) \
                     .order_by(MyModel.name.desc()) \
                     .limit(10)

    If you break in a statement with parentheses or braces, align to the
    braces:

        this_is_a_very_long(function_call, 'with many parameters',
                            23, 42, 'and even more')

    For lists or tuples with many items, break immediately after the
    opening brace:

        items = [
            'this is the first', 'set of items', 'with more items',
            'to come in this line', 'like this'
        ]

Blank lines:

:   Top level functions and classes are separated by two lines,
    everything else by one. Do not use too many blank lines to separate
    logical segments in code. Example:

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

:   -   No whitespace for unary operators that are not words (e.g.: `-`,
        `~` etc.) as well on the inner side of parentheses.
    -   Whitespace is placed between binary operators.

    Good:

        exp = -1.05
        value = (item_value / item_count) * offset / exp
        value = my_list[index]
        value = my_dict['key']

    Bad:

        exp = - 1.05
        value = ( item_value / item_count ) * offset / exp
        value = (item_value/item_count)*offset/exp
        value=( item_value/item_count ) * offset/exp
        value = my_list[ index ]
        value = my_dict ['key']

Yoda statements are a no-go:

:   Never compare constant with variable, always variable with constant:

    Good:

        if method == 'md5':
            pass

    Bad:

        if 'md5' == method:
            pass

Comparisons:

:   -   against arbitrary types: `==` and `!=`
    -   against singletons with `is` and `is not` (eg:
        `foo is not None`)
    -   never compare something with `True` or `False` (for example
        never do `foo == False`, do `not foo` instead)

Negated containment checks:

:   use `foo not in bar` instead of `not foo in bar`

Instance checks:

:   `isinstance(a, C)` instead of `type(A) is C`, but try to avoid
    instance checks in general. Check for features.

Naming Conventions
------------------

-   Module names: `lowercase_with_underscores`
-   Class names: `CamelCase`, with acronyms kept uppercase (`HTTPWriter`
    and not `HttpWriter`)
-   Variable names: `lowercase_with_underscores`
-   Method and function names: `lowercase_with_underscores`
-   Constants: `UPPERCASE_WITH_UNDERSCORES`
-   precompiled regular expressions: `name_re`

Protected members are prefixed with a single underscore. Double
underscores are reserved for mixin classes.

On classes with keywords, trailing underscores are appended. Clashes
with builtins are allowed and **must not** be resolved by appending an
underline to the variable name. If the function needs to access a
shadowed builtin, rebind the builtin to a different name instead.

Function and method arguments:

:   -   class methods: `cls` as first parameter
    -   instance methods: `self` as first parameter
    -   lambdas for properties might have the first parameter replaced
        with `x` like in
        `display_name = property(lambda x: x.real_name or x.username)`

Docstrings
----------

Docstring conventions:

:   All docstrings are formatted with reStructuredText as understood by
    Sphinx. Depending on the number of lines in the docstring, they are
    laid out differently. If it\'s just one line, the closing triple
    quote is on the same line as the opening, otherwise the text is on
    the same line as the opening quote and the triple quote that closes
    the string on its own line:

        def foo():
            """This is a simple docstring"""


        def bar():
            """
        This is a longer docstring with so much information in there
            that it spans three lines.  In this case the closing triple quote
            is on its own line.
            """

    Bliss supports *napoleon* sphinx extension. The recommended way to
    document API is to follow the [Google Python Style
    Guide](http://google.github.io/styleguide/pyguide.html):

        def move(axis, position, wait=False):
            """
            move the given axis to the given absolute position

            Note:
                using `wait=True` will block the current :class:`~gevent.Greenlet`.

            See Also:
                :func:`rmove`

            Args:
                axis (Axis): instance of bliss :class:`bliss.common.axis.Axis`
                position (float): position (axis units)
                wait (bool): wait or not for motion to end [default: False]

            Returns:
                float: actual position where motor is (axis units)
            """
            pass

Module header:

:   The module header consists of an utf-8 encoding declaration (if non
    ASCII letters are used, but it is recommended all the time) and a
    standard docstring:

        # -*- coding: utf-8 -*-
        #
        # This file is part of the bliss project
        #
        # Copyright (c) 2016 Beamline Control Unit, ESRF
        # Distributed under the GNU LGPLv3. See LICENSE for more info.

Comments
--------

Rules for comments are similar to docstrings. Both are formatted with
reStructuredText. If a comment is used to document an attribute, put a
colon after the opening pound sign (`#`):

    class User(object):

        #: the name of the user as unicode string
        name = Column(String)

        #: the sha1 hash of the password + inline salt
        pw_hash = Column(String)
